#!/usr/bin/env python3
"""
Summit Media Dashboard
- User view: Monthly spend / leads / CPL per account + active campaigns
- Admin view: High CPL adset monitor (adset-level heatmap) with date picker
- Auth: hardcoded passwords via st.secrets
- Hosting: Streamlit Community Cloud (secrets via TOML)
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import sqlite3
import pandas as pd
import html as html_lib
import json
import os
import time
from datetime import datetime, timedelta, date
from typing import Optional
from calendar import monthrange
import plotly.graph_objects as go

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Summit Life Group - Media Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Credentials & secrets ─────────────────────────────────────────────────────
# On Streamlit Community Cloud set these in Settings → Secrets:
#   [auth]
#   user_password  = "..."
#   admin_password = "..."
#   [meta]
#   access_token   = "..."

CREDS = {
    "user":  st.secrets.get("auth", {}).get("user_password",  "user123"),
    "admin": st.secrets.get("auth", {}).get("admin_password", "admin123"),
}
META_TOKEN   = st.secrets.get("meta", {}).get("access_token", os.getenv("FACEBOOK_ACCESS_TOKEN", ""))
API_VERSION  = "v23.0"
BASE_URL     = f"https://graph.facebook.com/{API_VERSION}"
DB_NAME      = "summit_dashboard.db"
CPL_THRESHOLD = 50.0

# ── Fixed ad accounts ─────────────────────────────────────────────────────────
ACCOUNTS = [
    {"id": "act_256997828970145",  "name": "Summit 2"},
    {"id": "act_311776766505945",  "name": "Summit Life Insurance Ad Account 1"},
    {"id": "act_681511289264579",  "name": "JMDBGA"},
]

# ── Conversion action types (from original CPL monitor) ───────────────────────
PIXEL_ACTIONS = {
    "offsite_conversion.fb_pixel_complete_registration",
    "omni_complete_registration",
    "offsite_conversion.fb_pixel_custom",
    "offsite_conversion.fb_pixel_lead",
    "complete_registration",
}
LEAD_FORM_ACTIONS = {
    "lead",
    "onsite_conversion.lead_grouped",
    "leadgen_grouped",
    "contact",
    "onsite_conversion.lead",
}
OTHER_ACTIONS = {"purchase", "onsite_conversion.post_save"}
CONVERSION_ACTIONS = PIXEL_ACTIONS | LEAD_FORM_ACTIONS | OTHER_ACTIONS

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
body, [data-testid="stAppViewContainer"] { background: #ffffff; color: #1a1a18; font-size: 15px; }
h1, h2, h3, h4 { color: #1a1a18; }
p, li, span, div { font-size: 15px; }

/* ── Login card ── */
.login-wrap { max-width: 380px; margin: 80px auto; padding: 40px; background: #f9f9f7;
              border: 1px solid #e0e0de; border-radius: 12px; }

/* ── Account section card ── */
.acct-card { background: #ffffff; border: 1px solid #e0e0de; border-radius: 10px;
             padding: 20px 24px; margin-bottom: 24px; }
.acct-title { font-size: 20px; font-weight: 700; color: #1a1a18; margin-bottom: 4px; }
.acct-sub   { font-size: 14px; color: #888; margin-bottom: 16px; }

/* ── Period badge ── */
.period-badge { display:inline-block; background:#f0f0ee; color:#555; font-size:13px;
                font-weight:600; padding:2px 8px; border-radius:99px; margin-right:6px; }

/* ── KPI tiles ── */
.kpi-row { display:flex; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
.kpi-tile { background:#f7f7f5; border:1px solid #e8e8e4; border-radius:8px;
            padding:16px 20px; min-width:160px; flex:1; }
.kpi-label { font-size:13px; color:#888; font-weight:600; text-transform:uppercase;
             letter-spacing:.05em; margin-bottom:6px; }
.kpi-value { font-size:26px; font-weight:700; color:#1a1a18; }
.kpi-sub   { font-size:13px; color:#aaa; margin-top:4px; }

/* ── Campaign table ── */
.camp-table { width:100%; border-collapse:collapse; font-size:14px; margin-top:8px; }
.camp-table th { text-align:left; padding:8px 12px; font-size:13px; font-weight:600;
                 color:#888; border-bottom:2px solid #e8e8e4; }
.camp-table th.right { text-align:right; }
.camp-table td { padding:9px 12px; border-bottom:1px solid #f0f0ee; color:#1a1a18;
                 vertical-align:middle; }
.camp-table td.right { text-align:right; font-variant-numeric:tabular-nums; }
.camp-table tr:last-child td { border-bottom:none; }
.camp-table tr:hover td { background:#fafaf8; }
.cpl-pill { display:inline-block; padding:3px 10px; border-radius:99px;
            font-weight:600; font-size:13px; }
.pill-great { background:#d1f0d1; color:#1a6b1a; }
.pill-ok    { background:#fdf3b0; color:#7a6500; }
.pill-watch { background:#fce08a; color:#7a5200; }
.pill-high  { background:#f9b87a; color:#7a2e00; }
.pill-vhigh { background:#f57c56; color:#5c1000; }
.pill-crit  { background:#e34b2e; color:#ffffff; }
.pill-none  { background:#eeeeee; color:#888888; }

/* ── Section label ── */
.section-label { font-size:15px; font-weight:600; color:#1a1a18; margin:16px 0 8px 0; }

/* ── Period tabs ── */
.stTabs [data-baseweb="tab-list"] { gap:4px; }
.stTabs [data-baseweb="tab"] { font-size:15px; padding:8px 16px; border-radius:6px; }

/* ── Heatmap cells (admin) ── */
.hcell { display:inline-block; padding:3px 8px; border-radius:4px; font-weight:600;
         font-size:13px; min-width:64px; text-align:center; }
.cpl-great  { background:#d1f0d1; color:#1a6b1a; }
.cpl-ok     { background:#fdf3b0; color:#7a6500; }
.cpl-watch  { background:#fce08a; color:#7a5200; }
.cpl-high   { background:#f9b87a; color:#7a2e00; }
.cpl-vhigh  { background:#f57c56; color:#5c1000; }
.cpl-crit   { background:#e34b2e; color:#ffffff; }
.cpl-zero   { background:#d6d6d6; color:#444444; }
.cpl-none   { color:#aaaaaa; font-size:12px; }
.badge-pause   { background:#fde8e8; color:#c0392b; padding:2px 8px; border-radius:99px;
                 font-size:11px; font-weight:600; }
.badge-monitor { background:#fef3cd; color:#856404; padding:2px 8px; border-radius:99px;
                 font-size:11px; font-weight:600; }
.badge-red     { background:#fde8e8; color:#c0392b; padding:2px 8px; border-radius:99px;
                 font-size:11px; font-weight:600; }
.badge-amber   { background:#fef3cd; color:#856404; padding:2px 8px; border-radius:99px;
                 font-size:11px; font-weight:600; }

/* ── Sidebar ── */
[data-testid="stSidebar"] { background: #f7f7f5; }
[data-testid="stSidebar"] .stMarkdown p { color: #1a1a18; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def parse_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0

def esc(text: str) -> str:
    return html_lib.escape(str(text))

def extract_results(actions) -> float:
    """
    Extract result count from Meta actions array.
    Takes the MAX value across matching action types — never sums them,
    because Meta often returns the same conversion under multiple action_type
    names (e.g. 'lead' and 'offsite_conversion.fb_pixel_lead' are the same event).
    """
    if not isinstance(actions, list):
        return 0.0
    best = 0.0
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("action_type") in (
            "offsite_conversion.fb_pixel_complete_registration",
            "complete_registration",
            "offsite_conversion.fb_pixel_lead",
            "onsite_web_lead",
            "lead",
            "onsite_conversion.lead_grouped",
            "leadgen_grouped",
        ):
            v = parse_float(action.get("value", 0))
            if v > best:
                best = v
    return best

def extract_cpa(cost_per_action_type) -> Optional[float]:
    """
    Extract cost per result from cost_per_action_type array.
    Returns the value for the first matching lead/conversion action type.
    """
    if not isinstance(cost_per_action_type, list):
        return None
    for action in cost_per_action_type:
        if not isinstance(action, dict):
            continue
        if action.get("action_type") in (
            "offsite_conversion.fb_pixel_complete_registration",
            "complete_registration",
            "offsite_conversion.fb_pixel_lead",
            "onsite_web_lead",
            "lead",
            "onsite_conversion.lead_grouped",
            "leadgen_grouped",
        ):
            v = parse_float(action.get("value", 0))
            if v > 0:
                return v
    return None

def _is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return pd.isna(v)
    except Exception:
        return False

def cpl_class(cpl):
    if _is_missing(cpl): return "cpl-none"
    if cpl < 55:  return "cpl-great"
    if cpl < 65:  return "cpl-ok"
    if cpl < 75:  return "cpl-watch"
    if cpl < 100: return "cpl-high"
    if cpl < 130: return "cpl-vhigh"
    return "cpl-crit"

def cpl_pill_class(cpl):
    """Same scale but for pill badges in user view."""
    if _is_missing(cpl): return "pill-none"
    if cpl < 55:  return "pill-great"
    if cpl < 65:  return "pill-ok"
    if cpl < 75:  return "pill-watch"
    if cpl < 100: return "pill-high"
    if cpl < 130: return "pill-vhigh"
    return "pill-crit"

def fmt_cpl(cpl):
    if _is_missing(cpl): return "—"
    return f"${cpl:,.2f}"

def fmt_spend(v: float) -> str:
    if v == 0: return "—"
    return f"${v:,.2f}"

def fmt_int(v) -> str:
    if _is_missing(v) or v == 0: return "—"
    return f"{int(v):,}"

def hcell(cpl) -> str:
    css   = cpl_class(cpl)
    label = fmt_cpl(cpl)
    return f'<span class="hcell {css}">{label}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# DATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def month_range(year: int, month: int):
    first = date(year, month, 1)
    last  = date(year, month, monthrange(year, month)[1])
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")

def get_default_periods():
    today = date.today()
    y, m  = today.year, today.month

    this_since, this_until = month_range(y, m)

    last_m = m - 1 if m > 1 else 12
    last_y = y if m > 1 else y - 1
    last_since, last_until = month_range(last_y, last_m)

    prev_m = last_m - 1 if last_m > 1 else 12
    prev_y = last_y if last_m > 1 else last_y - 1
    prev_since, prev_until = month_range(prev_y, prev_m)

    def label(yr, mo):
        return date(yr, mo, 1).strftime("%B %Y")

    return [
        {"label": f"This Month ({label(y, m)})",       "since": this_since, "until": today.strftime("%Y-%m-%d")},
        {"label": f"Last Month ({label(last_y, last_m)})", "since": last_since, "until": last_until},
        {"label": f"Previous Month ({label(prev_y, prev_m)})", "since": prev_since, "until": prev_until},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# META API
# ─────────────────────────────────────────────────────────────────────────────

class MetaAPI:
    def __init__(self, token: str):
        self.token = token

    def _get(self, url: str, params: dict) -> dict:
        params["access_token"] = self.token
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_account_insights(self, account_id: str, since: str, until: str) -> dict:
        """Account-level: spend + leads for the period."""
        url = f"{BASE_URL}/{account_id}/insights"
        params = {
            "fields": "spend,actions,cost_per_action_type,impressions,clicks",
            "time_range": json.dumps({"since": since, "until": until}),
            "level": "account",
            "limit": 1,
        }
        try:
            data = self._get(url, params)
            rows = data.get("data", [])
            return rows[0] if rows else {}
        except Exception as e:
            st.warning(f"Could not fetch account insights: {e}")
            return {}

    def get_active_campaign_ids(self, account_id: str) -> set:
        """Returns a set of campaign IDs that are currently ACTIVE right now."""
        url = f"{BASE_URL}/{account_id}/campaigns"
        params = {
            "fields": "id,effective_status",
            "effective_status": json.dumps(["ACTIVE"]),
            "limit": 500,
        }
        active_ids = set()
        try:
            while url:
                data = self._get(url, params)
                for c in data.get("data", []):
                    active_ids.add(c["id"])
                url = data.get("paging", {}).get("next")
                params = {}
        except Exception as e:
            st.warning(f"Could not fetch active campaigns: {e}")
        return active_ids

    def get_campaign_insights(self, account_id: str, since: str, until: str) -> list:
        """Campaign-level: spend + leads. Returns all campaigns that had spend > 0
        in the period — this correctly handles historical periods where campaigns
        may now be paused/inactive."""
        url = f"{BASE_URL}/{account_id}/insights"
        params = {
            "fields": "campaign_name,campaign_id,spend,actions,cost_per_action_type,impressions,clicks",
            "time_range": json.dumps({"since": since, "until": until}),
            "level": "campaign",
            "limit": 200,
        }
        rows = []
        try:
            while url:
                data = self._get(url, params)
                for row in data.get("data", []):
                    # Only include campaigns that actually spent in this period
                    if parse_float(row.get("spend", 0)) > 0:
                        rows.append(row)
                url  = data.get("paging", {}).get("next")
                params = {}
        except Exception as e:
            st.warning(f"Could not fetch campaign insights: {e}")
        return rows

    def get_adset_insights(self, account_id: str, since: str, until: str) -> list:
        """Adset-level insights for CPL monitor (admin)."""
        url = f"{BASE_URL}/{account_id}/insights"
        params = {
            "level": "adset",
            "fields": "campaign_name,campaign_id,adset_name,adset_id,spend,actions,cost_per_action_type",
            "time_range": json.dumps({"since": since, "until": until}),
            "limit": 500,
        }
        rows = []
        while url:
            try:
                r = requests.get(url, params={**params, "access_token": self.token}, timeout=30)
                if r.status_code == 429 or "request limit" in r.text.lower():
                    st.warning("⏳ Rate limit — waiting 60 s…")
                    time.sleep(60)
                    continue
                r.raise_for_status()
                data = r.json()
                rows.extend(data.get("data", []))
                url  = data.get("paging", {}).get("next")
                params = {}
                time.sleep(0.1)
            except Exception as e:
                st.error(f"Error fetching adset insights: {e}")
                break
        return rows


# ─────────────────────────────────────────────────────────────────────────────
# SQLITE (history for admin CPL monitor)
# ─────────────────────────────────────────────────────────────────────────────

class DB:
    def __init__(self, name: str):
        self.name = name
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.name)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                account_name  TEXT,
                campaign_name TEXT,
                adset_name    TEXT,
                adset_id      TEXT,
                spend         REAL,
                results       REAL,
                cpl           REAL,
                window        TEXT,
                issue_type    TEXT
            )
        """)
        conn.commit()
        conn.close()

    def save_check(self, rows: list):
        if not rows:
            return
        conn = sqlite3.connect(self.name)
        c = conn.cursor()
        c.executemany("""
            INSERT INTO checks(account_name, campaign_name, adset_name, adset_id,
                               spend, results, cpl, window, issue_type)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()

    def get_history(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.name)
        try:
            df = pd.read_sql_query("""
                SELECT run_at, account_name, campaign_name, adset_name,
                       cpl, spend, results, window, issue_type
                FROM checks ORDER BY run_at DESC LIMIT 2000
            """, conn)
        except Exception:
            df = pd.DataFrame()
        conn.close()
        return df


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: CPL MONITOR LOGIC
# ─────────────────────────────────────────────────────────────────────────────

TABLE_CSS = """
<style>
  * { box-sizing:border-box; margin:0; padding:0;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
  body { background:transparent; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  thead tr.header-group { background:#f7f7f5; }
  thead tr.header-sub   { background:#f7f7f5; border-bottom:1px solid #e0e0e0; }
  th { padding:6px 8px; font-size:11px; font-weight:600; color:#666; white-space:nowrap; }
  th.left   { text-align:left; }
  th.center { text-align:center; }
  th.sep    { width:8px; background:#e8e8e4; padding:0; }
  td        { padding:6px 8px; vertical-align:middle; border-bottom:1px solid #f0f0ee; }
  td.name   { font-size:12px; font-weight:500; color:#1a1a1a; word-break:break-word; max-width:320px; }
  td.spend  { font-size:11px; color:#888; text-align:center; white-space:nowrap; }
  td.cell   { text-align:center; }
  td.sep    { width:8px; background:#e8e8e4; padding:0; }
  tr.acct   { background:#f4f4f2; }
  tr.acct td { font-size:11px; font-weight:700; color:#555; padding:6px 10px; letter-spacing:.01em; }
  tr.camp   { background:#fafaf8; }
  tr.camp td { font-size:11px; font-weight:500; color:#888; padding:4px 10px 4px 22px;
               border-bottom:1px solid #f0f0ee; font-style:italic; }
  tr.zero-row { background:#fffdf6; }
  tr:last-child td { border-bottom:none; }
  .hcell { display:inline-block; padding:3px 10px; border-radius:4px; font-weight:600;
           font-size:12px; min-width:60px; text-align:center; }
  .cpl-great { background:#d1f0d1; color:#1a6b1a; }
  .cpl-ok    { background:#fdf3b0; color:#7a6500; }
  .cpl-watch { background:#fce08a; color:#7a5200; }
  .cpl-high  { background:#f9b87a; color:#7a2e00; }
  .cpl-vhigh { background:#f57c56; color:#5c1000; }
  .cpl-crit  { background:#e34b2e; color:#fff;    }
  .cpl-zero  { background:#d6d6d6; color:#444;    }
  .cpl-none  { color:#bbb; font-size:11px; }
  .badge-pause   { background:#fde8e8; color:#c0392b; padding:2px 8px; border-radius:99px;
                   font-size:11px; font-weight:600; white-space:nowrap; }
  .badge-monitor { background:#fef3cd; color:#856404; padding:2px 8px; border-radius:99px;
                   font-size:11px; font-weight:600; white-space:nowrap; }
  .wrap { border:1px solid #e0e0e0; border-radius:8px; overflow:hidden; }
</style>
"""

def _full_html(body: str) -> str:
    return f"<!DOCTYPE html><html><head>{TABLE_CSS}</head><body>{body}</body></html>"

def _row_height(n_rows: int, header_px: int = 58) -> int:
    return header_px + n_rows * 34 + 20

def render_high_cpl_table(df: pd.DataFrame):
    rows_html = []
    current_account  = None
    current_campaign = None
    n_rows = 0
    for _, r in df.sort_values(["account_name", "campaign_name", "adset_name"]).iterrows():
        if r["account_name"] != current_account:
            current_account  = r["account_name"]
            current_campaign = None
            rows_html.append(f'<tr class="acct"><td colspan="13">{esc(current_account)}</td></tr>')
            n_rows += 1
        if r["campaign_name"] != current_campaign:
            current_campaign = r["campaign_name"]
            rows_html.append(f'<tr class="camp"><td colspan="13">📁 {esc(current_campaign)}</td></tr>')
            n_rows += 1
        rows_html.append(f"""<tr>
          <td class="name" style="padding-left:28px;">{esc(r["adset_name"])}</td>
          <td class="spend">{fmt_spend(r["spend_1d"])}</td>
          <td class="cell">{hcell(r["cpl_1d"])}</td>
          <td class="sep"></td>
          <td class="spend">{fmt_spend(r["spend_3d"])}</td>
          <td class="cell">{hcell(r["cpl_3d"])}</td>
          <td class="sep"></td>
          <td class="spend">{fmt_spend(r["spend_7d"])}</td>
          <td class="cell">{hcell(r["cpl_7d"])}</td>
          <td class="sep"></td>
          <td class="spend">{fmt_spend(r["spend_14d"])}</td>
          <td class="cell">{hcell(r["cpl_14d"])}</td>
        </tr>""")
        n_rows += 1

    table = f"""
    <div class="wrap"><table>
      <thead>
        <tr class="header-group">
          <th class="left" rowspan="2" style="width:30%;border-bottom:1px solid #ddd;">Adset</th>
          <th class="center" colspan="2" style="border-bottom:2px solid #ddd;">Yesterday</th>
          <th class="sep" rowspan="2"></th>
          <th class="center" colspan="2" style="border-bottom:2px solid #ccc;">Last 3 Days</th>
          <th class="sep" rowspan="2"></th>
          <th class="center" colspan="2" style="border-bottom:2px solid #aaa;">Last 7 Days</th>
          <th class="sep" rowspan="2"></th>
          <th class="center" colspan="2" style="border-bottom:2px solid #888;">Last 14 Days</th>
        </tr>
        <tr class="header-sub">
          {''.join(['<th class="center" style="font-weight:500;color:#999;font-size:10px;">Spend</th><th class="center" style="font-weight:500;color:#999;font-size:10px;">CPL</th>'] * 4)}
        </tr>
      </thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table></div>"""
    components.html(_full_html(table), height=_row_height(n_rows), scrolling=False)

def render_zero_table(df: pd.DataFrame):
    rows_html = []
    current_account  = None
    current_campaign = None
    n_rows = 0
    for _, r in df.sort_values(["account_name", "campaign_name", "adset_name"]).iterrows():
        if r["account_name"] != current_account:
            current_account  = r["account_name"]
            current_campaign = None
            rows_html.append(f'<tr class="acct"><td colspan="11">{esc(current_account)}</td></tr>')
            n_rows += 1
        if r["campaign_name"] != current_campaign:
            current_campaign = r["campaign_name"]
            rows_html.append(f'<tr class="camp"><td colspan="11">📁 {esc(current_campaign)}</td></tr>')
            n_rows += 1
        max_zero_spend = max(
            r["spend_3d"]  if r["results_3d"]  == 0 else 0,
            r["spend_7d"]  if r["results_7d"]  == 0 else 0,
            r["spend_14d"] if r["results_14d"] == 0 else 0,
        )
        badge = ('<span class="badge-pause">Pause</span>'
                 if max_zero_spend >= CPL_THRESHOLD * 2
                 else '<span class="badge-monitor">Monitor</span>')

        def zcell(results, spend):
            if spend > 0 and results == 0:
                return '<span class="hcell cpl-zero">0</span>'
            elif results > 0:
                return f'<span style="font-size:12px;font-weight:500;color:#1a6b1a;">{int(results)}</span>'
            return '<span style="color:#ccc;">—</span>'

        rows_html.append(f"""<tr class="zero-row">
          <td class="name" style="padding-left:28px;">{esc(r["adset_name"])}</td>
          <td class="spend">{fmt_spend(r["spend_1d"])}</td>
          <td class="cell">{zcell(r["results_1d"], r["spend_1d"])}</td>
          <td class="sep"></td>
          <td class="spend">{fmt_spend(r["spend_3d"])}</td>
          <td class="cell">{zcell(r["results_3d"], r["spend_3d"])}</td>
          <td class="sep"></td>
          <td class="spend">{fmt_spend(r["spend_7d"])}</td>
          <td class="cell">{zcell(r["results_7d"], r["spend_7d"])}</td>
          <td class="sep"></td>
          <td class="spend">{fmt_spend(r["spend_14d"])}</td>
          <td class="cell">{zcell(r["results_14d"], r["spend_14d"])}</td>
          <td class="cell">{badge}</td>
        </tr>""")
        n_rows += 1

    table = f"""
    <div class="wrap"><table>
      <thead>
        <tr class="header-group">
          <th class="left" rowspan="2" style="width:30%;border-bottom:1px solid #ddd;">Adset</th>
          <th class="center" colspan="2" style="border-bottom:2px solid #ddd;">Yesterday</th>
          <th class="sep" rowspan="2"></th>
          <th class="center" colspan="2" style="border-bottom:2px solid #ccc;">Last 3 Days</th>
          <th class="sep" rowspan="2"></th>
          <th class="center" colspan="2" style="border-bottom:2px solid #aaa;">Last 7 Days</th>
          <th class="sep" rowspan="2"></th>
          <th class="center" colspan="2" style="border-bottom:2px solid #888;">Last 14 Days</th>
          <th class="center" rowspan="2" style="border-bottom:1px solid #ddd;">Action</th>
        </tr>
        <tr class="header-sub">
          {''.join(['<th class="center" style="font-weight:500;color:#999;font-size:10px;">Spend</th><th class="center" style="font-weight:500;color:#999;font-size:10px;">Results</th>'] * 4)}
        </tr>
      </thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table></div>"""
    components.html(_full_html(table), height=_row_height(n_rows), scrolling=False)

def render_legend():
    legend_html = """
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 12px;">
      <span style="font-size:11px;color:#aaa;">CPL scale:</span>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#d1f0d1;display:inline-block;"></span>&lt;$55 great</div>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#fdf3b0;display:inline-block;"></span>$55–65 ok</div>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#fce08a;display:inline-block;"></span>$65–75 watch</div>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#f9b87a;display:inline-block;"></span>$75–100 high</div>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#f57c56;display:inline-block;"></span>$100–130 very high</div>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#e34b2e;display:inline-block;"></span>&gt;$130 critical</div>
      <div style="display:flex;align-items:center;gap:4px;font-size:11px;color:#555;">
        <span style="width:18px;height:13px;border-radius:3px;background:#d6d6d6;display:inline-block;"></span>0 results</div>
    </div></div>"""
    components.html(f"<!DOCTYPE html><html><body>{legend_html}</body></html>", height=44)

def run_admin_check(api: MetaAPI, since: str, until: str):
    today            = date.today()
    yesterday        = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    three_days_ago   = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    seven_days_ago   = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    fourteen_days_ago = (today - timedelta(days=14)).strftime("%Y-%m-%d")

    all_rows = []
    progress = st.progress(0)
    status   = st.empty()

    for idx, acc in enumerate(ACCOUNTS, 1):
        aid, aname = acc["id"], acc["name"]
        status.write(f"Fetching **{aname}** ({idx}/{len(ACCOUNTS)})…")

        ins_1d  = api.get_adset_insights(aid, yesterday,          yesterday)
        ins_3d  = api.get_adset_insights(aid, three_days_ago,     yesterday)
        ins_7d  = api.get_adset_insights(aid, seven_days_ago,     yesterday)
        ins_14d = api.get_adset_insights(aid, fourteen_days_ago,  yesterday)

        def build_map(rows):
            return {r["adset_id"]: r for r in rows}

        map_1d  = build_map(ins_1d)
        map_3d  = build_map(ins_3d)
        map_7d  = build_map(ins_7d)
        map_14d = build_map(ins_14d)
        all_ids = set(list(map_1d) + list(map_3d) + list(map_7d) + list(map_14d))

        for adset_id in all_ids:
            r1  = map_1d.get(adset_id,  {})
            r3  = map_3d.get(adset_id,  {})
            r7  = map_7d.get(adset_id,  {})
            r14 = map_14d.get(adset_id, {})
            info = r1 or r3 or r7 or r14

            def window_metrics(rw):
                sp  = parse_float(rw.get("spend"))
                res = extract_results(rw.get("actions", []))
                cpa = extract_cpa(rw.get("cost_per_action_type"))
                cpl = cpa if cpa else (sp / res if res > 0 else None)
                return sp, res, cpl

            sp1,  res1,  cpl1  = window_metrics(r1)
            sp3,  res3,  cpl3  = window_metrics(r3)
            sp7,  res7,  cpl7  = window_metrics(r7)
            sp14, res14, cpl14 = window_metrics(r14)

            has_high_cpl = any([
                cpl1  and cpl1  > CPL_THRESHOLD,
                cpl3  and cpl3  > CPL_THRESHOLD,
                cpl7  and cpl7  > CPL_THRESHOLD,
                cpl14 and cpl14 > CPL_THRESHOLD,
            ])
            has_zero = any([
                sp3  > CPL_THRESHOLD and res3  == 0,
                sp7  > CPL_THRESHOLD and res7  == 0,
                sp14 > CPL_THRESHOLD and res14 == 0,
            ])

            if has_high_cpl or has_zero:
                all_rows.append({
                    "account_name":  aname,
                    "campaign_name": info.get("campaign_name", ""),
                    "adset_name":    info.get("adset_name", ""),
                    "adset_id":      adset_id,
                    "spend_1d":  sp1,  "results_1d":  res1,  "cpl_1d":  cpl1,
                    "spend_3d":  sp3,  "results_3d":  res3,  "cpl_3d":  cpl3,
                    "spend_7d":  sp7,  "results_7d":  res7,  "cpl_7d":  cpl7,
                    "spend_14d": sp14, "results_14d": res14, "cpl_14d": cpl14,
                    "has_high_cpl": has_high_cpl,
                    "has_zero":     has_zero,
                })
        progress.progress(idx / len(ACCOUNTS))

    progress.empty()
    status.empty()

    if not all_rows:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Save history
    db = DB(DB_NAME)
    history_rows = []
    for _, r in df.iterrows():
        issues = []
        if r["has_high_cpl"]: issues.append("HIGH_CPL")
        if r["has_zero"]:     issues.append("NO_RESULTS")
        history_rows.append((
            r["account_name"], r["campaign_name"], r["adset_name"], r["adset_id"],
            float(r["spend_3d"]), float(r["results_3d"]),
            float(r["cpl_3d"]) if r["cpl_3d"] is not None else None,
            "Last 3 Days", ",".join(issues)
        ))
    db.save_check(history_rows)

    high_cpl = df[df["has_high_cpl"]].copy()
    zero_res  = df[df["has_zero"]].copy()
    return high_cpl, zero_res


# ─────────────────────────────────────────────────────────────────────────────
# USER VIEW: Monthly report
# ─────────────────────────────────────────────────────────────────────────────

def render_trend_chart(period_summaries: list):
    """
    Renders a combo chart: grouped bars for Spend & Leads (left axis),
    line for CPL (right axis), one group per period.
    period_summaries = [{"label": str, "spend": float, "leads": float, "cpl": float|None}, ...]
    Only renders if we have at least 2 periods with data.
    """
    labels = [p["label"] for p in period_summaries]
    spends = [p["spend"] for p in period_summaries]
    leads  = [p["leads"] for p in period_summaries]
    cpls   = [p["cpl"] if p["cpl"] is not None else 0 for p in period_summaries]

    # Don't render if everything is zero
    if all(s == 0 for s in spends):
        return

    fig = go.Figure()

    # Bar: Spend
    fig.add_trace(go.Bar(
        name="Spend ($)",
        x=labels,
        y=spends,
        marker_color="#4A90D9",
        yaxis="y1",
        text=[f"${v:,.0f}" for v in spends],
        textposition="outside",
        textfont=dict(size=13),
    ))

    # Bar: Leads
    fig.add_trace(go.Bar(
        name="Leads",
        x=labels,
        y=leads,
        marker_color="#50C878",
        yaxis="y1",
        text=[f"{int(v):,}" if v > 0 else "" for v in leads],
        textposition="outside",
        textfont=dict(size=13),
    ))

    # Line: CPL (secondary axis)
    fig.add_trace(go.Scatter(
        name="CPL ($)",
        x=labels,
        y=cpls,
        mode="lines+markers+text",
        line=dict(color="#E05C2A", width=3),
        marker=dict(size=9, color="#E05C2A"),
        yaxis="y2",
        text=[f"${v:,.2f}" if v > 0 else "" for v in cpls],
        textposition="bottom center",
        textfont=dict(size=13, color="#E05C2A"),
    ))

    fig.update_layout(
        barmode="group",
        bargap=0.25,
        bargroupgap=0.08,
        height=320,
        margin=dict(t=60, b=10, l=10, r=10),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                  size=13, color="#1a1a18"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=13)),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=13),
        ),
        yaxis=dict(
            title=dict(text="Spend & Leads", font=dict(size=13)),
            showgrid=True,
            gridcolor="#f0f0ee",
            zeroline=False,
            tickfont=dict(size=13),
        ),
        yaxis2=dict(
            title=dict(text="CPL ($)", font=dict(size=13, color="#E05C2A")),
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=13, color="#E05C2A"),
        ),
    )

    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_account_section(api: MetaAPI, acc: dict, periods: list):
    st.markdown(f'<div class="acct-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="acct-title">📊 {acc["name"]}</div>'
                f'<div class="acct-sub">Account ID: {acc["id"]}</div>',
                unsafe_allow_html=True)

    # ── Pre-fetch all periods so chart can render before tabs ─────────────────
    # Also fetch currently-active campaign IDs once (not per period)
    active_ids_key = f"active_ids_{acc['id']}"
    if active_ids_key not in st.session_state:
        st.session_state[active_ids_key] = api.get_active_campaign_ids(acc["id"])
    active_ids = st.session_state[active_ids_key]

    period_summaries = []
    for period in periods:
        since, until  = period["since"], period["until"]
        cache_key     = f"data_{acc['id']}_{since}_{until}"
        if cache_key not in st.session_state:
            with st.spinner(f"Fetching {period['label']}…"):
                acct_data = api.get_account_insights(acc["id"], since, until)
                camp_data = api.get_campaign_insights(acc["id"], since, until)
            st.session_state[cache_key] = (acct_data, camp_data)

        acct_data, _ = st.session_state[cache_key]
        sp  = parse_float(acct_data.get("spend", 0))
        cpa = extract_cpa(acct_data.get("cost_per_action_type", []))
        lds = extract_results(acct_data.get("actions", []))
        cpl = cpa if cpa else (sp / lds if lds > 0 else None)
        period_summaries.append({
            "label": period["label"],
            "spend": sp,
            "leads": lds,
            "cpl":   cpl,
        })

    # ── Trend chart (only for default 3-period view, not custom) ─────────────
    if len(periods) >= 2:
        st.markdown('<div class="section-label">📈 3-Month Trend</div>', unsafe_allow_html=True)
        render_trend_chart(list(reversed(period_summaries)))  # oldest → newest left to right

    st.divider()

    # ── Per-period tabs ───────────────────────────────────────────────────────
    tabs = st.tabs([p["label"] for p in periods])

    for tab, period, summary in zip(tabs, periods, period_summaries):
        with tab:
            since, until  = period["since"], period["until"]
            cache_key     = f"data_{acc['id']}_{since}_{until}"
            acct_data, camp_data = st.session_state[cache_key]

            total_spend = summary["spend"]
            total_leads = summary["leads"]
            total_cpl   = summary["cpl"]
            pill_cls = cpl_pill_class(total_cpl)
            cpl_html = (f'<span class="cpl-pill {pill_cls}">{fmt_cpl(total_cpl)}</span>'
                        if total_cpl else '<span style="color:#aaa;">—</span>')

            st.markdown(f"""
            <div class="kpi-row">
              <div class="kpi-tile">
                <div class="kpi-label">Total Spend</div>
                <div class="kpi-value">{fmt_spend(total_spend)}</div>
                <div class="kpi-sub">{since} → {until}</div>
              </div>
              <div class="kpi-tile">
                <div class="kpi-label">Leads</div>
                <div class="kpi-value">{fmt_int(total_leads)}</div>
                <div class="kpi-sub">all conversion types</div>
              </div>
              <div class="kpi-tile">
                <div class="kpi-label">Cost Per Lead</div>
                <div class="kpi-value">{cpl_html}</div>
                <div class="kpi-sub">spend ÷ leads</div>
              </div>
              <div class="kpi-tile">
                <div class="kpi-label">Campaigns w/ Spend</div>
                <div class="kpi-value">{len(camp_data)}</div>
                <div class="kpi-sub">had activity this period</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Campaign breakdown
            if not camp_data:
                st.info("No campaigns with spend found for this period.")
            else:
                # Build rows first so active_now_count is known before header renders
                rows_html = []
                active_now_count = 0
                for c in sorted(camp_data, key=lambda x: -parse_float(x.get("spend", 0))):
                    sp   = parse_float(c.get("spend", 0))
                    cpa  = extract_cpa(c.get("cost_per_action_type", []))
                    lds  = extract_results(c.get("actions", []))
                    cpl  = cpa if cpa else (sp / lds if lds > 0 else None)
                    cname = esc(c.get("campaign_name", "—"))
                    pill_c   = cpl_pill_class(cpl)
                    cpl_cell = (f'<span class="cpl-pill {pill_c}">{fmt_cpl(cpl)}</span>'
                                if cpl else '<span style="color:#aaa;">—</span>')
                    is_active = c.get("campaign_id") in active_ids
                    if is_active:
                        active_now_count += 1
                    active_badge = (
                        ' <span style="display:inline-block;background:#d1f0d1;color:#1a6b1a;'
                        'font-size:11px;font-weight:600;padding:1px 7px;border-radius:99px;'
                        'vertical-align:middle;">● Active</span>'
                        if is_active else
                        ' <span style="display:inline-block;background:#f0f0ee;color:#999;'
                        'font-size:11px;font-weight:600;padding:1px 7px;border-radius:99px;'
                        'vertical-align:middle;">Paused</span>'
                    )
                    rows_html.append(f"""<tr>
                      <td>{cname}{active_badge}</td>
                      <td class="right">{fmt_spend(sp)}</td>
                      <td class="right">{fmt_int(lds)}</td>
                      <td class="right">{cpl_cell}</td>
                    </tr>""")

                # Now render header with correct counts
                st.markdown(
                    f'<div class="section-label">Campaigns this period &nbsp;'
                    f'<span style="font-size:13px;font-weight:400;color:#888;">'
                    f'{active_now_count} currently active · {len(camp_data) - active_now_count} paused'
                    f'</span></div>',
                    unsafe_allow_html=True)

                table_html = f"""
                <table class="camp-table">
                  <thead>
                    <tr>
                      <th>Campaign</th>
                      <th class="right">Spend</th>
                      <th class="right">Leads</th>
                      <th class="right">CPL</th>
                    </tr>
                  </thead>
                  <tbody>{''.join(rows_html)}</tbody>
                </table>"""
                st.markdown(table_html, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

def show_login():
    st.markdown("""
    <div style="text-align:center;margin-top:60px;">
      <h2 style="color:#1a1a18;font-size:26px;font-weight:700;">Summit Life Group - Media Dashboard</h2>
      <p style="color:#888;font-size:14px;margin-top:4px;">Sign in to continue</p>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 1.2, 1])[1]
    with col:
        st.markdown("<br>", unsafe_allow_html=True)
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        if st.button("Sign In", type="primary", use_container_width=True):
            if password == CREDS["admin"]:
                st.session_state["role"] = "admin"
                st.rerun()
            elif password == CREDS["user"]:
                st.session_state["role"] = "user"
                st.rerun()
            else:
                st.error("Incorrect password. Try again.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

if "role" not in st.session_state:
    show_login()
    st.stop()

role = st.session_state["role"]
api  = MetaAPI(META_TOKEN)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 📊 Summit Life Group - Media")
    st.caption(f"Signed in as **{role.title()}**")
    st.divider()

    if role == "admin":
        page = st.radio("View", ["Monthly Report", "CPL Monitor", "Check History"],
                        label_visibility="collapsed")
    else:
        page = "Monthly Report"
        st.markdown("**Monthly Report**")

    st.divider()

    # Custom date range (both roles)
    st.markdown("**Custom Date Range**")
    use_custom = st.checkbox("Use custom dates", value=False)
    if use_custom:
        custom_since = st.date_input("From", value=date.today().replace(day=1))
        custom_until = st.date_input("To",   value=date.today())
    st.divider()

    if st.button("🚪 Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Build periods list ────────────────────────────────────────────────────────
if use_custom:
    periods = [{"label": f"Custom ({custom_since} → {custom_until})",
                "since": custom_since.strftime("%Y-%m-%d"),
                "until": custom_until.strftime("%Y-%m-%d")}]
else:
    periods = get_default_periods()


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY REPORT PAGE
# ─────────────────────────────────────────────────────────────────────────────
if page == "Monthly Report":
    st.markdown("## Monthly Performance Report")
    st.caption(f"Showing: Spend · Leads · CPL — active campaigns only")
    st.divider()

    for acc in ACCOUNTS:
        render_account_section(api, acc, periods)


# ─────────────────────────────────────────────────────────────────────────────
# CPL MONITOR PAGE (admin only)
# ─────────────────────────────────────────────────────────────────────────────
elif page == "CPL Monitor":
    st.markdown("## 🔴 CPL Monitor")
    st.caption(f"Adset-level · Threshold: **${CPL_THRESHOLD:.0f}** · All 3 accounts")

    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.markdown("Select a date range for the check windows (Yesterday / 3d / 7d / 14d "
                    "are always relative to today).")
    with col_btn:
        run = st.button("🔍 Run Check", type="primary", use_container_width=True)

    if run:
        today = date.today()
        since = (today - timedelta(days=14)).strftime("%Y-%m-%d")
        until = today.strftime("%Y-%m-%d")
        with st.spinner("Pulling adset data from Meta…"):
            high_cpl, zero_res = run_admin_check(api, since, until)
        st.session_state["admin_high_cpl"]   = high_cpl
        st.session_state["admin_zero_res"]   = zero_res
        st.session_state["admin_check_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    st.divider()

    if "admin_high_cpl" in st.session_state:
        high_cpl   = st.session_state["admin_high_cpl"]
        zero_res   = st.session_state["admin_zero_res"]
        check_time = st.session_state.get("admin_check_time", "")

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("🔴 High CPL adsets", len(high_cpl))
        with m2:
            st.metric("⚠️ Zero-result adsets", len(zero_res))
        with m3:
            if not high_cpl.empty:
                avg = high_cpl["cpl_3d"].dropna().mean()
                st.metric("Avg CPL (3d)", f"${avg:,.0f}" if pd.notna(avg) else "—")
        with m4:
            if not zero_res.empty:
                wasted = zero_res["spend_3d"].sum()
                st.metric("💸 Wasted spend (3d)", f"${wasted:,.0f}")

        st.caption(f"Last checked: {check_time}")
        st.info(
            f"ℹ️ **Zero-result adsets** are flagged when spend exceeds **${CPL_THRESHOLD:.0f}** "
            f"in any 3d / 7d / 14d window with zero leads. Yesterday is excluded (attribution delay).",
        )
        st.divider()

        if not zero_res.empty:
            st.markdown(
                f'### 🚨 Zero-result adsets &nbsp;'
                f'<span class="badge-amber">{len(zero_res)} adsets · spent >${CPL_THRESHOLD:.0f} with 0 results</span>',
                unsafe_allow_html=True)
            render_zero_table(zero_res)
            csv = zero_res.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Export CSV", csv,
                               f"zero_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                               "text/csv", key="zero_dl")
            st.write("")

        if not high_cpl.empty:
            st.markdown(
                f'### 🔴 High CPL adsets &nbsp;'
                f'<span class="badge-red">{len(high_cpl)} adsets · CPL &gt; ${CPL_THRESHOLD:.0f}</span>',
                unsafe_allow_html=True)
            render_legend()
            st.write("")
            render_high_cpl_table(high_cpl)
            csv = high_cpl.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Export CSV", csv,
                               f"high_cpl_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                               "text/csv", key="cpl_dl")

        if high_cpl.empty and zero_res.empty:
            st.success("✅ All adsets performing well — no issues found.")
    else:
        st.info("👆 Click **Run Check** to pull adset data from Meta.")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK HISTORY PAGE (admin only)
# ─────────────────────────────────────────────────────────────────────────────
elif page == "Check History":
    st.markdown("## 📜 Check History")
    db = DB(DB_NAME)
    history = db.get_history()
    if history.empty:
        st.info("No history yet. Run a CPL check from the CPL Monitor page.")
    else:
        st.dataframe(history, use_container_width=True, height=600)
        csv = history.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv, "cpl_history.csv", "text/csv")

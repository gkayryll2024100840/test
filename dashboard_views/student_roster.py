# STUDENT ROSTER.PY
# UPDATED: 10/4/2026
#needs optimization

import html
from functools import lru_cache

import streamlit as st
from permissions import require_edit
import re
import pandas as pd
 
from db_connect import (
    get_student_roster_data,
    get_last_updated_time,
    trigger_data_sync,
    get_max_retry_count,
    get_available_cohorts,
    get_all_programs,
    create_program,
    set_user_program,
    get_user_program,
    get_my_adviser_name,
    get_stage_labels,
    get_flagged_students,
)
 
from dashboard_views.components import (
    DARK_MODE_CSS,
    render_status_pill,
    set_header_context,
)
 
st.set_page_config(page_title="Student Roster", layout="wide")

# Roster list size: how many students show before you have to scroll,
# and the height of one row in px.
ROWS_VISIBLE = 10
ROW_HEIGHT_PX = 58


@st.cache_data(ttl=60, show_spinner=False)
def cached_stage_labels(program_id):
    """US-30: this program's stage names (set in Admin Config)."""
    return get_stage_labels(program_id)


@st.cache_data(ttl=60, show_spinner=False)
def cached_roster(program_id):
    return get_student_roster_data(program_id=program_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_programs():
    return get_all_programs()


@st.cache_data(ttl=300, show_spinner=False)
def cached_cohorts(program_id):
    return get_available_cohorts(program_id=program_id)


@st.cache_data(ttl=60, show_spinner=False)
def cached_adviser_name(user_id):
    return get_my_adviser_name(user_id)


@st.cache_data(ttl=30, show_spinner=False)
def cached_retry_count(session_id):
    return get_max_retry_count(session_id)


TERM_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3, "autumn": 3}


@lru_cache(maxsize=None)
def cohort_sort_key(cohort):
    """'1Q2425' -> (2024, 1, ...) so cohorts sort by time. Falls back to the old '2025 - Fall' style."""
    s = str(cohort).strip().upper()
    m = re.fullmatch(r"(\d)Q(\d{2})(\d{2})", s)
    if m:
        return (2000 + int(m.group(2)), int(m.group(1)), s)
    low = s.lower()
    year = re.search(r"(19|20)\d{2}", low)
    term = next((v for k, v in TERM_ORDER.items() if k in low), 0)
    return (int(year.group()) if year else 0, term, low)


@st.cache_data(ttl=300, show_spinner=False)
def get_risk_flags(program_id):
    """{StudentNumber: flag reason} for students past their program's At-Risk threshold."""
    flags = get_flagged_students(program_id)
    if flags is None or flags.empty:
        return {}
    flags = flags[flags["is_flagged"].fillna(0).astype(int) == 1]
    return {str(sn): (reason or "") for sn, reason in zip(flags["StudentNumber"], flags["flag_reason"])}


def split_label_two_lines(label: str) -> str:
    """Format a table header label into 2 lines for compact and clean presentation."""
    cleaned = str(label).strip()
    words = cleaned.split()
    if len(words) <= 1:
        return html.escape(cleaned)
    if len(words) == 2:
        return f"{html.escape(words[0])}<br>{html.escape(words[1])}"
    if len(words) == 3:
        return f"{html.escape(words[0])} {html.escape(words[1])}<br>{html.escape(words[2])}"
    mid = (len(words) + 1) // 2
    return f"{html.escape(' '.join(words[:mid]))}<br>{html.escape(' '.join(words[mid:]))}"


# filter row + refresh button styling
st.markdown(
    """<style>
/* space between the filters (stops the dropdowns from touching / overlapping) */
.st-key-sr_filters [data-testid="stHorizontalBlock"]{gap:16px !important;column-gap:16px !important;}
.st-key-sr_filters [data-testid="stColumn"]{min-width:0 !important;}
.st-key-sr_filters [data-testid="stSelectbox"], .st-key-sr_filters [data-baseweb="select"]{width:100% !important;
    max-width:none !important;min-width:0 !important;}
/* search box fills its (wider) column instead of stopping at a fixed width */
.st-key-sr_search, .st-key-sr_search [data-testid="stTextInput"], .st-key-sr_search [data-testid="stTextInputRootElement"],
.st-key-sr_search [data-baseweb="input"], .st-key-sr_search [data-baseweb="base-input"]{width:100% !important;max-width:none !important;}
/* "Filter by Cohort" label sitting above the From / To boxes (same look as the other filter labels) */
.st-key-sr_filters [data-testid="stWidgetLabel"] p, .sr-group-label{font-size:15px !important;line-height:1.4 !important;}
.sr-group-label{color:inherit;margin:0 !important;padding:0 !important;font-weight:600;}
/* "Filter by Cohort" sits right on top of From / To (no big Streamlit gap in between) */
.st-key-sr_cohort{gap:2px !important;}
.st-key-sr_cohort [data-testid="stElementContainer"]:has(.sr-group-label),
.st-key-sr_cohort [data-testid="stMarkdown"]:has(.sr-group-label),
.st-key-sr_cohort [data-testid="stMarkdownContainer"]:has(.sr-group-label){margin:0 !important;padding:0 !important;
    min-height:0 !important;}
/* Refresh Now button pushed to the right edge of the page */
.st-key-sr_refresh{display:flex !important;flex-direction:row !important;justify-content:flex-end !important;
    align-items:center;width:100% !important;}
.st-key-sr_refresh [data-testid="stElementContainer"]{width:auto !important;}
/* Table cells maintain clean single-line structure without broken letters */
.st-key-roster_scroll .roster-cell-text,
.st-key-roster_table .roster-cell-text{display:inline-flex;align-items:center;white-space:nowrap !important;overflow-wrap:normal !important;word-break:keep-all !important;line-height:1.35;}
.st-key-roster_scroll .roster-cell-id,
.st-key-roster_table .roster-cell-id{white-space:nowrap !important;overflow-wrap:normal !important;word-break:keep-all !important;min-width:85px !important;display:inline-block !important;}
/* status pills inside the roster: single line, no broken words or letters */
.st-key-roster_scroll .status-pill,
.st-key-roster_scroll [class*="status-pill"],
.st-key-roster_table .status-pill,
.st-key-roster_table [class*="status-pill"]{
    white-space:nowrap !important;line-height:1 !important;
    word-break:keep-all !important;
    height:26px !important;min-height:26px !important;
    padding:0 11px !important;width:auto !important;max-width:none !important;
    text-align:center;display:inline-flex !important;flex-wrap:nowrap !important;align-items:center !important;justify-content:center !important;box-sizing:border-box;}
/* RISK column pill */
.sr-risk-pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;
    letter-spacing:.03em;border:1px solid #FECACA;background:#FEF2F2;color:#B91C1C;white-space:nowrap;cursor:help;}
html[data-eo-theme="dark"] .sr-risk-pill{background:rgba(239,68,68,.14);color:#FCA5A5;border-color:rgba(239,68,68,.3);}
.sr-risk-none{color:#9CA3AF;}

/* ---- MOBILE card list (shown only at <= 640px) ---- */
.st-key-sr_mobile_cards { display: none; }
.sr-mc {
  background: var(--roster-cell-bg, transparent);
  border: 1px solid var(--roster-th-border, #E5E7EB);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.sr-mc-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--roster-th-border, #E5E7EB);
}
.sr-mc-name {
  font-size: 16px;
  font-weight: 700;
  color: #2563EB !important;
  text-decoration: none !important;
  line-height: 1.3;
  word-break: keep-all;
}
.sr-mc-name:hover { text-decoration: underline !important; }
html[data-eo-theme="dark"] .sr-mc-name { color: #60A5FA !important; }
.sr-mc-id   { font-family: monospace; font-size: 12px; color: var(--roster-cell-id, #64748B); white-space: nowrap; }
.sr-mc-row  { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; line-height: 1.4; }
.sr-mc-label { color: var(--roster-th-color, #64748B); font-weight: 600; text-transform: uppercase;
               letter-spacing: .05em; font-size: 11px; }
.sr-mc-value { color: var(--roster-cell-text, #334155); text-align: right; word-break: keep-all; }
.sr-mc-pills {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0 4px 0;
  border-top: 1px solid var(--roster-th-border, #E5E7EB);
}
.sr-mc-pill-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.sr-mc-pill-label {
  font-size: 12px;
  color: var(--roster-th-color, #64748B);
  font-weight: 600;
  word-break: keep-all;
}
.sr-mc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--roster-th-border, #E5E7EB);
}

/* Turn mobile cards ON and desktop table OFF on mobile phones <= 640px */
@media (max-width: 640px) {
  .st-key-roster_table { display: none !important; }
  .st-key-sr_mobile_cards { display: block !important; }
}
@media (min-width: 641px) {
  .st-key-roster_table { display: block !important; }
  .st-key-sr_mobile_cards { display: none !important; }
}

/* Enterprise table scroll wrapper (desktop, tablet, landscape mobile) */
.st-key-roster_table {
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch !important;
  width: 100% !important;
}
.st-key-roster_table [data-testid="stHorizontalBlock"],
.st-key-roster_table .roster-th-divider,
.st-key-roster_table .roster-row-divider,
.st-key-roster_table .st-key-roster_scroll,
.st-key-roster_table .st-key-roster_scroll > div,
.st-key-roster_table [data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-roster_scroll) {
  min-width: 1100px !important;
}
.st-key-roster_table .st-key-roster_scroll {
  overflow-x: hidden !important;
}
.st-key-roster_table [data-testid="stHorizontalBlock"] {
  gap: 12px !important;
  column-gap: 12px !important;
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: flex-end !important;
  min-width: 1100px !important;
}
.st-key-roster_table [data-testid="stColumn"],
.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
  display: flex !important;
  flex-direction: column !important;
  width: auto !important;
  min-width: 0 !important;
  flex: var(--column-flex, 1 1 0%) !important;
}
.st-key-roster_table .roster-th {
  font-size: 11.5px !important;
  font-weight: 600 !important;
  letter-spacing: .02em !important;
  text-transform: uppercase !important;
  color: var(--roster-th-color, #64748B);
  white-space: normal !important;
  word-break: keep-all !important;
  overflow-wrap: normal !important;
  line-height: 1.25 !important;
  display: block !important;
}
</style>""",
    unsafe_allow_html=True,
)

HEADER_CSS = """<style>
/* ---- page header: copied from the Executive Overview header ---- */
.stApp{--sr-h-text:#0F172A; --sr-h-label:#4B5563; --sr-h-border:#E5E7EB;}
html[data-eo-theme="dark"] .stApp{--sr-h-text:#F1F5F9; --sr-h-label:#94A3B8; --sr-h-border:#263044;}
.sr-title{font-size:2.75rem !important;font-weight:700 !important;line-height:1.15 !important;color:var(--sr-h-text) !important;
        letter-spacing:-.01em;margin:0 !important;padding:0 !important;opacity:1 !important;}
/* title + caption stack on top of each other */
.sr-head{display:block !important;width:100%;}
.sr-head .sr-title,.sr-head .sr-caption{display:block !important;width:100%;}
/* caption under the title */
.sr-caption{font-size:14px !important;line-height:1.5 !important;color:var(--sr-h-label) !important;
        margin:4px 0 0 0 !important;padding:0 !important;opacity:1 !important;}
/* Roster column headers: allows clean 2-line headers */
.roster-th{white-space:normal !important;word-break:keep-all !important;overflow-wrap:normal !important;line-height:1.25 !important;
    display:block !important;font-size:11.5px !important;font-weight:600 !important;text-transform:uppercase !important;}
/* line under the whole header row */
.st-key-sr_top{border-bottom:1px solid var(--sr-h-border);padding-bottom:10px;}
.st-key-sr_top [data-testid="stElementContainer"]:has(.sr-title),
.st-key-sr_top [data-testid="stMarkdown"]:has(.sr-title),
.st-key-sr_top [data-testid="stMarkdownContainer"]:has(.sr-title){margin:0 !important;padding:0 !important;}

/* Tablet & Mobile responsive adjustments */
@media (max-width: 1150px) {
  .sr-title { font-size: 2.0rem !important; }
  .st-key-sr_filters [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap: 12px !important;
  }
  .st-key-sr_filters [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 12px) !important;
    min-width: 180px !important;
  }
}
@media (max-width: 768px) {
  .sr-title { font-size: 1.6rem !important; }
}
@media (max-width: 600px) {
  .st-key-sr_filters [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }
}

/* Tablet & Mobile responsive table scroll wrapper - never force columns to break letters */
.st-key-roster_table,
.st-key-sr_table_wrap {
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch !important;
  width: 100% !important;
}
.st-key-roster_table [data-testid="stHorizontalBlock"],
.st-key-roster_table .roster-th-divider,
.st-key-roster_table .roster-row-divider,
.st-key-roster_table .st-key-roster_scroll,
.st-key-roster_table .st-key-roster_scroll > div,
.st-key-roster_table [data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-roster_scroll),
.st-key-sr_table_wrap [data-testid="stHorizontalBlock"],
.st-key-sr_table_wrap .roster-th-divider,
.st-key-sr_table_wrap .roster-row-divider,
.st-key-sr_table_wrap .st-key-roster_scroll,
.st-key-sr_table_wrap .st-key-roster_scroll > div,
.st-key-sr_table_wrap [data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-roster_scroll) {
  min-width: 1100px !important;
}
.st-key-roster_table .st-key-roster_scroll,
.st-key-sr_table_wrap .st-key-roster_scroll {
  overflow-x: hidden !important;
}
.st-key-roster_table [data-testid="stHorizontalBlock"],
.st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
  gap: 12px !important;
  column-gap: 12px !important;
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: flex-end !important;
}
.st-key-roster_table [data-testid="stColumn"],
.st-key-sr_table_wrap [data-testid="stColumn"],
.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
.st-key-sr_table_wrap div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
  display: flex !important;
  flex-direction: column !important;
  width: auto !important;
  min-width: 0 !important;
  flex: var(--column-flex, 1 1 0%) !important;
}
.st-key-roster_table .roster-th,
.st-key-sr_table_wrap .roster-th {
  white-space: normal !important;
  word-break: keep-all !important;
  overflow-wrap: normal !important;
  line-height: 1.25 !important;
  font-size: 11.5px !important;
}
/* ============================================================
   TABLET & LANDSCAPE (<= 1150px): smooth sideways scroll without text wrapping
   ============================================================ */
@media (max-width: 1150px) {
  .roster-th {
    white-space: normal !important;
    word-break: keep-all !important;
    overflow-wrap: normal !important;
    line-height: 1.25 !important;
    display: block !important;
    font-size: 11.5px !important;
  }
  .st-key-roster_table [data-testid="stHorizontalBlock"],
  .st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
    align-items: flex-end !important;
    gap: 10px !important;
    column-gap: 10px !important;
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
  }
  .st-key-roster_table,
  .st-key-sr_table_wrap {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
    width: 100% !important;
    padding-bottom: 6px !important;
  }
  .st-key-roster_table > [data-testid="stVerticalBlock"],
  .st-key-roster_table [data-testid="stHorizontalBlock"],
  .st-key-sr_table_wrap > [data-testid="stVerticalBlock"],
  .st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
    min-width: 1100px !important;
  }
  .st-key-roster_scroll .roster-cell-text,
  .st-key-roster_scroll .roster-cell-id {
    white-space: nowrap !important;
    word-break: keep-all !important;
    overflow-wrap: normal !important;
    line-height: 1.3 !important;
  }
}

/* ============================================================
   MOBILE (<= 640px): one card per student, no wide grid at all
   ============================================================ */
@media (max-width: 640px) {
  /* Title / caption shrink so they fit one screen width */
  .sr-title { font-size: 1.55rem !important; line-height: 1.2 !important; }
  .sr-caption { font-size: 13px !important; }

  /* Filters stack vertically instead of sitting side by side */
  .st-key-sr_filters [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 10px !important;
    align-items: stretch !important;
  }
  .st-key-sr_filters [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 100% !important;
  }
  /* Cohort From / To always side by side, even on a phone */
  .st-key-sr_filters [data-testid="stColumn"] [data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
  }

  /* Hide the wide desktop grid (headers + row dividers) - we render cards instead */
  .st-key-sr_table_wrap { display: none !important; }

  /* Refresh Now button full width on mobile */
  .st-key-sr_refresh { justify-content: stretch !important; }
  .st-key-sr_refresh button { width: 100% !important; }
}
</style>"""
 
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)
 
# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to access the student roster.")
    st.stop()
 
# ---------------------------------------------------------------
# Program selection — includes "All Programs"
# Program Chairs are LOCKED to their assigned program (Users.CurrentProgramID)
# and cannot switch, cannot pick "All Programs", and cannot create programs.
# ---------------------------------------------------------------
user = st.session_state.get("user", {})
role = user.get("role")
# login.py stores the user dict with lowercase keys, so try both spellings
user_id = user.get("userid") or user.get("UserID")
IS_PROGRAM_CHAIR = (role == "Program_Chair")

if IS_PROGRAM_CHAIR:
    # Locked view: force the chair's assigned program into session state every run
    assigned = get_user_program(user_id)
    if not assigned:
        st.warning(
            "⏳ You don't have a program assigned yet. Contact IT/Admin to set your "
            "CurrentProgramID before using the Student Roster."
        )
        st.stop()
    # Always overwrite — this also defeats a stale session value from before the assignment
    st.session_state["active_program_id"] = assigned["ProgramID"]
    st.session_state["active_program_code"] = assigned["ProgramCode"]
    st.session_state["active_program_set"] = True
    st.info(
        f"🔒 You are assigned to **{assigned['ProgramCode']} — {assigned['ProgramName']}**. "
        "As a Program Chair, the Student Roster is scoped to this program."
    )
else:
    with st.expander("Active Program", expanded=not st.session_state.get("active_program_set")):
        programs = cached_programs()
        ALL_LABEL = "All Programs"
        options = {ALL_LABEL: None}
        for p in programs:
            options[f"{p['ProgramCode']} — {p['ProgramName']}"] = p["ProgramID"]

        # default index = the currently-active program (or All Programs)
        current_id = st.session_state.get("active_program_id")
        current_code = st.session_state.get("active_program_code")
        default_idx = 0
        if current_code == ALL_LABEL:
            default_idx = 0
        elif current_id is not None:
            for i, label in enumerate(options.keys()):
                if options[label] == current_id:
                    default_idx = i
                    break

        selected_label = st.selectbox(
            "Select program",
            list(options.keys()),
            index=default_idx,
            key="program_select",
        )
        if st.button("Set Active Program"):
            pid = options[selected_label]
            st.session_state["active_program_id"] = pid
            st.session_state["active_program_code"] = ALL_LABEL if pid is None else selected_label.split(" — ")[0]
            st.session_state["active_program_set"] = True
            if pid is not None:
                set_user_program(user_id, pid)          # ← was user.get("UserID")
            st.success(f"Active program set to {selected_label}.")
            st.rerun()

        with st.form("create_program_form"):
            st.write("**Create New Program**")
            code = st.text_input("Program Code (e.g., BIA)")
            name = st.text_input("Program Name (e.g., BS Business Intelligence)")
            if st.form_submit_button("Create Program"):
                require_edit()
                if not code or not name:
                    st.warning("Please enter both Program Code and Name.")
                else:
                    ok, result = create_program(code.strip().upper(), name.strip())
                    if ok:
                        st.cache_data.clear()
                        st.session_state["active_program_id"] = result
                        st.session_state["active_program_code"] = code.strip().upper()
                        st.session_state["active_program_set"] = True
                        set_user_program(user_id, result)
                        st.success(f"Created **{code}** and set as active.")
                        st.rerun()
                    else:
                        st.error(f"Could not create program: {result}")
 
 
# Only block the page when the user has never picked a program (None means "All Programs" is valid)
if not st.session_state.get("active_program_set"):
    st.warning("⏳ No active program has been set. Please pick one from the Active Program panel above.")
    st.stop()
 
active_program_id = st.session_state.get("active_program_id")   # may be None = All Programs
active_code = st.session_state.get("active_program_code", "")

# Student Profile only opens after a program has been picked here.
st.session_state["roster_program_id"] = active_program_id
st.session_state["roster_program_code"] = active_code
 
# ---------------------------------------------------------------
# Session state
# ---------------------------------------------------------------
active_login_id = st.session_state.get("session_id", None)
 
if active_login_id:
    retry_count = cached_retry_count(active_login_id)
    if retry_count > 1:
        st.warning(
            f"Warning: Repeated sync failures detected for your session "
            f"({retry_count} attempts). Check Admin logs."
        )
 
# ---------------------------------------------------------------
# US-23: Faculty/Program Advisor sees ONLY their own advisees.
# ---------------------------------------------------------------
my_adviser_name = None
is_advisor_view = (role == "Faculty_Advisor")   # the role name login.py stores

if is_advisor_view:
    my_adviser_name = cached_adviser_name(user_id)


# ---------------------------------------------------------------
# US-37: advisee alerts - a bell next to the page title (red dot = new alerts); clicking it opens the list.
# Alerts = advisees who moved to Cancelled / Incomplete / Conditionally Enrolled. Logic: advisee_alerts.py,
# stored in Alert_Logs.
# ---------------------------------------------------------------
from advisee_alerts import scan_status_changes, my_alerts, acknowledge, BAD_STATUSES, LOOKBACK_DAYS

MY_ALERTS_CSS = """<style>
/* the bell: top right of the page title */
.st-key-sr_top{position:relative;}
.st-key-ma_bell{position:absolute !important;top:4px;right:0;width:auto !important;z-index:5;overflow:visible !important;}
.st-key-ma_bell button{width:48px;height:48px;min-height:48px;padding:0;border-radius:14px;position:relative;
        overflow:visible;display:flex;align-items:center;justify-content:center;}
.st-key-ma_bell button p{font-size:28px;line-height:1;margin:0;}
.st-key-ma_bell button span[role="img"]{font-variation-settings:"FILL" 0, "wght" 400;}   /* outline bell */
.st-key-ma_bell button div[aria-hidden="true"]{display:none;}   /* no open/close arrow next to the bell */
.st-key-sr_top:has(.st-key-ma_bell) .sr-head{padding-right:60px;}   /* keep the title clear of the bell */
/* the panel that opens */
[data-testid="stPopoverBody"]:has(.ma-head){width:min(760px, 92vw) !important;max-width:92vw !important;
        padding:20px 22px !important;}
/* the panel is drawn outside the page, so it gets the roster's colours itself (same values as HEADER_CSS) */
[data-testid="stPopoverBody"]:has(.ma-head){--sr-h-text:#0F172A; --sr-h-label:#4B5563; --sr-h-border:#E5E7EB;}
html[data-eo-theme="dark"] [data-testid="stPopoverBody"]:has(.ma-head){--sr-h-text:#F1F5F9; --sr-h-label:#94A3B8;
        --sr-h-border:#263044;}
.st-key-ma_top{padding-bottom:14px;margin-bottom:6px;border-bottom:1px solid var(--sr-h-border);}
.ma-head{display:block;width:100%;}
.ma-mid{display:block;width:100%;}
.ma-title{font-size:18px;font-weight:700;color:var(--sr-h-text);display:flex;align-items:center;gap:10px;}
.ma-count{font-size:12px;font-weight:700;color:#B91B21;background:#FEF2F2;border:1px solid #FECACA;
        border-radius:999px;padding:2px 9px;}
html[data-eo-theme="dark"] .ma-count{color:#FCA5A5;background:rgba(185,27,33,.18);border-color:rgba(185,27,33,.4);}
.ma-desc{font-size:13px;color:var(--sr-h-label);line-height:1.5;}
/* one box per student */
[class*="st-key-ma_row_"]{border:1px solid var(--sr-h-border);border-radius:12px;padding:12px 16px;margin-top:4px;}
[class*="st-key-ma_row_"] [data-testid="stColumn"]:not(:first-child){border-left:1px solid var(--sr-h-border);
        padding-left:16px;}
.ma-name{font-size:15px;font-weight:600;color:var(--sr-h-text) !important;line-height:1.35;
        text-decoration:none !important;}
.ma-name:hover{text-decoration:underline !important;}
/* inside the panel: no extra space under text blocks, so everything centres exactly */
[data-testid="stPopoverBody"]:has(.ma-head) [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
.st-key-ma_show_seen{display:flex;justify-content:flex-end;width:100%;}
.st-key-ma_show_seen label{margin-left:auto;margin-right:16px;}   /* lines up with the Acknowledge buttons */
.ma-sn{font-size:12px;color:var(--sr-h-label);margin-top:2px;}
.ma-change{font-size:14px;color:var(--sr-h-text);line-height:1.4;}
.ma-bad{color:#B91B21;font-weight:700;}
html[data-eo-theme="dark"] .ma-bad{color:#FCA5A5;}
.ma-when{font-size:12px;color:var(--sr-h-label);margin-top:3px;}
.ma-empty{font-size:14px;color:var(--sr-h-label);padding:6px 0;}
/* phones: the 3 parts of a box stack, so the dividers go on top instead of the left */
@media (max-width: 640px) {
  [class*="st-key-ma_row_"] [data-testid="stColumn"]:not(:first-child){border-left:none;padding-left:0;
          border-top:1px solid var(--sr-h-border);padding-top:8px;}
}
</style>"""
MA_RED_DOT_CSS = """<style>
.st-key-ma_bell button::after{content:"";position:absolute;top:-6px;right:-6px;width:14px;height:14px;
        border-radius:50%;background:#DC2626;box-shadow:0 0 0 2px var(--background-color, #FFFFFF);}
</style>"""
MA_WIDTHS = [1.6, 2.4, 1.1]   # Name + ID | What changed + when | Acknowledge


@st.cache_data(ttl=60, show_spinner=False)
def cached_status_scan():
    """Turn new status changes into alerts (at most once a minute, shared by every adviser)."""
    return scan_status_changes()


def _ma_when(value):
    try:
        return f"{value:%b %d, %Y} · {value.hour % 12 or 12}:{value:%M %p}"
    except Exception:
        return str(value or "")


def _ma_change_html(change):
    """'Comprehensive Exam changed from In-Progress to Incomplete on ...' -> the bad status in red."""
    text = html.escape(change.split(" on ")[0])
    for bad in BAD_STATUSES:
        text = text.replace(f"to {html.escape(bad)}", f'to <span class="ma-bad">{html.escape(bad)}</span>')
    return text


@st.fragment
def my_alerts_bell():
    try:
        cached_status_scan()
        new_alerts = my_alerts(user_id)
        show_seen = st.session_state.get("ma_show_seen", False)
        alerts = my_alerts(user_id, acknowledged=True) if show_seen else new_alerts
    except Exception as e:
        st.warning(f"Couldn't load your alerts: {e}")
        return
    st.markdown(MY_ALERTS_CSS + (MA_RED_DOT_CSS if new_alerts else ""), unsafe_allow_html=True)

    with st.popover(":material/notifications:", key="ma_bell"):
        with st.container(key="ma_top"):
            # "My Alerts" and the switch on one line (switch at the right edge), the description underneath
            c_head, c_toggle = st.columns([3, 1.3], vertical_alignment="center")
            count = f'<span class="ma-count">{len(new_alerts)} new</span>' if new_alerts else ""
            c_head.markdown(f'<div class="ma-head"><div class="ma-title">My Alerts {count}</div></div>',
                            unsafe_allow_html=True)
            c_toggle.toggle("Show acknowledged", key="ma_show_seen")
            st.markdown(f'<div class="ma-head"><div class="ma-desc">Your advisees who moved to '
                        f'{", ".join(BAD_STATUSES[:-1])} or {BAD_STATUSES[-1]} in the last {LOOKBACK_DAYS} days.'
                        '</div></div>', unsafe_allow_html=True)

        if not alerts:
            st.markdown('<div class="ma-empty">' + ("No acknowledged alerts yet." if show_seen else
                        "No new alerts. You're all caught up.") + '</div>', unsafe_allow_html=True)
            return

        for a in alerts:
            sn = str(a["StudentNumber"])
            name = a["Student"].rsplit(" (", 1)[0] or sn
            with st.container(key=f"ma_row_{a['AlertID']}"):
                c_student, c_change, c_ack = st.columns(MA_WIDTHS, vertical_alignment="center")
                c_student.markdown(
                    f'<div class="ma-mid"><a class="ma-name" href="student_profile?student_id={html.escape(sn)}" '
                    f'target="_self">{html.escape(name)}</a><div class="ma-sn">{html.escape(sn)}</div></div>',
                    unsafe_allow_html=True)
                c_change.markdown(f'<div class="ma-mid"><div class="ma-change">{_ma_change_html(a["Change"])}</div>'
                                  f'<div class="ma-when">{_ma_when(a["CreatedAt"])}</div></div>',
                                  unsafe_allow_html=True)
                if show_seen:
                    c_ack.markdown(f'<div class="ma-when">Acknowledged<br>{_ma_when(a["AcknowledgedAt"])}</div>',
                                   unsafe_allow_html=True)
                elif c_ack.button("Acknowledge", key=f"ma_ack_{a['AlertID']}", use_container_width=True):
                    acknowledge(a["AlertID"], user_id)
                    st.rerun(scope="fragment")


# Header & Sync Controls
st.markdown(HEADER_CSS, unsafe_allow_html=True)
with st.container(key="sr_top"):
    with st.container():
        st.markdown(
            f'<div class="sr-head"><div class="sr-title">Student Roster — {html.escape(str(active_code))}</div>'
            '<div class="sr-caption">Search, filter, and sort students in this program, '
            'and open any student\'s profile.</div></div>',
            unsafe_allow_html=True,
        )

    if is_advisor_view and my_adviser_name:
        my_alerts_bell()   # US-37
 
cohort_choice = "All Cohorts"


def _sync_cohort_range(changed_key, other_key):
    """Keeps the From / To cohort boxes consistent (runs when either one changes)."""
    new_value = st.session_state.get(changed_key, "All Cohorts")
    other_value = st.session_state.get(other_key, "All Cohorts")
    if new_value == "All Cohorts":
        st.session_state[other_key] = "All Cohorts"
    elif other_value == "All Cohorts":
        st.session_state[other_key] = new_value


# Displays student roster in table format
try:
    df = cached_roster(active_program_id)
 
    if is_advisor_view:
        if my_adviser_name is None:
            st.info(
                "You don't have an adviser profile linked to your account yet. "
                "Contact your Program Chair or IT/Admin to get set up."
            )
            df = df.iloc[0:0]
        else:
            df = df[df["Adviser"].fillna("").str.split(", ").apply(lambda names: my_adviser_name in names)]
 
    if not df.empty:
        # ----------------- Clean Filter & Search Rhythm -----------------
        filters_box = st.container(key="sr_filters")
        if is_advisor_view:
            col_search, col_cohort, col_sort = filters_box.columns([3.5, 3, 1.8], vertical_alignment="bottom")
            adviser_choice = None
        else:
            col_search, col_adviser, col_cohort, col_sort = filters_box.columns([3, 1.8, 3, 1.8],
                                                                              vertical_alignment="bottom")

        with col_search:
            search_query = st.text_input(
                "Search Student",
                placeholder="Student name or ID...",
                label_visibility="visible",
                key="sr_search",
            )

        if not is_advisor_view:
            with col_adviser:
                adviser_names = {n for v in df["Adviser"].dropna() for n in str(v).split(", ") if n}
                available_advisers = ["All Advisers"] + sorted(adviser_names)
                adviser_choice = st.selectbox("Filter by Adviser", available_advisers)

        with col_cohort:
            cohort_list = sorted(cached_cohorts(active_program_id), key=cohort_sort_key)
            cohort_options = ["All Cohorts"] + cohort_list
            for _k in ("sr_cohort_from", "sr_cohort_to"):
                if st.session_state.get(_k) not in cohort_options:
                    st.session_state[_k] = "All Cohorts"
            c_from, c_to = st.columns(2)
            with c_from:
                cohort_from = st.selectbox("Filter by Cohort -- From", cohort_options, key="sr_cohort_from",
                                           on_change=_sync_cohort_range, args=("sr_cohort_from", "sr_cohort_to"))
            with c_to:
                cohort_to = st.selectbox("Filter by Cohort -- To", cohort_options, key="sr_cohort_to",
                                         on_change=_sync_cohort_range, args=("sr_cohort_to", "sr_cohort_from"))

        with col_sort:
            sort_map = {
                "Student Number": "StudentNumber",
                "Student Name": "Student",
                "Cohort": "Cohort",
                "Last Update": "LastUpdate",
            }
            sort_choice = st.selectbox("Sort by", list(sort_map.keys()))

        # Apply Filters
        df_filtered = df

        if search_query and search_query.strip():
            q = search_query.strip().lower()
            df_filtered = df_filtered[
                df_filtered["Student"].astype(str).str.lower().str.contains(q, na=False, regex=False) |
                df_filtered["StudentNumber"].astype(str).str.contains(q, na=False, regex=False)
            ]

        # cohort range (inclusive)
        lo = cohort_sort_key(cohort_from) if cohort_from != "All Cohorts" else None
        hi = cohort_sort_key(cohort_to) if cohort_to != "All Cohorts" else None
        cohort_range_invalid = bool(lo and hi and lo > hi)
        if cohort_range_invalid:
            df_filtered = df_filtered.iloc[0:0]
        elif lo or hi:
            keys = df_filtered["Cohort"].map(cohort_sort_key)
            keep = pd.Series(True, index=df_filtered.index)
            if lo:
                keep &= keys >= lo
            if hi:
                keep &= keys <= hi
            df_filtered = df_filtered[keep & df_filtered["Cohort"].notna()]

        # what the yellow header bar shows for the cohort
        if cohort_from == "All Cohorts" and cohort_to == "All Cohorts":
            cohort_choice = "All Cohorts"
        elif cohort_to == "All Cohorts":
            cohort_choice = f"{cohort_from} onward"
        elif cohort_from == "All Cohorts":
            cohort_choice = f"Up to {cohort_to}"
        elif cohort_from == cohort_to:
            cohort_choice = cohort_from
        else:
            cohort_choice = f"{cohort_from} – {cohort_to}"

        if not is_advisor_view and adviser_choice and adviser_choice != "All Advisers":
            df_filtered = df_filtered[
                df_filtered["Adviser"].fillna("").str.split(", ").apply(lambda names: adviser_choice in names)
            ]

        sort_col = sort_map[sort_choice]
        if sort_col == "Cohort":
            df_filtered = df_filtered.sort_values(by="Cohort", key=lambda col: col.map(
                lambda c: cohort_sort_key(c) if pd.notna(c) else (9999, 9, "")))
        else:
            df_filtered = df_filtered.sort_values(
                by=sort_col, ascending=(sort_col != "LastUpdate"), na_position="last"
            )

        if cohort_range_invalid:
            st.warning(
                f"Invalid cohort range: 'From' ({cohort_from}) comes after 'To' ({cohort_to}). "
                "Pick a From cohort that is the same as or earlier than the To cohort."
            )
        elif df_filtered.empty:
            st.info("No students match these filters.")

        # ----------------- Enterprise Roster Grid -----------------
        show_program_col = active_program_id is None   # "All Programs" -> show the PROGRAM column
        if show_program_col:
            # 10 columns: ID | Student | Program | Cohort | Adviser | CW | CE | CP | Last Update | Risk
            # CP is wider so "Defended for Completion" fits on one line like the other pills (same total width)
            col_widths = [0.9, 1.4, 0.7, 0.8, 1.6, 1.2, 1.2, 1.8, 1.0, 0.7]
        else:
            # 9 columns: ID | Student | Cohort | Adviser | CW | CE | CP | Last Update | Risk
            col_widths = [0.9, 1.5, 0.8, 1.6, 1.2, 1.2, 1.8, 1.0, 0.7]

        try:
            risk_flags = get_risk_flags(active_program_id)
        except Exception:
            risk_flags = {}

        # The table scrolls, so all matching rows are drawn (no paging)
        page_df = df_filtered

        stage_labels = cached_stage_labels(active_program_id)
        if show_program_col:
            header_labels = [
                "STUDENT ID", "STUDENT", "PROGRAM", "COHORT", "ADVISER",
                stage_labels["Coursework"].upper(), stage_labels["CompExam"].upper(),
                stage_labels["Capstone"].upper(), "LAST UPDATE", "RISK"
            ]
        else:
            header_labels = [
                "STUDENT ID", "STUDENT", "COHORT", "ADVISER",
                stage_labels["Coursework"].upper(), stage_labels["CompExam"].upper(),
                stage_labels["Capstone"].upper(), "LAST UPDATE", "RISK"
            ]
        table_box = st.container(key="roster_table")   # header + rows live in one box so they scroll sideways together
        header_cols = table_box.columns(col_widths, vertical_alignment="center")
        for col, label in zip(header_cols, header_labels):
            col.markdown(f'<div class="roster-th">{split_label_two_lines(label)}</div>', unsafe_allow_html=True)
        table_box.markdown('<div class="roster-th-divider"></div>', unsafe_allow_html=True)
 
        if df_filtered.empty:
            st.info("No students match the current filters.")
        else:
            scroll_kwargs = {"height": ROW_HEIGHT_PX * ROWS_VISIBLE} if len(page_df) > ROWS_VISIBLE else {}
            with table_box.container(border=False, key="roster_scroll", **scroll_kwargs):
                for row in page_df.to_dict("records"):
                    s_id = str(row.get("StudentNumber", ""))
                    s_name = str(row.get("Student", "Unknown"))
                    p_code = str(row.get("ProgramCode") or "—")
                    cohort = str(row.get("Cohort", "N/A"))
                    adviser_raw = row.get("Adviser")
                    adviser = ("<br>".join(html.escape(a) for a in str(adviser_raw).split(", ") if a)
                               if pd.notna(adviser_raw) and str(adviser_raw).strip() else "None Assigned")
 
                    cw_pill = render_status_pill(row.get("CourseworkStatus"))
                    ce_pill = render_status_pill(row.get("CompExamStatus"))
                    cp_pill = render_status_pill(row.get("CapstoneStatus"))

                    r_cols = st.columns(col_widths, vertical_alignment="center")
                    idx = 0
                    r_cols[idx].markdown(
                        f'<span class="roster-cell-id">{s_id}</span>',
                        unsafe_allow_html=True
                    ); idx += 1
                    r_cols[idx].page_link(
                        "dashboard_views/student_profile.py",
                        label=s_name,
                        query_params={"student_id": s_id}
                    ); idx += 1
                    if show_program_col:
                        r_cols[idx].markdown(
                            f'<span class="roster-cell-text">{html.escape(p_code)}</span>',
                            unsafe_allow_html=True
                        ); idx += 1
                    r_cols[idx].markdown(
                        f'<span class="roster-cell-text">{cohort}</span>',
                        unsafe_allow_html=True
                    ); idx += 1
                    r_cols[idx].markdown(
                        f'<span class="roster-cell-text">{adviser}</span>',
                        unsafe_allow_html=True
                    ); idx += 1
                    r_cols[idx].markdown(cw_pill, unsafe_allow_html=True); idx += 1
                    r_cols[idx].markdown(ce_pill, unsafe_allow_html=True); idx += 1
                    r_cols[idx].markdown(cp_pill, unsafe_allow_html=True); idx += 1
                    last_upd = row.get("LastUpdate")
                    last_txt = pd.to_datetime(last_upd).strftime("%b %d, %Y") if pd.notna(last_upd) else "—"
                    r_cols[idx].markdown(
                        f'<span class="roster-cell-text">{last_txt}</span>',
                        unsafe_allow_html=True
                    ); idx += 1
                    reason = risk_flags.get(s_id)
                    r_cols[idx].markdown(
                        f'<span class="sr-risk-pill" title="{html.escape(reason)}">AT RISK</span>'
                        if reason is not None else '<span class="sr-risk-none">—</span>',
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        '<div class="roster-row-divider"></div>',
                        unsafe_allow_html=True
                    )
        # ---- MOBILE VIEW (<= 640px): one card per student ----
        # Rendered always; the CSS above hides it on wider screens and hides the desktop grid on phones.
        with st.container(key="sr_mobile_cards"):
            for row in page_df.to_dict("records"):
                s_id = str(row.get("StudentNumber", ""))
                s_name = str(row.get("Student", "Unknown"))
                p_code = str(row.get("ProgramCode") or "—")
                cohort = str(row.get("Cohort", "N/A"))
                adviser_raw = row.get("Adviser")
                adviser = (", ".join(str(a) for a in str(adviser_raw).split(", ") if a)
                           if pd.notna(adviser_raw) and str(adviser_raw).strip() else "None Assigned")

                cw_pill = render_status_pill(row.get("CourseworkStatus"))
                ce_pill = render_status_pill(row.get("CompExamStatus"))
                cp_pill = render_status_pill(row.get("CapstoneStatus"))

                last_upd = row.get("LastUpdate")
                last_txt = pd.to_datetime(last_upd).strftime("%b %d, %Y") if pd.notna(last_upd) else "—"
                reason = risk_flags.get(s_id)
                risk_html = (f'<span class="sr-risk-pill">AT RISK</span>'
                             if reason is not None else
                             '<span class="sr-risk-none">—</span>')
                program_html = (f'<div class="sr-mc-row"><span class="sr-mc-label">Program</span>'
                                f'<span class="sr-mc-value">{html.escape(p_code)}</span></div>'
                                if show_program_col else "")

                st.markdown(
                    f"""
<div class="sr-mc">
  <div class="sr-mc-head">
    <a class="sr-mc-name" href="student_profile?student_id={html.escape(s_id)}" target="_self">{html.escape(s_name)}</a>
    <div class="sr-mc-id">{html.escape(s_id)}</div>
  </div>
  {program_html}
  <div class="sr-mc-row"><span class="sr-mc-label">Cohort</span><span class="sr-mc-value">{html.escape(cohort)}</span></div>
  <div class="sr-mc-row"><span class="sr-mc-label">Adviser</span><span class="sr-mc-value">{html.escape(adviser)}</span></div>
  <div class="sr-mc-pills">
    <div class="sr-mc-pill-block"><span class="sr-mc-pill-label">{html.escape(stage_labels['Coursework'])}</span>{cw_pill}</div>
    <div class="sr-mc-pill-block"><span class="sr-mc-pill-label">{html.escape(stage_labels['CompExam'])}</span>{ce_pill}</div>
    <div class="sr-mc-pill-block"><span class="sr-mc-pill-label">{html.escape(stage_labels['Capstone'])}</span>{cp_pill}</div>
  </div>
  <div class="sr-mc-foot">
    <span class="sr-mc-label">Last Update</span>
    <span class="sr-mc-value">{html.escape(last_txt)}</span>
    {risk_html}
  </div>
</div>
""",
                    unsafe_allow_html=True,
                )
        st.caption(
            f"Showing {len(df_filtered)} of {len(df)} students. "
            f"Click any student name to view their profile."
        )
    else:
        if is_advisor_view and my_adviser_name is not None:
            st.info(
                f"You currently have no advisees assigned in {active_code}. "
                f"Once a Program Chair assigns students to you, they'll appear here."
            )
        elif not is_advisor_view:
            st.info(f"No students are currently tagged under {active_code}.")
 
except Exception as e:
    if "mapping" in str(e).lower():
        st.error(f"Configuration Error: The Student Roster cannot load because field mappings are invalid. "
                 f"Please check the Admin Configuration page. ({e})")
    else:
        st.error(f"The Student Roster couldn't load: {e}")

# Yellow header bar
set_header_context(program=active_program_id, cohort=cohort_choice)

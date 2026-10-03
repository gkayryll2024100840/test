# STUDENT ROSTER.PY
# UPDATED: 9/30/2026
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
.st-key-sr_table_wrap .roster-cell-text{display:inline-flex;align-items:center;white-space:nowrap !important;overflow-wrap:normal !important;word-break:keep-all !important;line-height:1.35;}
.st-key-roster_scroll .roster-cell-id,
.st-key-sr_table_wrap .roster-cell-id{white-space:nowrap !important;overflow-wrap:normal !important;word-break:keep-all !important;min-width:85px !important;display:inline-block !important;}
/* status pills inside the roster: single line, no broken words or letters */
.st-key-roster_scroll .status-pill,
.st-key-roster_scroll [class*="status-pill"],
.st-key-sr_table_wrap .status-pill,
.st-key-sr_table_wrap [class*="status-pill"]{
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
.st-key-sr_mobile_cards { display: none; }   /* hidden by default; the mobile @media block turns it on */

.sr-mc {
  background: var(--roster-cell-bg, transparent);
  border: 1px solid var(--roster-th-border);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sr-mc-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--roster-th-border);
}
.sr-mc-name { font-size: 16px; font-weight: 700; color: var(--roster-cell-text); line-height: 1.3; word-break: keep-all; }
.sr-mc-id   { font-family: monospace; font-size: 12px; color: var(--roster-cell-id); white-space: nowrap; }
.sr-mc-row  { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; line-height: 1.4; }
.sr-mc-label { color: var(--roster-th-color); font-weight: 600; text-transform: uppercase;
               letter-spacing: .05em; font-size: 11px; }
.sr-mc-value { color: var(--roster-cell-text); text-align: right; word-break: keep-all; }
.sr-mc-pills {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0 4px 0;
  border-top: 1px solid var(--roster-th-border);
}
.sr-mc-pill-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.sr-mc-pill-label {
  font-size: 12px;
  color: var(--roster-th-color);
  font-weight: 600;
  word-break: keep-all;
}
.sr-mc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--roster-th-border);
}

/* turn the card list ON and the desktop grid OFF at 640px */
@media (max-width: 640px) {
  .st-key-sr_mobile_cards { display: block !important; }
  .st-key-sr_mobile_cards .st-key-sr_mobile_cards { display: block !important; }
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
/* Roster column headers: single clean line, never wrap or split letters */
.roster-th{white-space:nowrap !important;word-break:keep-all !important;line-height:1.2 !important;
    display:inline-flex !important;align-items:center !important;}
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
.st-key-sr_table_wrap {
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch !important;
  width: 100% !important;
}
.st-key-sr_table_wrap [data-testid="stHorizontalBlock"],
.st-key-sr_table_wrap .roster-th-divider,
.st-key-sr_table_wrap .roster-row-divider,
.st-key-sr_table_wrap .st-key-roster_scroll,
.st-key-sr_table_wrap .st-key-roster_scroll > div,
.st-key-sr_table_wrap [data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-roster_scroll) {
  min-width: 1100px !important;
}
.st-key-sr_table_wrap .st-key-roster_scroll {
  overflow-x: hidden !important;
}
.st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
  gap: 12px !important;
  column-gap: 12px !important;
}
.st-key-sr_table_wrap .roster-th {
  white-space: nowrap !important;
  word-break: keep-all !important;
  overflow-wrap: normal !important;
}
/* ============================================================
   TABLET (<= 1150px): header labels wrap, table scrolls sideways
   ============================================================ */
@media (max-width: 1150px) {
  /* Allow header labels to wrap onto a second line instead of overlapping.
     Without this the "nowrap" rule above pushes them into the neighbouring column. */
  .roster-th {
    white-space: normal !important;
    word-break: keep-all !important;
    overflow-wrap: break-word !important;
    line-height: 1.15 !important;
    display: block !important;
    min-height: 28px;
  }
  /* Align the header cells at the top so a wrapped 2-line label doesn't drag the row down */
  .st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
    align-items: flex-start !important;
  }
  /* Slightly tighter gap so more of the table fits before the scroll starts */
  .st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
    gap: 8px !important;
    column-gap: 8px !important;
  }
  /* Horizontal scroll container for the whole grid.
     The inner width stays wide enough for the columns; the user scrolls to see the rest. */
  .st-key-sr_table_wrap {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
    width: 100% !important;
    padding-bottom: 6px !important;
  }
  /* Keep a sensible minimum width so column ratios still make sense */
  .st-key-sr_table_wrap > [data-testid="stVerticalBlock"],
  .st-key-sr_table_wrap [data-testid="stHorizontalBlock"] {
    min-width: 1050px !important;
  }
  /* Cells still never break a word mid-way, but wrap their content */
  .st-key-roster_scroll .roster-cell-text,
  .st-key-roster_scroll .roster-cell-id {
    white-space: normal !important;
    word-break: keep-all !important;
    overflow-wrap: break-word !important;
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
# ---------------------------------------------------------------
user = st.session_state.get("user", {})
role = user.get("role")
 
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
            set_user_program(user.get("UserID"), pid)
        st.success(f"Active program set to {selected_label}.")
        st.rerun()
 
    with st.form("create_program_form"):
        st.write("**Create New Program**")
        code = st.text_input("Program Code (e.g., BIA)")
        name = st.text_input("Program Name (e.g., BS Business Intelligence and Analytics)")
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
                    set_user_program(user.get("UserID"), result)
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

 
# ---------------------------------------------------------------
# US-23: Faculty/Program Advisor sees ONLY their own advisees.
# ---------------------------------------------------------------
my_adviser_name = None
is_advisor_view = (role == "FacultyAdvisor")
 
if is_advisor_view:
    my_adviser_name = cached_adviser_name(user.get("UserID"))
 
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
            col_widths = [1.1, 1.6, 0.7, 0.8, 1.7, 1.2, 1.2, 1.5, 1.0, 0.7]
        else:
            # 9 columns: ID | Student | Cohort | Adviser | CW | CE | CP | Last Update | Risk
            col_widths = [1.1, 1.7, 0.8, 1.7, 1.2, 1.2, 1.5, 1.0, 0.7]

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
        with st.container(key="sr_table_wrap"):
            header_cols = st.columns(col_widths, vertical_alignment="center")
            for col, label in zip(header_cols, header_labels):
                col.markdown(f'<div class="roster-th">{label}</div>', unsafe_allow_html=True)
            st.markdown('<div class="roster-th-divider"></div>', unsafe_allow_html=True)

            if df_filtered.empty:
                st.info("No students match the current filters.")
            else:
                scroll_kwargs = {"height": ROW_HEIGHT_PX * ROWS_VISIBLE} if len(page_df) > ROWS_VISIBLE else {}
                with st.container(border=False, key="roster_scroll", **scroll_kwargs):
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
    <div class="sr-mc-name">{html.escape(s_name)}</div>
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

# STUDENT ROSTER.PY 9-29-26
# STUDENT ROSTER.PY 9-28-26

import html
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
    get_my_adviser_name,   # NEW -- see db_connect_addition.py, needs to be added to db_connect.py
    get_flagged_students,  # US-26/27: time in stage + At-Risk flag (v_student_stage_flags view)
)
 
# Only import these if dashboard_views/components.py actually exists.
# If it doesn't, delete this block and the two references to it below.
from dashboard_views.components import (
    DARK_MODE_CSS,
    render_status_pill,
    set_header_context,
)
 
st.set_page_config(page_title="Student Roster", layout="wide")

# Roster list size: how many students show before you have to scroll,
# and the height of one row in px (raise/lower it if 10 rows show a bit more or less than 10).
ROWS_VISIBLE = 10
ROW_HEIGHT_PX = 58


TERM_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3, "autumn": 3}


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
    """{StudentNumber: flag reason} for students past their program's At-Risk threshold.

    Comes from the v_student_stage_flags view (threshold set in Admin Configuration).
    Completed and Cancelled students are never in here. Saving a new threshold clears this cache.
    """
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
/* all filter labels + "Filter by Cohort" use the same size so they match */
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
/* long text (e.g. 2 advisers) wraps onto more lines inside its column instead of running past it */
.st-key-roster_scroll .roster-cell-text{display:block;white-space:normal !important;overflow-wrap:anywhere;
    word-break:break-word;line-height:1.35;}
/* RISK column pill */
.sr-risk-pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;
    letter-spacing:.03em;border:1px solid #FECACA;background:#FEF2F2;color:#B91C1C;white-space:nowrap;cursor:help;}
html[data-eo-theme="dark"] .sr-risk-pill{background:rgba(239,68,68,.14);color:#FCA5A5;border-color:rgba(239,68,68,.3);}
.sr-risk-none{color:#9CA3AF;}
</style>""",
    unsafe_allow_html=True,
)

HEADER_CSS = """<style>
/* ---- page header: copied from the Executive Overview header ---- */
.stApp{--sr-h-text:#0F172A; --sr-h-label:#4B5563; --sr-h-border:#E5E7EB;}
html[data-eo-theme="dark"] .stApp{--sr-h-text:#F1F5F9; --sr-h-label:#94A3B8; --sr-h-border:#263044;}
.sr-title{font-size:2.75rem !important;font-weight:700 !important;line-height:1.15 !important;color:var(--sr-h-text) !important;
        letter-spacing:-.01em;margin:0 !important;padding:0 !important;opacity:1 !important;}
/* title + caption stack on top of each other (something on the page lays markdown out side by side) */
.sr-head{display:block !important;width:100%;}
.sr-head .sr-title,.sr-head .sr-caption{display:block !important;width:100%;}
/* caption under the title: change margin-top to move it closer to / further from the title */
.sr-caption{font-size:14px !important;line-height:1.5 !important;color:var(--sr-h-label) !important;
        margin:4px 0 0 0 !important;padding:0 !important;opacity:1 !important;}
/* line under the whole header row (title + controls on the right); padding-bottom = space above the line */
.st-key-sr_top{border-bottom:1px solid var(--sr-h-border);padding-bottom:10px;}
/* Streamlit gives markdown a negative bottom margin that would pull the caption onto the line */
.st-key-sr_top [data-testid="stElementContainer"]:has(.sr-title),
.st-key-sr_top [data-testid="stMarkdown"]:has(.sr-title),
.st-key-sr_top [data-testid="stMarkdownContainer"]:has(.sr-title){margin:0 !important;padding:0 !important;}
</style>"""
 
# Inject unified dark mode styling
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)
 
# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to access the student roster.")
    st.stop()
 
# ---------------------------------------------------------------
# Program selection — visible to every role for demonstration.
# (Will be restricted later when the View-Only role is added.)
# ---------------------------------------------------------------
user = st.session_state.get("user", {})
role = user.get("role")
 
with st.expander("Active Program", expanded=not st.session_state.get("active_program_id")):
    programs = get_all_programs()
    options = {f"{p['ProgramCode']} — {p['ProgramName']}": p["ProgramID"] for p in programs}
 
    if options:
        current_id = st.session_state.get("active_program_id")
        default_idx = 0
        if current_id:
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
            st.session_state["active_program_code"] = selected_label.split(" — ")[0]
            set_user_program(user.get("UserID"), pid)
            st.success(f"Active program set to {selected_label}.")
            st.rerun()
 
    with st.form("create_program_form"):
        st.write("**Create New Program**")
        code = st.text_input("Program Code (e.g., BIA)")
        name = st.text_input("Program Name (e.g., BS Business Intelligence)")
        if st.form_submit_button("Create Program"):
            # US-13: block View-Only users and log the attempt
            require_edit()
 
            if not code or not name:
                st.warning("Please enter both Program Code and Name.")
            else:
                ok, result = create_program(code.strip().upper(), name.strip())
                if ok:
                    st.session_state["active_program_id"] = result
                    st.session_state["active_program_code"] = code.strip().upper()
                    set_user_program(user.get("UserID"), result)
                    st.success(f"Created **{code}** and set as active.")
                    st.rerun()
                else:
                    st.error(f"Could not create program: {result}")
 
 
 
# Block the page if no program is set
active_program_id = st.session_state.get("active_program_id")
if not active_program_id:
    st.warning("⏳ No active program has been set. Please pick one from the Active Program panel above.")
    st.stop()
 
# Student Profile only opens after a program has been picked here on the Student Roster.
# This is the "unlock" it checks for (it holds the program chosen on this page).
st.session_state["roster_program_id"] = active_program_id
st.session_state["roster_program_code"] = st.session_state.get("active_program_code", "")
 
active_code = st.session_state.get("active_program_code", "")
 
# ---------------------------------------------------------------
# Session state
# ---------------------------------------------------------------
active_login_id = st.session_state.get("session_id", None)
 
if active_login_id:
    retry_count = get_max_retry_count(active_login_id)
    if retry_count > 1:
        st.warning(
            f"Warning: Repeated sync failures detected for your session "
            f"({retry_count} attempts). Check Admin logs."
        )
 
# Header & Sync Controls (title + caption styled like the Executive Overview header)
st.markdown(HEADER_CSS, unsafe_allow_html=True)
with st.container(key="sr_top"):
    # (Refresh Now moved to the sidebar "Data" block, so it's available on every page)
    col_title = st.container()

    with col_title:
        st.markdown(
            f'<div class="sr-head"><div class="sr-title">Student Roster — {html.escape(str(active_code))} Program</div>'
            '<div class="sr-caption">Search, filter, and sort students in this program, '
            'and open any student\'s profile.</div></div>',
            unsafe_allow_html=True,
        )

 
# ---------------------------------------------------------------
# US-23: Faculty/Program Advisor sees ONLY their own advisees.
# "so that I focus on my own advisees" -> this is automatic, not a manual
# selection, so it happens before any of the other filters below even render.
# Other roles (Dean, Program Chair, IT/Admin) aren't restricted here; they
# instead get an optional "Filter by Adviser" dropdown further down.
# ---------------------------------------------------------------
my_adviser_name = None
is_advisor_view = (role == "FacultyAdvisor")
 
if is_advisor_view:
    my_adviser_name = get_my_adviser_name(user.get("UserID"))
 
cohort_choice = "All Cohorts"   # reported to the yellow header bar at the end of the page

# Displays student roster in table format
try:
    df = get_student_roster_data(program_id=active_program_id)
 
    if is_advisor_view:
        if my_adviser_name is None:
            # US-23 AC2: advisor has no Adviser record / no login link at all
            st.info(
                "You don't have an adviser profile linked to your account yet. "
                "Contact your Program Chair or IT/Admin to get set up."
            )
            df = df.iloc[0:0]
        else:
            df = df[df["Adviser"].fillna("").str.split(", ").apply(lambda names: my_adviser_name in names)]
 
    if not df.empty:
        # ----------------- Clean Filter & Search Rhythm -----------------
        # Order: Search | Filter by Adviser | Filter by Cohort (From / To) | Sort by
        filters_box = st.container(key="sr_filters")
        if is_advisor_view:
            col_search, col_cohort, col_sort = filters_box.columns([3.5, 3, 1.8], vertical_alignment="bottom")
            adviser_choice = None  # already scoped above, nothing to pick
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
                # US-23 AC1 (for non-advisor roles browsing by adviser) + AC3 (combinable with cohort)
                adviser_names = {n for v in df["Adviser"].dropna() for n in str(v).split(", ") if n}
                available_advisers = ["All Advisers"] + sorted(adviser_names)
                adviser_choice = st.selectbox("Filter by Adviser", available_advisers)

        with col_cohort:
            # Cohort range: pick a From and/or To cohort. Both on "All Cohorts" = no cohort filter.
            cohort_list = sorted(get_available_cohorts(program_id=active_program_id), key=cohort_sort_key)
            c_from, c_to = st.columns(2)
            with c_from:
                cohort_from = st.selectbox("Filter by Cohort -- From", ["All Cohorts"] + cohort_list)
            with c_to:
                cohort_to = st.selectbox("Filter by Cohort -- To", ["All Cohorts"] + cohort_list)

        with col_sort:
            sort_map = {                     # first one = default
                "Student Number": "StudentNumber",
                "Student Name": "Student",
                "Cohort": "Cohort",
                "Last Update": "LastUpdate",   # newest first
            }
            sort_choice = st.selectbox("Sort by", list(sort_map.keys()))

        # Apply Filters
        df_filtered = df.copy()

        if search_query and search_query.strip():
            q = search_query.strip().lower()
            df_filtered = df_filtered[
                df_filtered["Student"].astype(str).str.lower().str.contains(q, na=False) |
                df_filtered["StudentNumber"].astype(str).str.contains(q, na=False)
            ]

        # cohort range (inclusive); if From is later than To they're swapped
        lo = cohort_sort_key(cohort_from) if cohort_from != "All Cohorts" else None
        hi = cohort_sort_key(cohort_to) if cohort_to != "All Cohorts" else None
        if lo and hi and lo > hi:
            lo, hi = hi, lo
            cohort_from, cohort_to = cohort_to, cohort_from
        if lo or hi:
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
        if sort_col == "Cohort":   # chronological (1Q2425, 2Q2425, ...), not alphabetical
            df_filtered = df_filtered.sort_values(by="Cohort", key=lambda col: col.map(
                lambda c: cohort_sort_key(c) if pd.notna(c) else (9999, 9, "")))   # blanks go last
        else:
            df_filtered = df_filtered.sort_values(
                by=sort_col, ascending=(sort_col != "LastUpdate"), na_position="last"
            )

 
        # ----------------- Enterprise Roster Grid -----------------
        col_widths = [1.1, 2.0, 0.8, 1.9, 1.2, 1.2, 1.6, 1.1, 0.9]
        try:
            risk_flags = get_risk_flags(active_program_id)
        except Exception:
            risk_flags = {}   # view missing / DB hiccup -> RISK column just shows "—"
 
        header_cols = st.columns(col_widths, vertical_alignment="center")
        header_labels = [
            "STUDENT ID", "STUDENT", "COHORT", "ADVISER",
            "COURSEWORK", "COMP EXAM", "CAPSTONE", "LAST UPDATE", "RISK"
        ]
        for col, label in zip(header_cols, header_labels):
            col.markdown(f'<div class="roster-th">{label}</div>', unsafe_allow_html=True)
        st.markdown('<div class="roster-th-divider"></div>', unsafe_allow_html=True)
 
        if df_filtered.empty:
            st.info("No students match the current filters.")
        else:
            # Scrollable list: shows about ROWS_VISIBLE students, scroll for the rest.
            # The column headers above stay put while the rows scroll.
            scroll_height = ROW_HEIGHT_PX * ROWS_VISIBLE if len(df_filtered) > ROWS_VISIBLE else None
            with st.container(height=scroll_height, border=False, key="roster_scroll"):
                for _, row in df_filtered.iterrows():
                    s_id = str(row.get("StudentNumber", ""))
                    s_name = str(row.get("Student", "Unknown"))
                    cohort = str(row.get("Cohort", "N/A"))
                    adviser_raw = row.get("Adviser")
                    # 2+ advisers -> one per line (and each line can wrap if it's long)
                    adviser = ("<br>".join(html.escape(a) for a in str(adviser_raw).split(", ") if a)
                               if pd.notna(adviser_raw) and str(adviser_raw).strip() else "None Assigned")
 
                    cw_status = row.get("CourseworkStatus")
                    ce_status = row.get("CompExamStatus")
                    cp_status = row.get("CapstoneStatus")
 
                    cw_pill = render_status_pill(cw_status)
                    ce_pill = render_status_pill(ce_status)
                    cp_pill = render_status_pill(cp_status)
 
                    r_cols = st.columns(col_widths, vertical_alignment="center")
                    r_cols[0].markdown(
                        f'<span class="roster-cell-id">{s_id}</span>',
                        unsafe_allow_html=True
                    )
                    r_cols[1].page_link(
                        "dashboard_views/student_profile.py",
                        label=s_name,
                        query_params={"student_id": s_id}
                    )
                    r_cols[2].markdown(
                        f'<span class="roster-cell-text">{cohort}</span>',
                        unsafe_allow_html=True
                    )
                    r_cols[3].markdown(
                        f'<span class="roster-cell-text">{adviser}</span>',
                        unsafe_allow_html=True
                    )
                    r_cols[4].markdown(cw_pill, unsafe_allow_html=True)
                    r_cols[5].markdown(ce_pill, unsafe_allow_html=True)
                    r_cols[6].markdown(cp_pill, unsafe_allow_html=True)
                    last_upd = row.get("LastUpdate")
                    last_txt = pd.to_datetime(last_upd).strftime("%b %d, %Y") if pd.notna(last_upd) else "—"
                    r_cols[7].markdown(
                        f'<span class="roster-cell-text">{last_txt}</span>',
                        unsafe_allow_html=True
                    )
                    reason = risk_flags.get(s_id)
                    r_cols[8].markdown(
                        f'<span class="sr-risk-pill" title="{html.escape(reason)}">AT RISK</span>'
                        if reason is not None else '<span class="sr-risk-none">—</span>',
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        '<div class="roster-row-divider"></div>',
                        unsafe_allow_html=True
                    )

        # Total Count Bar (under the table)
        st.caption(
            f"Showing {len(df_filtered)} of {len(df)} students. "
            f"Click any student name to view their profile."
        )
    else:
        # US-23 AC2: advisor exists but has zero assigned students right now
        if is_advisor_view and my_adviser_name is not None:
            st.info(
                f"You currently have no advisees assigned in the {active_code} program. "
                f"Once a Program Chair assigns students to you, they'll appear here."
            )
        elif not is_advisor_view:
            st.info(f"No students are currently tagged under the {active_code} program.")
 
except Exception as e:
    st.error(f"Configuration Error: The Student Roster cannot load because field mappings are invalid. Please check the Admin Configuration page. ({e})")

# Yellow header bar: show this page's program + selected cohort
# (kept outside the try/except above so it can't be swallowed by it)
set_header_context(program=active_program_id, cohort=cohort_choice)
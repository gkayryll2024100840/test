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
    col_title, col_action = st.columns([2.5, 1.5], vertical_alignment="top")

    with col_title:
        st.markdown(
            f'<div class="sr-head"><div class="sr-title">Student Roster — {html.escape(str(active_code))} Program</div>'
            '<div class="sr-caption">Search, filter, and sort students in this program, '
            'and open any student\'s profile.</div></div>',
            unsafe_allow_html=True,
        )

    with col_action:
        last_sync = get_last_updated_time()
        st.caption(f"Last Refreshed: {last_sync}")
        if st.button("Refresh Now", use_container_width=False):
            success = trigger_data_sync(login_id=active_login_id)
            if success:
                st.success("Synced successfully.")
                st.rerun()
            else:
                st.error("Sync failed. Check admin logs.")
                st.rerun()
 
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
        if is_advisor_view:
            col_search, col_cohort, col_sort = st.columns([3.5, 2, 2])
            adviser_choice = None  # already scoped above, nothing to pick
        else:
            col_search, col_cohort, col_adviser, col_sort = st.columns([3, 1.8, 1.8, 1.8])
 
        with col_search:
            search_query = st.text_input(
                "SEARCH:",
                placeholder="Student name or ID...",
                label_visibility="visible"
            )
 
        with col_cohort:
            available_cohorts = ["All Cohorts"] + get_available_cohorts(program_id=active_program_id)
            cohort_choice = st.selectbox("FILTER BY COHORT:", available_cohorts)
 
        if not is_advisor_view:
            with col_adviser:
                # US-23 AC1 (for non-advisor roles browsing by adviser) + AC3 (combinable with cohort)
                adviser_names = {n for v in df["Adviser"].dropna() for n in str(v).split(", ") if n}
                available_advisers = ["All Advisers"] + sorted(adviser_names)
                adviser_choice = st.selectbox("FILTER BY ADVISER:", available_advisers)
 
        with col_sort:
            sort_map = {
                "Student Name": "Student",
                "Student ID": "StudentNumber",
                "Cohort": "Cohort",
                "Last Update (newest)": "LastUpdate",
            }
            sort_choice = st.selectbox("SORT BY:", list(sort_map.keys()))
 
        # Apply Filters
        df_filtered = df.copy()
 
        if search_query and search_query.strip():
            q = search_query.strip().lower()
            df_filtered = df_filtered[
                df_filtered["Student"].astype(str).str.lower().str.contains(q, na=False) |
                df_filtered["StudentNumber"].astype(str).str.contains(q, na=False)
            ]
 
        if cohort_choice != "All Cohorts":
            df_filtered = df_filtered[df_filtered["Cohort"] == cohort_choice]
 
        if not is_advisor_view and adviser_choice and adviser_choice != "All Advisers":
            df_filtered = df_filtered[
                df_filtered["Adviser"].fillna("").str.split(", ").apply(lambda names: adviser_choice in names)
            ]
 
        sort_col = sort_map[sort_choice]
        df_filtered = df_filtered.sort_values(
            by=sort_col, ascending=(sort_col != "LastUpdate"), na_position="last"
        )
 
        # Total Count Bar
        st.caption(
            f"Showing {len(df_filtered)} of {len(df)} students. "
            f"Click any student name to view their profile."
        )
 
        # ----------------- Enterprise Roster Grid -----------------
        col_widths = [1.2, 2.2, 0.9, 1.9, 1.2, 1.2, 1.6, 1.2]
 
        header_cols = st.columns(col_widths, vertical_alignment="center")
        header_labels = [
            "STUDENT ID", "STUDENT", "COHORT", "ADVISER",
            "COURSEWORK", "COMP EXAM", "CAPSTONE", "LAST UPDATE"
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
                    adviser = str(row.get("Adviser", "None Assigned"))
 
                    cw_status = row.get("CourseworkStatus")
                    ce_status = row.get("CompExamStatus")
                    cp_status = row.get("CapstoneStatus")
 
                    cw_pill = render_status_pill(cw_status)
                    ce_pill = render_status_pill(ce_status)
                    cp_pill = render_status_pill(cp_status)
 
                    r_cols = st.columns(col_widths)
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
                    st.markdown(
                        '<div class="roster-row-divider"></div>',
                        unsafe_allow_html=True
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
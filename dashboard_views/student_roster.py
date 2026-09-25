import streamlit as st
from permissions import require_edit
import re
 
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
)
 
st.set_page_config(page_title="Student Roster", layout="wide")
 
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
 
# Header & Sync Controls
col_title, col_action = st.columns([2.5, 1.5])
 
with col_title:
    st.title(f"Student Roster — {active_code} Program")
 
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
 
st.markdown("---")
 
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
            df = df[df["Adviser"] == my_adviser_name]
 
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
                available_advisers = ["All Advisers"] + sorted(df["Adviser"].dropna().unique().tolist())
                adviser_choice = st.selectbox("FILTER BY ADVISER:", available_advisers)
 
        with col_sort:
            sort_map = {
                "Student Name": "Student",
                "Student ID": "StudentNumber",
                "Cohort": "Cohort",
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
            df_filtered = df_filtered[df_filtered["Adviser"] == adviser_choice]
 
        df_filtered = df_filtered.sort_values(by=sort_map[sort_choice])
 
        # Total Count Bar
        st.caption(
            f"Showing {len(df_filtered)} of {len(df)} students. "
            f"Click any student name to view their profile."
        )
 
        # ----------------- Enterprise Roster Grid -----------------
        col_widths = [1.2, 2.4, 1.0, 2.0, 1.3, 1.3, 1.3]
 
        header_cols = st.columns(col_widths, vertical_alignment="center")
        header_labels = [
            "STUDENT ID", "STUDENT", "COHORT", "ADVISER",
            "COURSEWORK", "COMP EXAM", "CAPSTONE"
        ]
        for col, label in zip(header_cols, header_labels):
            col.markdown(f'<div class="roster-th">{label}</div>', unsafe_allow_html=True)
        st.markdown('<div class="roster-th-divider"></div>', unsafe_allow_html=True)
 
        if df_filtered.empty:
            st.info("No students match the current filters.")
        else:
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
 

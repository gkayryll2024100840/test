from attrs import field
import streamlit as st
import pandas as pd
from db_connect import (
    get_student_roster_data,
    get_last_updated_time,
    trigger_data_sync,
    get_max_retry_count,
    get_available_cohorts
)
from dashboard_views.components import (
    DARK_MODE_CSS, 
    render_status_pill, 
    calculate_risk_status
)

st.set_page_config(page_title="Student Roster", layout="wide")

# Inject unified dark mode styling
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to access the student roster.")
    st.stop()

active_login_id = getattr(st.session_state, "session_id", None)

    # Yellow — in progress / attention
    "In-Progress":             "background-color: #E69F00; color: black;",

    # Red — cancelled / incomplete / pending
    "Cancelled":               "background-color: #D55E00; color: white;",
    "Incomplete":              "background-color: #D55E00; color: white;",
    "Pending":                 "background-color: #D55E00; color: white;",
}

# Source column names as returned by db_connect.get_student_roster_data()
LIFECYCLE_COLUMNS = ["CourseworkStatus", "CompExamStatus", "CapstoneStatus"]

def _rename_header(col_name: str) -> str:
    """Convert CamelCase to UPPERCASE WITH SPACES (e.g. CourseworkStatus → COURSEWORK STATUS)."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", col_name).upper()

# Precompute renamed lifecycle headers (post-rename names used in the Styler subset)
RENAMED_LIFECYCLE_COLS = [_rename_header(c) for c in LIFECYCLE_COLUMNS]

def color_status(val):
    """Return CSS for a lifecycle status value."""
    return STATUS_COLORS.get(str(val).strip(), "")


# ---------------------------------------------------------------
# session_state defined safely
# ---------------------------------------------------------------
active_login_id = st.session_state.get("session_id", None)

# Check repeated failures specifically for THIS session
if active_login_id:
    retry_count = get_max_retry_count(active_login_id)
    if retry_count > 1:
        st.warning(f"Warning: Repeated sync failures detected for your session ({retry_count} attempts). Check Admin logs.")

# Header & Sync Controls
col_title, col_action = st.columns([2.5, 1.5])

with col_title:
    st.title("Student Roster")

# refresh button and last sync timestamp
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

# displays student roster in table format
df = get_student_roster_data()

if not df.empty:
    # ----------------- Clean Filter & Search Rhythm -----------------
    col_search, col_cohort, col_sort = st.columns([2, 1, 1])

    with col_search:
        search_query = st.text_input(
            "SEARCH:",
            placeholder="Search by student name or ID...",
            label_visibility="visible"
        )

    with col_cohort:
        available_cohorts = ["All Cohorts"] + get_available_cohorts()
        cohort_choice = st.selectbox("FILTER BY COHORT:", available_cohorts)

    with col_sort:
        # sorting map (only these columns can be the basis of sorting the table)
        sort_map = {
            "Student Name": "Student",
            "Student ID": "StudentNumber",
            "Cohort": "Cohort",
        }
        # dropdown selector
        sort_choice = st.selectbox("SORT BY:", list(sort_map.keys()))

    # Apply Filters
    df_filtered = df.copy()

    if search_query and search_query.strip():
        q = search_query.strip().lower()
        df_filtered = df_filtered[
            df_filtered["Student"].astype(str).str.lower().str.contains(q, na=False) |
            df_filtered["StudentNumber"].astype(str).contains(q, na=False)
        ]

    if cohort_choice != "All Cohorts":
        df_filtered = df_filtered[df_filtered["Cohort"] == cohort_choice]

    df_filtered = df_filtered.sort_values(by=sort_map[sort_choice])

    # Total Count Bar
    st.caption(f"Showing {len(df_filtered)} of {len(df)} students. Click any student name to view their profile.")

    # ----------------- Enterprise Roster Grid with Native Page Links -----------------
    # Using st.page_link keeps navigation inside Streamlit's SPA router so session state is preserved
    col_widths = [1.2, 2.2, 0.9, 1.8, 1.2, 1.2, 1.6, 1.1]

    header_cols = st.columns(col_widths)
    header_labels = [
        "STUDENT ID", "STUDENT", "COHORT", "ADVISOR",
        "COURSEWORK", "COMP EXAM", "CAPSTONE", "RISK STATUS"
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
            advisor = str(row.get("Advisor", "None Assigned"))

            cw_status = row.get("CourseworkStatus")
            ce_status = row.get("CompExamStatus")
            cp_status = row.get("CapstoneStatus")

            cw_pill = render_status_pill(cw_status)
            ce_pill = render_status_pill(ce_status)
            cp_pill = render_status_pill(cp_status)

            risk_text = calculate_risk_status(cw_status, ce_status, cp_status)
            risk_pill = render_status_pill(risk_text)

            r_cols = st.columns(col_widths)
            r_cols[0].markdown(f'<span class="roster-cell-id">{s_id}</span>', unsafe_allow_html=True)
            r_cols[1].page_link(
                "dashboard_views/student_profile.py",
                label=s_name,
                query_params={"student_id": s_id}
            )
            r_cols[2].markdown(f'<span class="roster-cell-text">{cohort}</span>', unsafe_allow_html=True)
            r_cols[3].markdown(f'<span class="roster-cell-text">{advisor}</span>', unsafe_allow_html=True)
            r_cols[4].markdown(cw_pill, unsafe_allow_html=True)
            r_cols[5].markdown(ce_pill, unsafe_allow_html=True)
            r_cols[6].markdown(cp_pill, unsafe_allow_html=True)
            r_cols[7].markdown(risk_pill, unsafe_allow_html=True)
            st.markdown('<div class="roster-row-divider"></div>', unsafe_allow_html=True)

    # ----------------- Quick Jump Navigation -----------------
    if not df_filtered.empty:
        with st.expander("Quick Jump by Student Dropdown", expanded=False):
            col_jump_sel, col_jump_btn = st.columns([3, 1])
            student_dict = {
                f"{r['StudentNumber']} - {r['Student']}": str(r['StudentNumber'])
                for _, r in df_filtered.iterrows()
            }
            with col_jump_sel:
                jump_target = st.selectbox(
                    "SELECT STUDENT:",
                    list(student_dict.keys()),
                    label_visibility="collapsed"
                )
            with col_jump_btn:
                if st.button("Open Selected Profile", use_container_width=True):
                    st.session_state["selected_student_override"] = student_dict[jump_target]
                    st.switch_page("dashboard_views/student_profile.py")

else:
    st.info(
        "No student records found in the database or connection issue occurred."
    )

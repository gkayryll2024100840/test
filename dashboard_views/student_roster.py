from attrs import field
import streamlit as st
import re
from db_connect import (
    get_student_roster_data,
    get_last_updated_time,
    trigger_data_sync,
    get_max_retry_count,
    get_available_cohorts
)

st.set_page_config(page_title="Student Roster", layout="wide")

# ---------------------------------------------------------------
# Colorblind-safe status → CSS mapping (Okabe-Ito palette,
# consistent with executive_overview.py)
# ---------------------------------------------------------------
STATUS_COLORS = {
    # Green — completed / passed / defended
    "Completed":               "background-color: #009E73; color: white;",
    "Passed":                  "background-color: #009E73; color: white;",
    "Defended for Completion": "background-color: #009E73; color: white;",

    # Yellow — in progress / attention
    "In-Progress":             "background-color: #E69F00; color: black;",

    # Red — cancelled / incomplete / pending
    "Cancelled":               "background-color: #D55E00; color: white;",
    "Incomplete":              "background-color: #D55E00; color: white;",
    "Pending":                 "background-color: #D55E00; color: white;",
}

# Optional redundant symbols for accessibility (colorblind users)
STATUS_SYMBOLS = {
    "Completed":               "🟢",
    "Passed":                  "🟢",
    "Defended for Completion": "🟢",
    "In-Progress":             "🟡",
    "Cancelled":               "🔴",
    "Incomplete":              "🔴",
    "Pending":                 "🔴",
}

# Source column names as returned by db_connect.get_student_roster_data()
LIFECYCLE_COLUMNS = ["CourseworkStatus", "CompExamStatus", "CapstoneStatus"]

def _rename_header(col_name: str) -> str:
    """Convert CamelCase to UPPERCASE WITH SPACES (e.g. CourseworkStatus → COURSEWORK STATUS)."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", col_name).upper()

# Precompute renamed lifecycle headers (post-rename names used in the Styler subset)
RENAMED_LIFECYCLE_COLS = [_rename_header(c) for c in LIFECYCLE_COLUMNS]

def color_status(val):
    """Return CSS for a lifecycle status value (strips any leading emoji)."""
    clean = (
        str(val)
        .replace("🟢", "").replace("🟡", "").replace("🔴", "")
        .strip()
    )
    return STATUS_COLORS.get(clean, "")


# ---------------------------------------------------------------
# session_state defined safely
# ---------------------------------------------------------------
active_login_id = st.session_state.get("session_id", None)

# Check repeated failures specifically for THIS session
if active_login_id:
    retry_count = get_max_retry_count(active_login_id)
    if retry_count > 1:
        st.warning(
            f"**Warning:** Repeated sync failures detected for your session "
            f"({retry_count} attempts). Check Admin logs."
        )

# Splits the top section into two columns
col_title, col_action = st.columns([2, 1])

with col_title:
    st.title("Student Roster")

# refresh button and last sync timestamp
with col_action:
    last_sync = get_last_updated_time()
    st.caption(f"Last Refreshed: {last_sync}")

    if st.button("Refresh Now"):
        success = trigger_data_sync(login_id=active_login_id)
        if success:
            st.success("Synced successfully!")
            st.rerun()
        else:
            st.error("Sync failed! Check admin logs.")
            st.rerun()

st.markdown("---")

# displays student roster in table format
df = get_student_roster_data()

if not df.empty:
    # side by side columns for sorting and filtering drop down buttons
    col_sort, col_filter = st.columns(2)

    with col_sort:
        # sorting map (only these columns can be the basis of sorting the table)
        sort_map = {
            "Student ID": "StudentNumber",
            "Student": "Student",
            "Enrollment Status": "EnrollmentStatus",
        }
        # dropdown selector
        sort_choice = st.selectbox("SORT BY:", list(sort_map.keys()))
        df_sorted = df.sort_values(by=sort_map[sort_choice])

    with col_filter:
        # Cohort dropdown filter
        available_cohorts = ["All Cohorts"] + get_available_cohorts()
        cohort_choice = st.selectbox("FILTER BY COHORT:", available_cohorts)

        # Apply cohort filtering if a specific cohort is selected
        if cohort_choice != "All Cohorts":
            df_filtered = df_sorted[df_sorted["Cohort"] == cohort_choice]
        else:
            df_filtered = df_sorted

    # formatted column headers (ex: StudentNumber -> STUDENT NUMBER)
    df_display = df_filtered.rename(columns=_rename_header).copy()

    # --- Optional: prefix statuses with symbols for accessibility ---
    for col in RENAMED_LIFECYCLE_COLS:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda v: f"{STATUS_SYMBOLS.get(str(v).strip(), '')} {v}".strip()
            )

    # --- Apply color coding to lifecycle columns only ---
    lifecycle_subset = [c for c in RENAMED_LIFECYCLE_COLS if c in df_display.columns]
    styled = df_display.style.map(color_status, subset=lifecycle_subset)

    st.dataframe(styled, use_container_width=True, hide_index=True)

else:
    st.info(
        "No student records found in the database or connection issue occurred."
    )

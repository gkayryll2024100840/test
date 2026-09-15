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

# session_state defined safely
active_login_id = getattr(st.session_state, "session_id", None)

# Check repeated failures specifically for THIS session
if active_login_id:
    retry_count = get_max_retry_count(active_login_id)
    if retry_count > 1:
        st.warning(f"**Warning:** Repeated sync failures detected for your session ({retry_count} attempts). Check Admin logs.")

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
    df_display = df_filtered.rename(
        columns=lambda x: re.sub(r"(?<!^)(?=[A-Z])", " ", x).upper()
    )

    st.dataframe(df_display, use_container_width=True, hide_index=True)

else:
    st.info(
        "No student records found in the database or connection issue occurred."
    )
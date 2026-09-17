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

active_login_id = getattr(st.session_state, "session_id", None)
username = getattr(st.session_state, "username", "")

if active_login_id:
    retry_count = get_max_retry_count(active_login_id)
    if retry_count > 1:
        st.warning(f"**Warning:** Repeated sync failures detected for your session ({retry_count} attempts). Check Admin logs.")

col_title, col_action = st.columns([2, 1])

with col_title:
    st.title("Student Roster")

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

df = get_student_roster_data()

if not df.empty:

    # Sorting and Filtering Controls
    col_sort, col_filter = st.columns(2)
    
    with col_sort:
        sort_map = {
            "Student ID": "StudentNumber",
            "Student": "Student",
            "Enrollment Status": "EnrollmentStatus",
        }
        sort_choice = st.selectbox("SORT BY:", list(sort_map.keys()))
        df_sorted = df.sort_values(by=sort_map[sort_choice])

    with col_filter:
        available_cohorts = ["All Cohorts"] + get_available_cohorts()
        cohort_choice = st.selectbox("FILTER BY COHORT:", available_cohorts)
        
        if cohort_choice != "All Cohorts":
            df_filtered = df_sorted[df_sorted["Cohort"] == cohort_choice]
        else:
            df_filtered = df_sorted

    # Format column headers for clean display
    df_display = df_filtered.rename(
        columns=lambda x: re.sub(r"(?<!^)(?=[A-Z])", " ", x).upper()
    )

    st.caption("Click the checkbox/row on the table below to select a student, then head over to the **Student Profile** page.")

    # --- NATIVE ROW SELECTION WITH INSTANT PAGE SWITCH ---
    event = st.dataframe(
        df_display, 
        use_container_width=True, 
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="roster_table"
    )

    # Instantly grab the selected row and jump pages with zero extra messages
    try:
        selected_rows = event.selection["rows"]
        if selected_rows:
            row_index = selected_rows[0]
            selected_student_num = df_filtered.iloc[row_index]["StudentNumber"]
            
            # Save to session state so student_profile.py knows who to load
            st.session_state["selected_student_override"] = selected_student_num
            
            # Instantly teleport to the student profile page
            st.switch_page("dashboard_views/student_profile.py")
    except (KeyError, IndexError):
        pass

else:
    st.info("No student records found in the database or connection issue occurred.")

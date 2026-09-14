from attrs import field
import streamlit as st
import re
from db_connect import get_student_roster_data, get_last_updated_time, trigger_data_sync, get_max_retry_count

st.set_page_config(page_title="Student Roster", layout="wide")

#session_state defined in app.py
active_login_id = st.session_state.session_id

# Check repeated failures specifically for THIS session
retry_count = get_max_retry_count(active_login_id)
if retry_count > 1:
    st.warning(f"**Warning:** Repeated sync failures detected for your session ({retry_count} attempts). Check Admin logs.")

#Splits the top section into two columns. Wider one for the title, smaller one for timestamp 
col_title, col_action = st.columns([2, 1])

with col_title:
    st.title("Student Roster")

#refresh button and last sync timestamp 
with col_action:
    last_sync = get_last_updated_time()
    st.caption(f"⏱︎ Last Refreshed: {last_sync}")
    if st.button("Refresh Now"):
        success = trigger_data_sync(login_id=active_login_id)
        if success:
            st.success("Synced successfully!")
            st.rerun()
        else:
            st.error("Sync failed! Check admin logs.")
            st.rerun()

st.markdown("---")

#displays student roster in table format
df = get_student_roster_data()

if not df.empty:
  #sorting map (only these columns can be the basis of sorting the table)
  sort_map = {
      "Student ID": "StudentNumber",
      "Student": "Student",
      "Enrollment Status": "EnrollmentStatus",
  }

  #dropdown selector
  sort_choice = st.selectbox("SORT BY:", list(sort_map.keys()))

  df_sorted = df.sort_values(by=sort_map[sort_choice])

  #formatted column headers (ex: StudentNumber -> STUDENT NUMBER)
  df_display = df_sorted.rename(
      columns=lambda x: re.sub(r"(?<!^)(?=[A-Z])", " ", x).upper()
  )

  st.dataframe(df_display, use_container_width=True)

else:
  st.info(
      "No student records found in the database or connection issue occurred."
  )
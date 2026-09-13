import streamlit as st
from db_connect import get_system_logs, trigger_data_sync
#get_system_logs(): pull history from local_logs.db
#trigger_data_sync: to test the connection to MySQL

#st: customize browser's tabs title and layout
st.set_page_config(page_title="Admin Configuration", layout="wide")

st.title("Admin Configuration")
st.markdown("---")

st.subheader("System Sync Logs")

active_login_id = st.session_state.session_id
st.info(f"Active Session ID for this browser: **{active_login_id}**")

if st.button("Run Sync Attempt"):
    #tries connecting to cloud database. True if successful, False if failed. If failed, logs the error to the local_logs.db
    success = trigger_data_sync(login_id=active_login_id)
    if success:
        st.success("Sync executed successfully!")
        st.rerun()
    else:
        st.error("Sync failed! Error logged to SQL System_Logs table.")
        st.rerun()

logs = get_system_logs()

#displays your logs on the admin screen using Streamlit
if logs:
    #turn it into an interactive table, and stretch it nicely across the full width of the admin screen
    st.dataframe(logs, use_container_width=True)
else:
    st.info("No system logs found in the local_logs.db")
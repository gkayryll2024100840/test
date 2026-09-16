import streamlit as st

user = st.session_state.get('user',{})

#grab active id session
active_session_id = st.session_state.get('session_id', 'default_admin')

st.title("Project PULSE Dashboard")

st.info(f"Active Session ID for this browser: **{active_session_id}**")
st.success(f"Welcome, {user['FirstName']} {user['LastName']}!")
st.info(f"Your role is: **{user['role']}**")

with st.expander("Account details"):
    st.write(f"**User ID:** {user['UserID']}")
    st.write(f"**Email:** {user['email']}")
    st.write(f"**Role:** {user['role']}")

#cleans up session id when logging out
if st.button("Log out"):
    st.session_state.user = None
    st.session_state.failed_attempts = 0
    st.rerun()
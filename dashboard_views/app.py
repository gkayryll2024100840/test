import streamlit as st

# Guard: if not logged in, send back to login page
if not st.session_state.get('user'):
    st.error("Please log in first.")
    st.stop()

user = st.session_state.user

st.title("Project PULSE Dashboard")

st.success(f"Welcome, {user['FirstName']} {user['LastName']}!")
st.info(f"Your role is: **{user['role']}**")

with st.expander("Account details"):
    st.write(f"**User ID:** {user['UserID']}")
    st.write(f"**Email:** {user['email']}")
    st.write(f"**Role:** {user['role']}")

# Optional: logout button
if st.button("Log out"):
    st.session_state.user = None
    st.session_state.failed_attempts = 0
    st.rerun()

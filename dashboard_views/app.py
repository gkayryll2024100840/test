import streamlit as st

# Guard: if not logged in, send back to login page
if not st.session_state.get('user'):
    st.error("Please log in first.")
    st.stop()

user = st.session_state.user

st.title("Project PULSE Dashboard")

st.success(f"Welcome, {user['FirstName']} {user['LastName']}!")
st.info(f"Your role is: **{user['role']}**")

# Define which pages each role can access
ROLE_PERMISSIONS = {
    "IT/Admin": [
        ("Executive Overview", "dashboard_views/executive_overview.py"),
        ("Student Roster", "dashboard_views/student_roster.py"),
    ],
    "Program_Chair": [
        ("Student Roster", "dashboard_views/student_roster.py"),
    ],
    # Fallback for other roles (Dean, Faculty_Advisor)
    "Dean": [
        ("Executive Overview", "dashboard_views/executive_overview.py"),
        ("Student Roster", "dashboard_views/student_roster.py"),
    ],
    "Faculty_Advisor": [
        ("Student Roster", "dashboard_views/student_roster.py"),
    ],
}

allowed_pages = ROLE_PERMISSIONS.get(role, [])

st.subheader("Menu")

cols = st.columns(len(allowed_pages))
for col, (label, page_path) in zip(cols, allowed_pages):
    with col:
        if st.button(label, use_container_width=True):
            st.switch_page(page_path)

with st.expander("Account details"):
    st.write(f"**User ID:** {user['UserID']}")
    st.write(f"**Email:** {user['email']}")
    st.write(f"**Role:** {user['role']}")

# Optional: logout button
if st.button("Log out"):
    st.session_state.user = None
    st.session_state.failed_attempts = 0
    st.switch_page("login.py")

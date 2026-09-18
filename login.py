import os
import hashlib
import uuid
import streamlit as st
import mysql.connector
import pandas as pd
from dotenv import load_dotenv
from db_connect import get_db_connection, format_mysql_error
from system_log import log_sync_attempt_local

load_dotenv()

# Creates session ID
# For US-16. Used to track sync attempts and log errors in local_logs.db
if "session_id" not in st.session_state:
    st.session_state.session_id = f"SESSION-{uuid.uuid4().hex[:6].upper()}"

MAX_FAILED_ATTEMPTS = 3

# Logs unauthorized access attempts
if 'failed_attempts' not in st.session_state:
    st.session_state.failed_attempts = 0


def log_failed_attempt(user_id, ip_address=None):
    """Insert a wrong-password attempt into login_logs."""
    try:
        connection = get_db_connection()
    except mysql.connector.Error:
        return

    try:
        with connection.cursor(dictionary=True) as cursor:
            sql = """
                INSERT INTO login_logs (UserID, ip_address, attempted_at)
                VALUES (%s, %s, NOW())
            """
            cursor.execute(sql, (user_id, ip_address))
            connection.commit()
    except mysql.connector.Error as e:
        st.warning(f"⚠️ Log failed: {e}")
    finally:
        connection.close()


# Login verify
def verify_login(user_id, password):
    """Verify user credentials against the database."""
    session_id = st.session_state.get('session_id', 'UNKNOWN_SESSION')

    try:
        connection = get_db_connection()
    except mysql.connector.Error as e:
        msg = format_mysql_error(e)
        log_sync_attempt_local(status="FAILED", error_message=msg, login_id=session_id)
        return False, msg

    try:
        with connection.cursor(dictionary=True) as cursor:
            sql = """
                SELECT UserID, FirstName, LastName, password_hash, salt, role, email
                FROM Users
                WHERE UserID = %s
            """
            cursor.execute(sql, (user_id,))
            user = cursor.fetchone()

            if not user:
                return False, "Invalid User ID or password."

            stored_salt = user['salt']
            combined = password + stored_salt
            computed_hash = hashlib.sha256(combined.encode()).hexdigest()

            if computed_hash == user['password_hash']:
                st.session_state.failed_attempts = 0
                return True, user
            else:
                st.session_state.failed_attempts += 1

                if st.session_state.failed_attempts >= MAX_FAILED_ATTEMPTS:
                    log_failed_attempt(user['UserID'], st.session_state.get('client_ip'))
                    return False, "Invalid User ID or password. Unauthorized attempts have been logged."
                else:
                    return False, "Invalid User ID or password. Verify using email."

    except mysql.connector.Error as er:
        log_sync_attempt_local(status="FAILED", error_message=f"Database error: {er}", login_id=session_id)
        return False, f"Database error: {er}"
    finally:
        connection.close()


# ============================================================
# ROUTING
# ============================================================
if not st.session_state.get('logged_in'):
    # --- LOGIN SCREEN (no header changes) ---
    st.title("Project PULSE Login Page")
    input_id = st.text_input("User ID")
    input_pass = st.text_input("Password", type="password")
    button_login = st.button("Log in")

    if button_login:
        if not input_id or not input_pass:
            st.warning("Please enter both User ID and Password.")
        else:
            success, result = verify_login(input_id, input_pass)
            if success:
                st.session_state["logged_in"] = True
                st.session_state["user"] = result
                if st.query_params.get("student_id"):
                    st.session_state["selected_student_override"] = str(
                        st.query_params.get("student_id")
                    ).strip()
                st.rerun()
            else:
                st.error(result)

else:
    # ------------------ AUTHENTICATED DASHBOARD NAVIGATION ------------------

    st.markdown(f"""
<style>
    /* Restyle Streamlit's header — it already respects the sidebar */
    [data-testid="stHeader"] {{
        background-color: #b91b21 !important;
        height: 72px !important;
        padding: 0 28px !important;
        display: flex !important;
        align-items: center !important;
        z-index: 999990 !important;
    }}

    /* Give the header its own content via a pseudo-element */
    [data-testid="stHeader"]::before {{
        content: "MAPÚA UNIVERSITY · ASU PATHWAYS\\A ETYSB Dashboard";
        white-space: pre;
        color: #ffffff !important;
        font-family: "Source Sans Pro", sans-serif;
        font-size: 14px;
        font-weight: 600;
        line-height: 1.5;
        letter-spacing: 0.3px;
        text-transform: none;
        position: absolute;
        left: 28px;
        top: 50%;
        transform: translateY(-50%);
        pointer-events: none;
    }}

    /* Program label on the right */
    [data-testid="stHeader"]::after {{
        position: absolute;
        right: 120px;
        top: 50%;
        transform: translateY(-50%);
        color: #f5d5d7 !important;
        font-family: "Source Sans Pro", sans-serif;
        font-size: 13px;
        font-weight: 600;
        pointer-events: none;
    }}

    /* Push page content below the header */
    .block-container {{
        padding-top: 90px !important;
    }}
</style>
""", unsafe_allow_html=True)

    # ----- Sidebar position (updated per request) -----
    st.markdown("""
<style>
[data-testid="stSidebarCollapseButton"] {
    position: fixed;
    top: 50%;
    left: 20px; /* Adjust left offset if needed (e.g., left: 20px;) */
    transform: translateY(-50%);
    z-index: 999; /* Keeps it on top of other content */
}

[data-testid="stExpandSidebarButton"] {
    position: fixed;
    top: 50%;
    left: 20px; /* Adjust left offset if needed (e.g., left: 20px;) */
    transform: translateY(-50%);
    z-index: 999; /* Keeps it on top of other content */
}


</style>


""", unsafe_allow_html=True)

    user = st.session_state.user
    role = user.get('role')

    if st.sidebar.button("Log Out"):
        st.session_state.clear()
        st.rerun()

    has_student_target = bool(
        st.query_params.get("student_id")
        or st.session_state.get("selected_student_override")
    )

    home         = st.Page("dashboard_views/app.py",                title="Home",               default=not has_student_target)
    exec_page    = st.Page("dashboard_views/executive_overview.py", title="Executive Overview")
    roster_page  = st.Page("dashboard_views/student_roster.py",     title="Student Roster")
    profile_page = st.Page("dashboard_views/student_profile.py",    title="Student Profile",    default=has_student_target)
    config_page  = st.Page("dashboard_views/admin_config.py",       title="Admin Config")

    if role == "Dean":
        allowed = [home, exec_page, roster_page, profile_page, config_page]
    elif role == "IT/Admin":
        allowed = [home, exec_page, roster_page, profile_page, config_page]
    elif role == "Program_Chair":
        allowed = [home, exec_page, roster_page, profile_page]
    elif role == "Faculty_Advisor":
        allowed = [home, roster_page, exec_page]
    else:
        allowed = []

    if not allowed:
        st.error("No pages assigned to your role. Contact IT/Admin.")
        st.stop()

    pg = st.navigation(allowed, position="sidebar")
    pg.run()

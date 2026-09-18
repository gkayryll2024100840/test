import os
import hashlib
import uuid
import streamlit as st
import streamlit.components.v1 as components
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
    """Verify user credentials against the database.

    Returns a tuple: (success: bool, result: dict or str)
    - On success: (True, user_dict)
    - On failure: (False, error_message)
    """
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

            # User not found
            if not user:
                return False, "Invalid User ID or password."

            # Recompute the hash using the stored salt
            stored_salt = user['salt']
            combined = password + stored_salt
            computed_hash = hashlib.sha256(combined.encode()).hexdigest()

            # Compare hashes
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
# HEADER + SIDEBAR-AWARE LAYOUT (rendered only when logged in)
# ============================================================
def render_navbar(program_code="MBA"):
    """Render the fixed top bar and JS that keeps it aligned with the sidebar."""

    st.markdown("""
<style>
    /* Fixed top bar — floats above everything except the sidebar */
    .navbar {
        position: fixed !important;
        top: 0 !important;
        left: 260px !important;
        width: calc(100% - 260px) !important;
        height: 72px !important;
        background-color: #b91b21 !important;
        z-index: 999999 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        padding: 0 28px !important;
        box-sizing: border-box !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.12) !important;
        transition: left 0.25s ease, width 0.25s ease !important;
        pointer-events: auto !important;
    }

    .navbar-content {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }

    .navbar-breadcrumbs {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.8px;
        color: #f5d5d7;
        text-transform: uppercase;
    }

    .navbar-title {
        font-size: 18px;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: 0.2px;
    }

    .navbar-program {
        font-size: 13px;
        color: #f5d5d7;
    }

    .navbar-program strong {
        color: #ffffff;
        font-weight: 700;
    }

    /* Push Streamlit's own top bar out of the way */
    [data-testid="stHeader"] {
        z-index: 0 !important;
        background: transparent !important;
    }

    /* Sidebar stays above the navbar */
    [data-testid="stSidebar"] {
        z-index: 1000000 !important;
    }

    /* Push page content below the fixed navbar */
    .block-container {
        padding-top: 90px !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# ROUTING
# ============================================================
if not st.session_state.get('logged_in'):
    # --- LOGIN SCREEN (no navbar) ---
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
                # Preserve student_id if user followed a direct link
                if st.query_params.get("student_id"):
                    st.session_state["selected_student_override"] = str(
                        st.query_params.get("student_id")
                    ).strip()
                st.rerun()
            else:
                st.error(result)

else:
    # ------------------ AUTHENTICATED DASHBOARD NAVIGATION ------------------
    user = st.session_state.user
    role = user.get('role')

    # Program label from session state
    program_code = st.session_state.get("active_program_code", "MBA")

    # Render the fixed header (with JS keeping it aligned to the sidebar)
    render_navbar(program_code=program_code)

    # Sidebar logout button
    if st.sidebar.button("Log Out"):
        st.session_state.clear()
        st.rerun()

    has_student_target = bool(
        st.query_params.get("student_id")
        or st.session_state.get("selected_student_override")
    )

    # Define all available pages
    home         = st.Page("dashboard_views/app.py",                title="Home",               default=not has_student_target)
    exec_page    = st.Page("dashboard_views/executive_overview.py", title="Executive Overview")
    roster_page  = st.Page("dashboard_views/student_roster.py",     title="Student Roster")
    profile_page = st.Page("dashboard_views/student_profile.py",    title="Student Profile",    default=has_student_target)
    config_page  = st.Page("dashboard_views/admin_config.py",       title="Admin Config")

    # Role-based page access control
    if role == "Dean":
        allowed = [home, exec_page, roster_page, profile_page, config_page]
    elif role == "IT/Admin":
        allowed = [home, config_page]
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

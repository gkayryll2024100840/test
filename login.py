import os
import hashlib
import uuid
import streamlit as st
import mysql.connector
import pandas as pd
from dotenv import load_dotenv
from db_connect import get_db_connection, format_mysql_error
from system_log import log_sync_attempt_local
from dashboard_views.components import render_app_shell

load_dotenv()

# Creates session ID
if "session_id" not in st.session_state:
    st.session_state.session_id = f"SESSION-{uuid.uuid4().hex[:6].upper()}"

MAX_FAILED_ATTEMPTS = 3

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


def verify_login(user_id, password):
    """Verify user credentials against the database."""
    try:
        connection = get_db_connection()
    except mysql.connector.Error as e:
        return False, f"Database connection error: {e}"

    try:
        with connection.cursor(dictionary=True) as cursor:
            sql = """
                SELECT UserID, FirstName, LastName, PasswordHash, Salt, Role, Email,
                       isActive, RolePermission, CurrentProgramID
                FROM Users
                WHERE UserID = %s
            """
            cursor.execute(sql, (user_id,))
            user = cursor.fetchone()

            if not user:
                return False, "Invalid User ID or password."

            stored_salt = user['Salt']
            combined = password + stored_salt
            computed_hash = hashlib.sha256(combined.encode()).hexdigest()

            if computed_hash == user['PasswordHash']:
                if not user.get('isActive', 1):
                    return False, "This account has been deactivated. Contact IT/Admin."

                st.session_state.failed_attempts = 0
                user = {k.lower(): v for k, v in user.items()}
                return True, user
            else:
                st.session_state.failed_attempts += 1

                if st.session_state.failed_attempts >= MAX_FAILED_ATTEMPTS:
                    log_failed_attempt(user['UserID'], st.session_state.get('client_ip'))
                    return False, "Invalid User ID or password. Unauthorized attempts have been logged."
                else:
                    return False, "Invalid User ID or password. Verify using email."

    except mysql.connector.Error as er:
        return False, f"Database error: {er}"
    finally:
        connection.close()


# -------------------------------------Streamlit UI-----------------------------------------------------

if not st.session_state.get('user'):
    # ----- Hide sidebar + its toggle buttons while on the login screen -----
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stExpandSidebarButton"] {
            display: none !important;
        }
        /* Give the login content a bit more breathing room without the sidebar */
        section.main > div.block-container {
            padding-top: 3rem !important;
            max-width: 900px;
            margin: 0 auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

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
    user = st.session_state.user
    role = user.get('role')

    has_student_target = bool(
        st.query_params.get("student_id")
        or st.session_state.get("selected_student_override")
    )

    exec_page    = st.Page("dashboard_views/executive_overview.py", title="Executive Overview", default=not has_student_target)
    roster_page  = st.Page("dashboard_views/student_roster.py",     title="Student Roster")
    profile_page = st.Page("dashboard_views/student_profile.py",    title="Student Profile",    default=has_student_target)
    config_page  = st.Page("dashboard_views/admin_config.py",       title="Admin Config")

    if role == "Dean":
        allowed = [exec_page, roster_page, profile_page, config_page]
    elif role == "IT/Admin":
        allowed = [exec_page, roster_page, profile_page, config_page]
    elif role == "Program_Chair":
        allowed = [exec_page, roster_page, profile_page]
    elif role == "Faculty_Advisor":
        allowed = [exec_page, roster_page, profile_page]
    elif role == "Success_Advisor":
        allowed = [exec_page, roster_page, profile_page]
    else:
        allowed = []

    if not allowed:
        st.error(
            f"No pages assigned to your role. Contact IT/Admin. "
            f"(Detected role: {role!r})"
        )
        st.stop()

    pg = st.navigation(allowed, position="sidebar")
    render_app_shell(user, page_key=pg.title)
    pg.run()

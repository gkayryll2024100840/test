import os
import hashlib
import uuid
import streamlit as st
import mysql.connector
import pandas as pd
from dotenv import load_dotenv
from db_connect import get_db_connection, format_mysql_error
from system_log import log_sync_attempt_local
# render_sidebar_permission_badge (permissions.py) drew the old "Access Mode ● Edit" block.
# The new sidebar card shows the same value via get_user_permission(), so it is no longer called.
from dashboard_views.components import render_app_shell

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


# login verify
def verify_login(user_id, password):
    """Verify user credentials against the database.

    Returns a tuple: (success: bool, result: dict or str)
    - On success: (True, user_dict) with lowercase keys
    - On failure: (False, error_message)
    """
    try:
        connection = get_db_connection()
    except mysql.connector.Error as e:
        return False, f"Database connection error: {e}"

    try:
        with connection.cursor(dictionary=True) as cursor:
            # FIX: Pull all needed columns from the updated Users schema
            sql = """
                SELECT UserID, FirstName, LastName, PasswordHash, Salt, Role, Email,
                       isActive, RolePermission, CurrentProgramID
                FROM Users
                WHERE UserID = %s
            """
            cursor.execute(sql, (user_id,))
            user = cursor.fetchone()

            # User not found
            if not user:
                return False, "Invalid User ID or password."

            # Recompute the hash using the stored salt
            stored_salt = user['Salt']
            combined = password + stored_salt
            computed_hash = hashlib.sha256(combined.encode()).hexdigest()

            # Compare hashes
            if computed_hash == user['PasswordHash']:
                # FIX: Block deactivated accounts (isActive == 0 / False)
                if not user.get('isActive', 1):
                    return False, "This account has been deactivated. Contact IT/Admin."

                st.session_state.failed_attempts = 0

                # FIX: Normalize all keys to lowercase so downstream code
                # (e.g. user.get('role')) works regardless of SQL column casing.
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


# -------------------------------------Streamlit Ui-----------------------------------------------------
# --- If NOT logged in: show the login form ---
if not st.session_state.get('user'):
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
    # FIX: Keys are now lowercase because verify_login() normalizes them.
    # This works whether you use 'role' or 'Role' — but we read 'role' here.
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
        allowed = [profile_page, roster_page, exec_page]
    elif role == "Success_Advisor":
        allowed = [profile_page, roster_page, exec_page]
    else:
        allowed = []

    if not allowed:
        # FIX: Show the actual returned role value so you can debug mismatches.
        st.error(
            f"No pages assigned to your role. Contact IT/Admin. "
            f"(Detected role: {role!r})"
        )
        st.stop()

    pg = st.navigation(allowed, position="sidebar")
    render_app_shell(user, page_key=pg.title)   # red/yellow header + sidebar card on every page
    pg.run()
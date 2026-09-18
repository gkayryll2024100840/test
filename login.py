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

    import streamlit.components.v1 as components

    st.markdown("""
<style>
    .navbar {
        position: fixed;
        top: 0;
        left: 260px;
        width: calc(100% - 260px);
        height: 72px;
        background-color: #b91b21;
        z-index: 1000;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 28px;
        box-sizing: border-box;
        box-shadow: 0 2px 6px rgba(0,0,0,0.12);
        transition: left 0.25s ease, width 0.25s ease;
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

    /* Push page content below the fixed navbar */
    .block-container {
        padding-top: 90px !important;
    }
</style>
""", unsafe_allow_html=True)

    program_code = st.session_state.get("active_program_code", "MBA")

    st.markdown(f"""
<nav class="navbar" id="pulse-navbar">
  <div class="navbar-content">
    <div class="navbar-breadcrumbs">MAPÚA UNIVERSITY · ASU PATHWAYS</div>
    <div class="navbar-title">ETYSB Dashboard — {program_code} Program</div>
  </div>
  <div class="navbar-program">
    Program: <strong>{program_code}</strong>
  </div>
</nav>
""", unsafe_allow_html=True)

    # JS: keep the navbar aligned with the sidebar's current width
    components.html("""
<script>
(function() {
    function adjustNavbar() {
        const sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
        const navbar  = window.parent.document.getElementById('pulse-navbar');
        if (!sidebar || !navbar) return;

        const rect = sidebar.getBoundingClientRect();
        // Treat anything <= 50px as "collapsed"
        const w = rect.width > 50 ? rect.width : 0;

        navbar.style.left  = w + 'px';
        navbar.style.width = 'calc(100% - ' + w + 'px)';
    }

    adjustNavbar();

    const sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
    if (sidebar) {
        const obs = new MutationObserver(adjustNavbar);
        obs.observe(sidebar, {
            attributes: true,
            attributeFilter: ['style', 'class', 'aria-expanded']
        });
    }
    setInterval(adjustNavbar, 400);
})();
</script>
""", height=0)

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

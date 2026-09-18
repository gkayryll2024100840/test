import os
import hashlib
import uuid
import streamlit as st
import mysql.connector
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from db_connect import get_db_connection, format_mysql_error
from system_log import log_sync_attempt_local
 
def show_empty_navbar():
    st.markdown('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.4.1/dist/css/bootstrap.min.css" integrity="sha384-Vkoo8x4CGsO3+Hhxv8T/Q5PaXtkKtu6ug5TOeNV6gBiFeWPGFN9MuhOf23Q9Ifjh" crossorigin="anonymous">', unsafe_allow_html=True)
 
st.markdown("""
<style>
    .navbar {
        position: fixed
        top: 0 ;
        left: 0 ;
        width: 100% ;
        height: 100px;
        background-color: #0e1117;
        z-index: 150;
    }
 
    /* Streamlit header */
    [data-testid="stHeader"] {
        z-index: 100;
    }
 
    /* Sidebar stays visible */
    [data-testid="stSidebar"] {
        z-index: 1000;
    }
</style>
""", unsafe_allow_html=True)
 
st.markdown("""
<nav class="navbar navbar-expand-lg fixed-top"  
     style="padding: 0 30px;">
 
</nav>
""", unsafe_allow_html=True)
 
 
show_empty_navbar()
 
load_dotenv()
 
#creates session ID
#for us-16. Used to track sync attempts and log the errors in local_logs.db
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
 
# -------------------------------------Streamlit UI & Routing-----------------------------------------------------
if not st.session_state.get('logged_in'):
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
                    st.session_state["selected_student_override"] = str(st.query_params.get("student_id")).strip()
                st.rerun()
            else:
                st.error(result)
else:
    # ------------------ AUTHENTICATED DASHBOARD NAVIGATION ------------------
   
    st.markdown("""
<style>
    .navbar {
        position: fixed;
        top: 0 ;
        left: 0px ;
        width: 100% ;
        height: 100px ;
        background-color: #b91b21 ;
        z-index: 150 ;
        display: flex ;
        align-items: center ;
        justify-content: space-between;
        padding: 0 30px ;
        box-sizing: border-box ;
    }
 
    [data-testid="stHeader"] {
        z-index: 0;
    }
 
    [data-testid="stSidebar"] {
        z-index: 200;
    }
 
    .navbar-content {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
 
    .navbar-breadcrumbs {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.8px;
        color: #b0c0d8;
        text-transform: uppercase;
    }
 
    .navbar-title {
        font-size: 20px;
        font-weight: 700;
        color: white;
        letter-spacing: 0.2px;
    }
 
    .navbar-program {
        font-size: 14px;
        color: #d0dbe9;
    }
 
    .navbar-program strong {
        color: white;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)
 
 
# Keep the HTML tags flush against the left margin of the string
    st.markdown("""
<nav class="navbar">
<div class="navbar-content">
<div class="navbar-breadcrumbs">
MAPÚA UNIVERSITY · ASU PATHWAYS
</div>
<div class="navbar-title">
ETYSB Dashboard — MBA Program
</div>
</div>
<div class="navbar-program">
Program: <strong>MBA</strong>
</div>
</nav>
""", unsafe_allow_html=True)
 
   
    user = st.session_state.user
    role = user.get('role')
 
    if st.sidebar.button("Log Out"):
        st.session_state.clear()
        st.session_state.failed_attempts = 0
        st.rerun()
        show_empty_navbar()
 
    # Route directly to student profile if a student target was requested
    has_student_target = bool(st.query_params.get("student_id") or st.session_state.get("selected_student_override"))
 
    # Define all available pages
    home    = st.Page("dashboard_views/app.py",                title="Home",        default=not has_student_target)
    exec_page    = st.Page("dashboard_views/executive_overview.py", title="Executive Overview")
    roster_page  = st.Page("dashboard_views/student_roster.py",     title="Student Roster")
    profile_page = st.Page("dashboard_views/student_profile.py",    title="Student Profile",  default=has_student_target)
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

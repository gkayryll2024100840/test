import os
import hashlib
import streamlit as st
import mysql.connector
from db_connect import get_db_connection

MAX_FAILED_ATTEMPTS = 3

#Logs unauthorized access attempts
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

#login verify
def verify_login(user_id, password):
    """Verify user credentials against the database.
    
    Returns a tuple: (success: bool, result: dict or str)
    - On success: (True, user_dict)
    - On failure: (False, error_message)
    """
    try:
        connection = get_db_connection()
    except mysql.connector.Error as e:
        return False, f"Database connection error: {e}"

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
        return False, f"Database error: {er}"
    finally:
        connection.close()

#-------------------------------------Streamlit Ui-----------------------------------------------------

st.title("Project PULSE Login Page")
input_id = st.text_input("User ID")
input_pass = st.text_input("Password", type = "password")
button_login = st.button("Log in")

if button_login:
    if not input_id or not input_pass:
        st.warning("Please enter both User ID and Password.")
    else:
        success, result = verify_login(input_id, input_pass)

        if success:
            st.session_state.user = result
            st.switch_page("dashboard_views/app.py")
        else:
            st.error(result)

if st.session_state.get('user'):
    user = st.session_state.user
    role = user['role']

    # Define available pages
    exec_page   = st.Page("dashboard_views/executive_overview.py", title="Executive Overview")
    roster_page = st.Page("dashboard_views/student_roster.py",     title="Student Roster")
    dashboard   = st.Page("dashboard_views/app.py",                title="Dashboard")

    # Role → allowed pages
    if role in {"IT/Admin", "Dean"}:
        allowed = [dashboard, exec_page, roster_page]
    elif role in {"Program_Chair", "Faculty_Advisor"}:
        allowed = [dashboard, roster_page]
    else:
        allowed = []

    if not allowed:
        st.error("No pages assigned to your role. Contact IT/Admin.")
        st.stop()

    nav = st.navigation(allowed)
    nav.run()


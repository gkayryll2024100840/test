import os
import hashlib
import pymysql
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
timeout = 10

#connect to database
DB_CONFIG = {
    'charset': "utf8mb4",
    'connect_timeout': 10,
    'cursorclass': pymysql.cursors.DictCursor,
    'database': "defaultdb",
    'host': os.getenv('DB_HOST'),
    'password': os.getenv('DB_PASSWORD'),
    'read_timeout': 10,
    'port': int(os.getenv('DB_PORT', 25535)),
    'user': os.getenv('DB_USER'),
    'write_timeout': 10,
}

MAX_FAILED_ATTEMPTS = 3

if 'failed_attempts' not in st.session_state:
    st.session_state.failed_attempts = 0

def log_failed_attempt(user_id, ip_address=None):
    """Insert a wrong-password attempt into login_logs."""
    try:
        connection = pymysql.connect(**DB_CONFIG)
    except pymysql.Error:
        return

    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO login_logs (UserID, ip_address, attempted_at)
                VALUES (%s, %s, NOW())
            """
            cursor.execute(sql, (user_id, ip_address))
            connection.commit()
    except pymysql.Error as e:
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
        connection = pymysql.connect(**DB_CONFIG)
    except pymysql.Error as e:
        return False, f"Database connection error: {e}"

    try:
        with connection.cursor() as cursor:
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
                log_failed_attempt(user['UserID'], st.session_state.get('client_ip'))
                if st.session_state.failed_attempts >= MAX_FAILED_ATTEMPTS:
                    return False, "Invalid User ID or password. Unauthorized attempts have been logged."
                else: 
                    return False, "Invalid User ID or password. Verify using email."

    except pymysql.Error as er:
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
            user = result
            st.success(f"Welcome, {user['FirstName']} {user['LastName']}!")
            st.info(f"Your role is: **{user['role']}**")
            # Optionally display more info (for testing only)
            with st.expander("Account details"):
                st.write(f"**User ID:** {user['UserID']}")
                st.write(f"**Email:** {user['email']}")
                st.write(f"**Role:** {user['role']}")
        else:
            st.error(result)


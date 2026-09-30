import os
import base64
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


def get_base64_of_file(path):
    """Reads a local image file and returns it as a base64 string for embedding in CSS/HTML."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def find_asset(*candidates):
    """Returns the first existing path among the given candidates, or None."""
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


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
    # ----- Resolve logo + background from the assets folder -----
    # (Falls back gracefully if the files aren't present, so the login page
    #  still works on a fresh clone or on Streamlit Cloud.)
    logo_path = find_asset(
        "assets/mapua-university-logo.png",
        "assets/mapua_logo.png",
        "assets/etysb_logo.png",
    )
    bg_path = find_asset(
        "assets/dashboardbackground.png",
        "assets/dashboard_background.png",
    )

    logo_base64 = get_base64_of_file(logo_path) if logo_path else ""
    background_base64 = get_base64_of_file(bg_path) if bg_path else ""

    bg_layer = (
        f'url("data:image/png;base64,{background_base64}")'
        if background_base64
        else "linear-gradient(160deg, #B91C2C 0%, #D9622B 50%, #F0A93A 100%)"
    )
    logo_html = (
        f'<img src="data:image/png;base64,{logo_base64}">'
        if logo_base64 else
        '<span style="font-size:22px;font-weight:700;color:#B91C2C;">PULSE</span>'
    )

    # ----- Hide sidebar + toggle buttons while on the login screen, apply the login skin -----
    st.markdown(
        f"""
        <style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stExpandSidebarButton"] {{
            display: none !important;
        }}

        [data-testid="stAppViewContainer"] {{
            background:
                linear-gradient(160deg, rgba(185,28,44,0.75) 0%, rgba(217,98,43,0.75) 45%, rgba(240,169,58,0.75) 100%),
                {bg_layer};
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        }}
        [data-testid="stHeader"] {{
            background: rgba(0,0,0,0);
        }}

        section.main > div.block-container {{
            padding-top: 2.5rem !important;
            max-width: 460px;
            margin: 0 auto;
        }}

        .st-key-login_card {{
            background: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 18px;
            padding: 36px 32px 28px 32px;
            backdrop-filter: blur(8px);
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
        }}

        .login-logo {{
            width: 90px;
            height: 90px;
            border-radius: 50%;
            background: #FFFFFF;
            margin: 0 auto 18px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}

        .login-logo img {{
            width: 60px;
            height: 60px;
            object-fit: contain;
        }}

        .login-title {{
            font-size: 28px;
            font-weight: 700;
            color: #1A1F36;
            margin-bottom: 24px;
            text-align: center;
            width: 100%;
        }}

        .st-key-login_card [data-testid="stTextInput"] label {{
            color: #1A1F36 !important;
            font-weight: 500;
            text-align: left;
            width: 100%;
        }}
        .st-key-login_card [data-testid="stTextInput"] input {{
            background: #FFFFFF !important;
            border-radius: 8px !important;
            border: none !important;
            padding: 10px 14px !important;
        }}
        .st-key-login_card [data-testid="stTextInput"] div[data-baseweb="input"] {{
            background: #FFFFFF !important;
            border-radius: 8px !important;
        }}
        .st-key-login_card [data-testid="stTextInputField"]::-ms-reveal,
        .st-key-login_card [data-testid="stTextInputField"]::-ms-clear {{
            display: none;
        }}

        .st-key-login_card button[kind="primary"],
        .st-key-login_card button {{
            background: #12172B !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            width: 100% !important;
            padding: 10px 0 !important;
            margin-top: 10px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ----- Card content -----
    with st.container(key="login_card"):
        st.markdown(
            f'<div class="login-logo">{logo_html}</div>'
            '<div class="login-title">Welcome Back!</div>',
            unsafe_allow_html=True,
        )

        input_id = st.text_input("UserID", key="login_userid")
        input_pass = st.text_input("Password", type="password", key="login_password")
        button_login = st.button("Login", key="login_button", use_container_width=True)

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

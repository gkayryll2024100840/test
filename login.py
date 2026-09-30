# LOGIN.PY
# UPDATED: 9/30/2026 (7:34 pm)

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

        /* ===== NARROW + CENTER THE PAGE CONTAINER ===== */
        [data-testid="stMainBlockContainer"],
        [data-testid="stAppViewBlockContainer"],
        section.main > div.block-container {{
            padding-top: 3rem !important;
            max-width: 500px !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }}

        /* The card itself: never wider than 500px, always centered */
        .st-key-login_card,
        .st-key-login_card > div,
        .st-key-login_card [data-testid="stVerticalBlock"] {{
            max-width: 500px !important;
            width: 100% !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }}

        .st-key-login_card {{
            background: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 16px;
            padding: 24px 22px 20px 22px;
            backdrop-filter: blur(8px);
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
        }}

        .login-logo {{
            width: 64px;
            height: 64px;
            border-radius: 50%;
            background: #FFFFFF;
            margin: 0 auto 12px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        .login-logo img {{
            width: 42px;
            height: 42px;
            object-fit: contain;
        }}

        .login-title {{
            font-size: 20px;
            font-weight: 700;
            color: #1A1F36;
            margin-bottom: 16px;
            text-align: center;
            width: 100%;
        }}

        /* ---- Inputs: target every Streamlit wrapper layer ---- */
        .st-key-login_card [data-testid="stTextInput"] label,
        .st-key-login_card [data-testid="stTextInput"] label p {{
            font-size: 12px !important;
            color: #1A1F36 !important;
            font-weight: 500 !important;
            margin-bottom: 2px !important;
            line-height: 1.2 !important;
        }}
        .st-key-login_card [data-testid="stTextInput"] {{
            margin-bottom: 4px !important;
        }}
        .st-key-login_card [data-testid="stTextInput"] input,
        .st-key-login_card [data-testid="stTextInput"] input:focus,
        .st-key-login_card [data-baseweb="input"],
        .st-key-login_card [data-baseweb="base-input"],
        .st-key-login_card [data-baseweb="input"] > div,
        .st-key-login_card div[data-testid="stTextInputRootElement"] {{
            background: #FFFFFF !important;
            border: none !important;
            border-radius: 6px !important;
            box-shadow: none !important;
            min-height: 32px !important;
            height: 32px !important;
        }}
        .st-key-login_card [data-testid="stTextInput"] input {{
            font-size: 13px !important;
            padding: 0 10px !important;
            color: #1A1F36 !important;
            line-height: 32px !important;
        }}
        .st-key-login_card [data-testid="stTextInput"] > div {{
            border: none !important;
            box-shadow: none !important;
        }}
        .st-key-login_card [data-testid="stTextInput"] [data-baseweb="input"]:focus-within {{
            border: none !important;
            box-shadow: none !important;
        }}
        .st-key-login_card [data-testid="stVerticalBlock"],
        .st-key-login_card [data-testid="stVerticalBlockBorderWrapper"] > div {{
            gap: 2px !important;
        }}
        .st-key-login_card [data-testid="stElementContainer"] {{
            margin: 0 !important;
            padding: 0 !important;
        }}
        .st-key-login_card [data-testid="stTextInputField"]::-ms-reveal,
        .st-key-login_card [data-testid="stTextInputField"]::-ms-clear {{
            display: none;
        }}

        /* ---- Login button ---- */
        .st-key-login_card button[kind="primary"],
        .st-key-login_card button {{
            background: #12172B !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            width: 100% !important;
            height: 36px !important;
            padding: 0 !important;
            margin-top: 8px !important;
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

    # ↓↓↓ Handlers MUST be indented inside the same `if` block that defines the widgets
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

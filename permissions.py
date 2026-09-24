import streamlit as st
from db_connect import can_edit, log_permission_attempt, get_user_permission


def get_current_user():
    return st.session_state.get("user", {})


def require_edit():
    """Call at the top of any write action.

    - View Only user: logs the attempt, shows an error, stops.
    - Edit user: returns True.
    """
    user = get_current_user()
    uid = user.get("userid")
    if not uid:
        st.error("Not logged in.")
        st.stop()

    if not can_edit(uid):
        log_permission_attempt(uid)
        st.error("View-Only access. This action is not allowed and has been logged.")
        st.stop()

    return True


def render_sidebar_permission_badge():
    """Show the current permission level at the bottom of the sidebar."""
    user = get_current_user()
    uid = user.get("userid")
    if not uid:
        return

    level = get_user_permission(uid)
    icon = "🟢" if level == "Edit" else "🔒"

    with st.sidebar:
        st.markdown("---")
        st.markdown(
            f"<div style='text-align:center; font-size:13px; color:#6b7280;'>"
            f"Access Mode<br>"
            f"<span style='font-size:15px; font-weight:700; color:#111827;'>"
            f"{icon} {level}</span></div>",
            unsafe_allow_html=True,
        )
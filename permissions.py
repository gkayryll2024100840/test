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
    """Show the current permission level in the sidebar (styled to match the sidebar user card)."""
    user = get_current_user()
    uid = user.get("userid")
    if not uid:
        return

    level = get_user_permission(uid)
    icon = "🟢" if level == "Edit" else "🔒"

    # UI only: small pill instead of the old centred block + divider line
    is_edit = icon == "🟢"
    dot = (
        "<span style='width:8px;height:8px;border-radius:50%;background:#10B981;display:inline-block;'></span>"
        if is_edit else "<span style='font-size:11px;line-height:1;'>🔒</span>"
    )
    pill_bg = "rgba(16,185,129,.12)" if is_edit else "rgba(148,163,184,.16)"
    pill_fg = "#047857" if is_edit else "#475569"

    with st.sidebar:
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;gap:8px;"
            f"font-size:12px;color:var(--ps-muted,#6B7280);padding:2px 2px 0 2px;'>"
            f"<span>Access mode</span>"
            f"<span style='display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;"
            f"background:{pill_bg};color:{pill_fg};font-weight:600;font-size:12px;'>{dot}{level}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
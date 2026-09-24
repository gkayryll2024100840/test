import json
import os
import streamlit as st
from db_connect import (
    get_system_logs,
    trigger_data_sync,
    check_column_exists,
    refresh_schema_cache,
    get_schema_load_error,
    search_users,
    get_user_permission,
    set_user_permission,
)
from system_log import get_system_logs_local
from field_mapping import load_mappings, save_mappings
from permissions import require_edit

st.title("Admin Configuration")
st.markdown("---")

# ============================================================
# FIELD MAPPING CONFIGURATION SECTION
# ============================================================
CONFIG_FILE = "field_mappings.json"

st.subheader("Field Mapping (US-10)")
st.markdown("Maps dashboard fields to IFT200's normalized schema — no code changes required to repoint for a new program.")

if st.button("Re-check schema"):
    require_edit()
    refresh_schema_cache()

schema_error = get_schema_load_error()
if schema_error:
    st.error(f"Could not read the database schema, so no mapping can be verified: {schema_error}")

if "current_mappings" not in st.session_state:
    st.session_state["current_mappings"] = load_mappings()

updated_mappings = {}
validation_errors = []

for field_label, db_column in st.session_state["current_mappings"].items():
    col1, col2, col3 = st.columns([3, 5, 2])

    with col1:
        st.write(f"**{field_label}**")

    with col2:
        new_column = st.text_input(
            f"Column for {field_label}",
            value=db_column,
            label_visibility="collapsed",
            key=f"input_{field_label}",
        )
        updated_mappings[field_label] = new_column.strip()

    with col3:
        typed_path = new_column.strip()
        column_exists = check_column_exists(typed_path)
        toggle_key = f"toggle_{field_label}"
        st.session_state[toggle_key] = column_exists
        st.toggle("Mapped", key=toggle_key, disabled=True)

        if not column_exists:
            validation_errors.append(field_label)

st.markdown("---")

col_save, col_status = st.columns([1, 3])

with col_save:
    save_clicked = st.button("Save Mappings", type="primary")

if save_clicked:
    require_edit()                # US-13 gate
    save_mappings(updated_mappings)
    st.session_state["current_mappings"] = updated_mappings

with col_status:
    if save_clicked and validation_errors:
        st.warning(
            "Saved with errors! Note: Roster view will be disabled until resolved. "
            f"Fix: {', '.join(validation_errors)}"
        )
    elif save_clicked:
        st.success("Configurations successfully saved!")
    elif validation_errors:
        st.warning(
            "Configuration has errors and cannot go live until resolved: "
            f"{', '.join(validation_errors)}"
        )
    else:
        st.success("All mappings valid and ready for production deployment.")


# ============================================================
# USER PERMISSIONS SECTION (US-13)
# ============================================================
st.markdown("---")
st.subheader("User Permissions")
st.markdown("Set a user's permission level to **Edit** (can make changes) or **View Only** (read-only; write attempts are blocked and logged).")

search_query = st.text_input(
    "Search user by name or ID",
    placeholder="e.g. Juan, dela Cruz, or 2024-10012",
    key="perm_search",
)

users = search_users(search_query)

if not users:
    st.info("No users match this search.")
else:
    st.caption(f"Showing {len(users)} user(s).")
    for u in users:
        cols = st.columns([2, 2, 1.4, 1.6])

        with cols[0]:
            st.write(f"**{u['UserID']}**")
        with cols[1]:
            st.write(f"{u['FirstName']} {u['LastName']}")
        with cols[2]:
            st.write(f"{u['Role']}")
        with cols[3]:
            current = u.get("RolePermission") or "View Only"
            idx = 0 if current == "View Only" else 1
            new_perm = st.selectbox(
                f"Permission for {u['UserID']}",
                ["View Only", "Edit"],
                index=idx,
                key=f"perm_{u['UserID']}",
                label_visibility="collapsed",
            )

            if new_perm != current:
                if st.button("Save", key=f"save_{u['UserID']}"):
                    require_edit()   # only IT/Admin has Edit
                    ok, err = set_user_permission(u["UserID"], new_perm)
                    if ok:
                        st.success(f"{u['UserID']} → {new_perm}")
                        st.rerun()
                    else:
                        st.error(f"Failed: {err}")


# ============================================================
# PERMISSION AUDIT LOG SECTION (US-13)
# ============================================================
st.markdown("---")
st.subheader("Permission Audit Log")
st.markdown("Every blocked write attempt by a **View Only** user is recorded here.")

try:
    from db_connect import get_db_connection
    _conn = get_db_connection()
    _cur = _conn.cursor(dictionary=True)
    _cur.execute(
        """SELECT pal.LogID, pal.UserID,
                  CONCAT(u.FirstName, ' ', u.LastName) AS Name,
                  u.Role AS Role,
                  pal.LoggedAt
           FROM Permission_Audit_Log pal
           LEFT JOIN Users u ON u.UserID = pal.UserID
           ORDER BY pal.LoggedAt DESC
           LIMIT 100"""
    )
    audit_rows = _cur.fetchall()
    _cur.close()
    _conn.close()

    if audit_rows:
        st.dataframe(audit_rows, use_container_width=True)
    else:
        st.caption("No blocked attempts recorded yet.")
except Exception as e:
    st.warning(f"Could not load audit log: {e}")


# ============================================================
# SYSTEM SYNC LOGS SECTION
# ============================================================
st.markdown("---")
st.subheader("System Sync Logs")

active_login_id = st.session_state.get("session_id", "default_admin")
st.info(f"Active Session ID for this browser: **{active_login_id}**")

if st.button("Run Sync Attempt"):
    # Sync is a read-only operation — no permission gate needed
    success = trigger_data_sync(login_id=active_login_id)
    if success:
        st.success("Sync executed successfully!")
        st.rerun()
    else:
        st.error("Sync failed! Error logged to SQL Local_Logs table.")
        st.rerun()

logs = get_system_logs_local()

if logs:
    st.dataframe(logs, use_container_width=True)
else:
    st.info("No system logs found in the local_logs.db")
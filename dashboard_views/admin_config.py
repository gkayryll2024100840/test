# ADMIN_CONFIG 9-28-26

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

HEADER_CSS = """<style>
/* ---- page header: copied from the Executive Overview header ---- */
.stApp{--ac-h-text:#0F172A; --ac-h-label:#4B5563; --ac-h-border:#E5E7EB;}
html[data-eo-theme="dark"] .stApp{--ac-h-text:#F1F5F9; --ac-h-label:#94A3B8; --ac-h-border:#263044;}
.ac-title{font-size:2.75rem !important;font-weight:700 !important;line-height:1.15 !important;color:var(--ac-h-text) !important;
        letter-spacing:-.01em;margin:0 !important;padding:0 !important;opacity:1 !important;}
/* caption under the title: change margin-top to move it closer to / further from the title */
.ac-caption{font-size:14px !important;line-height:1.5 !important;color:var(--ac-h-label) !important;
        margin:4px 0 0 0 !important;padding:0 !important;opacity:1 !important;}
/* title + caption with the line under both (one element = no extra Streamlit gaps) */
.ac-header{padding-bottom:10px;border-bottom:1px solid var(--ac-h-border);margin:0;}
</style>"""

# Title + caption styled like the Executive Overview header (line under both)
st.markdown(HEADER_CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="ac-header">'
    '<div class="ac-title">Admin Configuration</div>'
    '<div class="ac-caption">Manage field mappings, user permissions, and system sync logs.</div>'
    '</div>',
    unsafe_allow_html=True,
)

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
# KPI TILES (US-29) — stored as JSON on Program.KpiTiles
# ============================================================
from db_connect import (
    get_all_programs,
    get_all_kpi_tiles,
    save_kpi_tiles,
    reset_kpi_tiles,
)

st.markdown("---")
st.subheader("KPI Tiles")
st.markdown(
    "Configure the tiles shown on the Executive Overview. "
    "Tiles are stored per program. Programs with no custom set — including any program "
    "created later from the Student Roster — fall back to the built-in defaults."
)

programs = get_all_programs(active_only=False)
if not programs:
    st.info("No programs available yet.")
else:
    prog_choice = st.selectbox(
        "Program",
        programs,
        format_func=lambda p: f"{p['ProgramCode']} — {p['ProgramName']}",
        key="kpi_program",
    )
    pid = prog_choice["ProgramID"]

    tiles = get_all_kpi_tiles(program_id=pid)

    # ----- Edit existing tiles -----
    for i, t in enumerate(tiles):
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 1.2, 1.2, 1.2, 1])
            with c1:
                t["label"] = st.text_input("Label", value=t.get("label", ""), key=f"kpi_l_{i}")
            with c2:
                st.text_input("Source", value=t.get("source", ""), disabled=True, key=f"kpi_s_{i}")
            with c3:
                t["visible"] = st.checkbox(
                    "Visible", value=bool(t.get("visible", True)), key=f"kpi_v_{i}"
                )
            with c4:
                t["order"] = st.number_input(
                    "Order", value=int(t.get("order", i + 1)),
                    step=1, min_value=0, key=f"kpi_o_{i}"
                )
            with c5:
                t["color"] = st.color_picker(
                    "Accent", value=t.get("color", "#1F3864"), key=f"kpi_c_{i}"
                )
            with c6:
                st.write("")
                if st.button("Delete", key=f"kpi_d_{i}"):
                    require_edit()
                    tiles.pop(i)
                    ok, err = save_kpi_tiles(pid, tiles)
                    if ok:
                        st.success("Removed.")
                        st.rerun()
                    else:
                        st.error(err)

    # ----- Save / reset -----
    col_a, col_b, col_c = st.columns([1, 1, 3])
    with col_a:
        if st.button("Save Tiles", type="primary", key="kpi_save_all"):
            require_edit()
            ok, err = save_kpi_tiles(pid, tiles)
            if ok:
                st.success("Saved.")
                st.rerun()
            else:
                st.error(err)
    with col_b:
        if st.button("Reset to Defaults", key="kpi_reset"):
            require_edit()
            ok, err = reset_kpi_tiles(pid)
            if ok:
                st.success("Reset.")
                st.rerun()
            else:
                st.error(err)

    # ----- Add a new tile -----
    st.markdown("#### Add a Tile")
    with st.form("kpi_add"):
        a1, a2, a3, a4 = st.columns([2, 3, 2, 1])
        with a1:
            new_key = st.text_input("Key (unique)", placeholder="retention_rate")
        with a2:
            new_label = st.text_input("Label", placeholder="Retention Rate")
        with a3:
            new_source = st.selectbox("Source", [
                "total_enrolled", "remaining", "at_risk",
                "on_time_rate", "overall_completion", "completion_rate",
                "cohort_count", "program_label", "student_count",
            ])
        with a4:
            new_color = st.color_picker("Accent", "#1F3864")

        new_visible = st.checkbox("Visible", value=True)

        if st.form_submit_button("Add"):
            require_edit()
            if not new_key or not new_label:
                st.warning("Both Key and Label are required.")
            else:
                tiles.append({
                    "key": new_key.strip().lower().replace(" ", "_"),
                    "label": new_label.strip(),
                    "source": new_source,
                    "order": len(tiles) + 1,
                    "visible": new_visible,
                    "color": new_color,
                })
                ok, err = save_kpi_tiles(pid, tiles)
                if ok:
                    st.success(f"Added **{new_label}**.")
                    st.rerun()
                else:
                    st.error(err)
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

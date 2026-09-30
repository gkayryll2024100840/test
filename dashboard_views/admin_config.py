# ADMIN CONFIG.PY 9-29-26
#
# SPEED NOTES
#  - Each section is an @st.fragment: clicking/typing in one section only re-runs THAT section,
#    not the whole page (before, every click re-ran every section + every database query).
#  - Database reads are cached for a short time and the cache is cleared right after a save,
#    so what you see is always up to date after a change.
#  - The user list shows USERS_PER_PAGE users at a time instead of building up to 200 rows of widgets.

import streamlit as st
from datetime import datetime, time as dtime
from db_connect import (
    trigger_data_sync,
    check_column_exists,
    refresh_schema_cache,
    get_schema_load_error,
    search_users,
    set_user_permission,
    get_db_connection,
    get_all_programs, get_program_threshold, set_program_threshold,
    get_refresh_schedule, set_refresh_time,
)
from system_log import get_system_logs_local
from field_mapping import load_mappings, save_mappings
from permissions import require_edit

USERS_PER_PAGE = 20

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

/* ---- section heading + description (e.g. "Field Mapping (US-10)") ----
   padding-top = space between the page's line and the section title (same as Executive Overview's line -> filters)
   description sits 4px under the title, same size/colour as the page caption */
.ac-section{padding-top:32px;padding-bottom:32px;margin:0;}
/* line between sections: same thin line as the page header's, no extra Streamlit hr margins,
   so every section sits the same distance below its line as Field Mapping does */
.ac-divider{border-top:1px solid var(--ac-h-border);margin:0;height:0;}
/* table column headers (User Permissions) */
.ac-th{font-size:12px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:#6B7280;}
html[data-eo-theme="dark"] .ac-th{color:#94A3B8;}
.ac-th-line{border-top:1px solid var(--ac-h-border);margin:-8px 0 0 0;height:0;}

/* Re-check schema + Save Mappings in one row, left-aligned */
.st-key-ac_actions{display:flex !important;flex-direction:row !important;flex-wrap:wrap;align-items:center !important;
        justify-content:flex-start !important;gap:12px !important;}
.st-key-ac_actions [data-testid="stElementContainer"]{width:auto !important;flex:0 0 auto !important;}
.ac-section-title{font-size:1.75rem !important;font-weight:600 !important;line-height:1.2 !important;
        color:var(--ac-h-text) !important;margin:0 !important;padding:0 !important;}
.ac-sub{font-size:16px;font-weight:600;color:var(--ac-h-text);margin:0;}
.ac-sub-gap{height:20px;}
.ac-section-caption{font-size:14px !important;line-height:1.5 !important;color:var(--ac-h-label) !important;
        margin:4px 0 0 0 !important;padding:0 !important;}
</style>"""



def section_divider():
    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)


def section_header(title, description):
    """Section title with its description right under it (one element, so no extra Streamlit gaps)."""
    st.markdown(
        f'<div class="ac-section"><div class="ac-section-title">{title}</div>'
        f'<div class="ac-section-caption">{description}</div></div>',
        unsafe_allow_html=True,
    )


def current_user_id():
    user = st.session_state.get("user", {}) or {}
    return user.get("userid") or user.get("UserID")


# ---------------------------------------------------------------------------
# Cached reads (short TTL; cleared right after the matching save)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def cached_programs():
    return get_all_programs() or []


@st.cache_data(ttl=60, show_spinner=False)
def cached_threshold(program_id):
    return get_program_threshold(program_id)


@st.cache_data(ttl=60, show_spinner=False)
def cached_schedule():
    return get_refresh_schedule()


@st.cache_data(ttl=30, show_spinner=False)
def cached_users(query):
    return search_users(query)


@st.cache_data(ttl=30, show_spinner=False)
def cached_audit_rows():
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT pal.LogID, pal.UserID,
                      CONCAT(u.FirstName, ' ', u.LastName) AS Name,
                      u.Role AS Role,
                      pal.LoggedAt
               FROM Permission_Audit_Log pal
               LEFT JOIN Users u ON u.UserID = pal.UserID
               ORDER BY pal.LoggedAt DESC
               LIMIT 100"""
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return rows


# Title + caption styled like the Executive Overview header (line under both)
st.markdown(HEADER_CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="ac-header">'
    '<div class="ac-title">Admin Configuration</div>'
    '<div class="ac-caption">Manage field mappings, program thresholds, refresh schedule, user permissions, '
    'and system sync logs.</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================
# FIELD MAPPING CONFIGURATION SECTION
# ============================================================
CONFIG_FILE = "field_mappings.json"

section_header(
    "Field Mapping",
    "Tells the dashboard which database column holds each piece of student data. "
    "A field shows <b>Mapped</b> when its column is found in the database, so you can confirm "
    "everything is connected correctly before saving.",
)


@st.fragment
def field_mapping_section():
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
            column_exists = check_column_exists(typed_path)   # in-memory lookup (schema snapshot)
            toggle_key = f"toggle_{field_label}"
            st.session_state[toggle_key] = column_exists
            st.toggle("Mapped", key=toggle_key, disabled=True)

            if not column_exists:
                validation_errors.append(field_label)

    st.markdown("---")

    col_save, col_status = st.columns([1.3, 3])

    with col_save:
        # Re-check schema + Save Mappings side by side, starting at the page's left margin
        with st.container(key="ac_actions"):
            recheck_clicked = st.button("Re-check schema", key="ac_recheck")
            save_clicked = st.button("Save Mappings", type="primary", key="ac_save")

    if recheck_clicked:
        require_edit()
        refresh_schema_cache()
        st.rerun(scope="fragment")   # redraw this section so the Mapped switches use the fresh schema

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


field_mapping_section()


# ============================================================
# PROGRAM-SPECIFIC THRESHOLDS AND TERMINOLOGIES
#   1) At-Risk Threshold (US-27): one number per program, used for every stage
#   2) Data Refresh Schedule: nightly automatic refresh (dashboard-wide)
# ============================================================
section_divider()
section_header(
    "Program-Specific Thresholds and Terminologies",
    "Set each program's At-Risk threshold and when the dashboard's data refreshes automatically. "
    "Changes apply right away.",
)


@st.fragment
def threshold_section():
    st.markdown('<div class="ac-sub">At-Risk Threshold</div>', unsafe_allow_html=True)
    programs = cached_programs()
    if not programs:
        st.info("No programs found.")
        return

    prog_by_label = {f"{p['ProgramCode']} — {p['ProgramName']}": p["ProgramID"] for p in programs}
    th_col_prog, th_col_days, th_col_btn = st.columns([2.2, 1.4, 1], vertical_alignment="bottom")

    with th_col_prog:
        th_label = st.selectbox("Program", list(prog_by_label), key="th_program")
    th_program_id = prog_by_label[th_label]
    th_current = cached_threshold(th_program_id)

    with th_col_days:
        th_days = st.number_input(
            "Days in a single stage",
            min_value=1, step=1,
            value=int(th_current) if th_current else 180,
            key=f"th_days_{th_program_id}",
        )
    with th_col_btn:
        th_save = st.button("Save Threshold", type="primary", key="th_save", use_container_width=True)

    st.caption(
        f"Current threshold for this program: {th_current} days in a single stage."
        if th_current else "No threshold set for this program yet (nobody is flagged until one is saved)."
    )

    if th_save:
        require_edit()   # US-13 gate: View Only users are stopped and the attempt is logged
        ok, msg = set_program_threshold(current_user_id(), th_program_id, int(th_days))
        if ok:
            st.cache_data.clear()   # dashboards (roster / overview) pick up the new flags right away
            st.session_state["th_flash"] = msg
            st.rerun(scope="fragment")   # redraw so "Current threshold" shows the new number
        else:
            st.error(msg)

    th_flash = st.session_state.pop("th_flash", None)
    if th_flash:
        st.success(th_flash)


@st.fragment
def refresh_schedule_section():
    st.markdown('<div class="ac-sub-gap"></div><div class="ac-sub">Data Refresh Schedule</div>',
                unsafe_allow_html=True)
    schedule = cached_schedule()
    cur_h, cur_m = (int(x) for x in schedule["time"].split(":"))
    rf_col_freq, rf_col_time, rf_col_btn = st.columns([2.2, 1.4, 1], vertical_alignment="bottom")
    with rf_col_freq:
        st.selectbox("Frequency", ["Nightly (every day)"], disabled=True, key="rf_freq",
                     help="The refresh runs once every night at the time on the right.")
    with rf_col_time:
        rf_time = st.time_input(f"Refresh time ({schedule['timezone']})", value=dtime(cur_h, cur_m),
                                step=900, key="rf_time")
    with rf_col_btn:
        rf_save = st.button("Save Schedule", type="primary", key="rf_save", use_container_width=True)

    last_run_txt = "not run yet"
    if schedule["last_run"]:
        try:
            last_run_txt = datetime.strptime(schedule["last_run"], "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y · %I:%M %p")
        except ValueError:
            last_run_txt = schedule["last_run"]
        if schedule["last_status"]:
            last_run_txt += f" ({schedule['last_status']})"
    st.caption(
        f"Current schedule: nightly at {schedule['time']} ({schedule['timezone']}). "
        f"Last scheduled refresh: {last_run_txt}. Failed refreshes are recorded in System Sync Logs below. "
        "For urgent updates, use Refresh Now in the sidebar or Run Sync Attempt below."
    )

    if rf_save:
        require_edit()   # US-13 gate
        ok, msg = set_refresh_time(current_user_id(), rf_time.strftime("%H:%M"))
        if ok:
            cached_schedule.clear()
            st.session_state["rf_flash"] = msg
            st.rerun(scope="fragment")
        else:
            st.error(msg)

    rf_flash = st.session_state.pop("rf_flash", None)
    if rf_flash:
        st.success(rf_flash)


threshold_section()
refresh_schedule_section()

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
section_divider()
section_header(
    "User Permissions",
    "Set a user's permission level to <b>Edit</b> (can make changes) or <b>View Only</b> "
    "(read-only; write attempts are blocked and logged).",
)


@st.fragment
def user_permissions_section():
    search_query = st.text_input(
        "Search User by Name or UserID",
        placeholder="e.g. Juan, dela Cruz, or 2024-10012",
        key="perm_search",
    )

    users = cached_users(search_query.strip())

    if not users:
        st.info("No users match this search.")
        return

    # show USERS_PER_PAGE at a time (building 200 rows of widgets on every click was the slowest part)
    n_pages = max(1, -(-len(users) // USERS_PER_PAGE))
    page = 1
    if n_pages > 1:
        pg_col, _ = st.columns([1, 5])
        with pg_col:
            page = st.number_input(f"Page (of {n_pages})", min_value=1, max_value=n_pages, value=1,
                                   step=1, key=f"perm_page_{search_query}")
    page_users = users[(page - 1) * USERS_PER_PAGE: page * USERS_PER_PAGE]

    # column headers (same look as the Student Roster / Executive Overview table headers)
    perm_widths = [2, 2, 1.4, 1.6]
    for col, label in zip(st.columns(perm_widths, vertical_alignment="bottom"),
                          ["UserID", "Name", "Role", "Permission"]):
        col.markdown(f'<div class="ac-th">{label}</div>', unsafe_allow_html=True)
    st.markdown('<div class="ac-th-line"></div>', unsafe_allow_html=True)

    for u in page_users:
        cols = st.columns(perm_widths)

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
                        cached_users.clear()
                        st.rerun(scope="fragment")
                    else:
                        st.error(f"Failed: {err}")

    if n_pages > 1:
        st.caption(f"Showing {len(page_users)} of {len(users)} users.")


user_permissions_section()


# ============================================================
# PERMISSION AUDIT LOG SECTION (US-13)
# ============================================================
section_divider()
section_header(
    "Permission Audit Log",
    "Every blocked write attempt by a <b>View Only</b> user is recorded here.",
)

try:
    audit_rows = cached_audit_rows()
    if audit_rows:
        st.dataframe(audit_rows, use_container_width=True)
    else:
        st.caption("No blocked attempts recorded yet.")
except Exception as e:
    st.warning(f"Could not load audit log: {e}")


# ============================================================
# SYSTEM SYNC LOGS SECTION
# ============================================================
section_divider()
section_header(
    "System Sync Logs",
    "Run a test sync and review past sync attempts, including any errors, for troubleshooting.",
)


@st.fragment
def sync_logs_section():
    active_login_id = st.session_state.get("session_id", "default_admin")
    st.info(f"Active Session ID for this browser: **{active_login_id}**")

    if st.button("Run Sync Attempt"):
        # Sync is a read-only operation — no permission gate needed
        success = trigger_data_sync(login_id=active_login_id)
        if success:
            st.success("Sync executed successfully!")
            st.rerun()   # full page rerun so the sidebar's Live Sync Status updates too
        else:
            st.error("Sync failed! Error logged to SQL Local_Logs table.")
            st.rerun()

    logs = get_system_logs_local()

    if logs:
        st.dataframe(logs, use_container_width=True)
    else:
        st.info("No system logs found in the local_logs.db")


sync_logs_section()
if logs:
    st.dataframe(logs, use_container_width=True)
else:
    st.info("No system logs found in the local_logs.db")

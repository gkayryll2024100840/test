# ADMIN CONFIG.
# UPDATED: PY 10/6/26
#
# SPEED NOTES
#  - Each section is an @st.fragment: clicking/typing in one section only re-runs THAT section,
#    not the whole page (before, every click re-ran every section + every database query).
#  - Database reads are cached for a short time and the cache is cleared right after a save,
#    so what you see is always up to date after a change.
#  - The user list shows USERS_PER_PAGE users at a time instead of building up to 200 rows of widgets.

import html
import pandas as pd
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
    get_stage_labels, set_stage_label, DEFAULT_STAGE_LABELS,
    set_user_program,
)
from system_log import get_system_logs_local
from field_mapping import load_mappings, save_mappings
from permissions import require_edit
from dashboard_views.components import DARK_MODE_CSS, _last_sync_time

USERS_PER_PAGE = 20

HEADER_CSS = """<style>
/* ---- typography guarantee for admin config ---- */
.stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp label,
.ac-title, .ac-caption, .ac-section-title, .ac-section-caption, .ac-sub, .ac-th, .ac-table, .ac-table th, .ac-table td {
    font-family: 'Plus Jakarta Sans', 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
}
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
/* Field Mapping: the "Mapped" switch sits at the right edge of the page */
[class*="st-key-fmtog_"]{align-items:flex-end !important;}
[class*="st-key-fmtog_"] [data-testid="stElementContainer"]{width:auto !important;}
.ac-section-caption{font-size:14px !important;line-height:1.5 !important;color:var(--ac-h-label) !important;
        margin:4px 0 0 0 !important;padding:0 !important;}

/* log tables (Permission Audit Log / System Sync Logs): always the full page width, text left-aligned,
   long messages wrap instead of being cut off, header stays visible while the table scrolls */
.ac-table-wrap{width:100%;overflow:auto;border:1px solid var(--ac-h-border);border-radius:14px;box-shadow:0 1px 3px rgba(16,24,40,.06);}
html[data-eo-theme="dark"] .ac-table-wrap{box-shadow:0 4px 16px -2px rgba(0,0,0,.4);}
.ac-table{width:100%;border-collapse:collapse;font-size:13px;color:var(--ac-h-text);}
.ac-table th{position:sticky;top:0;z-index:1;text-align:left;padding:10px 14px;font-size:11.5px;font-weight:700;
        letter-spacing:.04em;text-transform:uppercase;color:var(--ac-h-label);background:var(--ac-foot-bg,#FAFAFA);
        border-bottom:1px solid var(--ac-h-border);white-space:nowrap;}
.ac-table td{text-align:left;vertical-align:top;padding:9px 14px;border-top:1px solid var(--ac-h-border);
        overflow-wrap:anywhere;}
.ac-table tbody tr:first-child td{border-top:none;}
.ac-table tbody tr{transition:background 120ms ease;}
.ac-table tbody tr:hover td{background:rgba(148,163,184,.10);}

@media (max-width: 1150px) {
  .ac-title { font-size: 2.0rem !important; }
}
@media (max-width: 640px) {
  .ac-title { font-size: 1.55rem !important; line-height: 1.2 !important; }
  .ac-section-title { font-size: 1.35rem !important; }
  .ac-section { padding-top: 20px; padding-bottom: 20px; }
}
@media (max-height: 520px) and (orientation: landscape) {
  .ac-title { font-size: 1.45rem !important; }
  .ac-section { padding-top: 14px; padding-bottom: 14px; }
}
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


def table_html(rows):
    """HTML for a simple full-width table from a list of dicts / rows (None if the rows can't be read)."""
    try:
        df = pd.DataFrame([dict(r) for r in rows])
    except Exception:
        return None
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for rec in df.itertuples(index=False):
        cells = "".join(
            "<td>" + html.escape("" if pd.isna(v) else str(v)).replace("\n", " ").replace("\r", " ") + "</td>"
            for v in rec
        )
        body.append(f"<tr>{cells}</tr>")
    return (f'<div class="ac-table-wrap" style="max-height:440px;"><table class="ac-table">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def show_table(rows):
    """Full-width log table. (st.dataframe stopped short of the page's right edge and right-aligned numbers.)"""
    markup = table_html(rows)
    if markup is None:
        st.dataframe(rows, use_container_width=True, hide_index=True)   # unknown row format: plain fallback
    else:
        st.markdown(markup, unsafe_allow_html=True)


def current_user_id():
    user = st.session_state.get("user", {}) or {}
    return user.get("userid") or user.get("UserID")
# ------------------------------------------------------------
# US-42: honor ?program=<ProgramID> from the Program Instances console
# ------------------------------------------------------------
_incoming_program = st.query_params.get("program")
if _incoming_program:
    try:
        st.session_state["pi_target_program"] = int(_incoming_program)
    except (TypeError, ValueError):
        st.session_state.pop("pi_target_program", None)

# ---------------------------------------------------------------------------
# Cached reads (cleared right after the matching save, so longer TTLs are safe)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def cached_programs():
    return get_all_programs() or []


@st.cache_data(ttl=300, show_spinner=False)
def cached_threshold(program_id):
    return get_program_threshold(program_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_schedule():
    return get_refresh_schedule()


@st.cache_data(ttl=120, show_spinner=False)
def cached_users(query):
    return search_users(query)


@st.cache_data(ttl=60, show_spinner=False)
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
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)
st.markdown(HEADER_CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="ac-header">'
    '<div class="ac-title">Admin Config</div>'
    '<div class="ac-caption">Field mappings, program-specific thresholds and terminologies, dashboard tiles, '
    'user permissions and sync logs. Changes apply right away.</div>'
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
        # label | input (wide) | Mapped switch pushed to the right edge, lined up with the cards' Save buttons
        col1, col2, col3 = st.columns([2.2, 7, 1.1], vertical_alignment="center")

        with col1:
            st.markdown(f"**{field_label}**")

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
            with st.container(key=f"fmtog_{field_label.replace(' ', '_')}"):
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
        st.cache_data.clear()         # Student Roster / Profile re-check the mappings right away
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
# PROGRAM INSTANCES CONSOLE (US-42)
# ============================================================
from db_connect import get_program_instances, set_program_owner


@st.cache_data(ttl=60, show_spinner=False)
def cached_program_instances():
    return get_program_instances() or []


section_divider()
st.markdown('<div style="height:32px;"></div>', unsafe_allow_html=True)

# Program | Owner | Chair | Students | Status  (the ⚙ Configure column was removed)
PI_WIDTHS = [2.4, 2.3, 2.3, 0.9, 1.1]


@st.fragment
def program_instances_section():
    instances = cached_program_instances()
    total = len(instances)
    active_n = sum(1 for r in instances if r.get("IsActive"))

    # cached user list (shared by every row's pickers -> one DB read per page, not per program)
    all_users = cached_users("") or []
    user_labels = {f"{u['FirstName']} {u['LastName']} ({u['UserID']})": u["UserID"] for u in all_users}
    options = ["— Unassigned —"] + list(user_labels)

    def label_for(uid):
        return next((lbl for lbl, u in user_labels.items() if u == uid), "— Unassigned —")

    with st.container(key="accard_programs"):
        with st.container(key="achead_programs"):
            c_title, c_stats = st.columns([2.6, 1.1], vertical_alignment="top")
            with c_title:
                st.markdown(
                    '<div class="ac-card-title">Program Instances</div>'
                    '<div class="ac-card-desc">Every program on the platform. Assign its owner and program chair.</div>',
                    unsafe_allow_html=True,
                )
            with c_stats:
                st.markdown(
                    f'<div class="ac-stats"><span><b>{total}</b> programs</span>'
                    f'<span><b>{active_n}</b> active</span><span><b>{total - active_n}</b> inactive</span></div>',
                    unsafe_allow_html=True,
                )

        with st.container(key="acbody_programs"):
            if not instances:
                st.info("No program instances exist yet. Create one from the Student Roster's Active Program panel.")
                return

            for col, label in zip(st.columns(PI_WIDTHS, vertical_alignment="bottom"),
                                  ["Program", "Owner", "Program Chair", "Students", "Status"]):
                col.markdown(f'<div class="ac-th2">{label}</div>', unsafe_allow_html=True)

            for inst in instances:
                pid = inst["ProgramID"]
                cur_owner, cur_chair = label_for(inst.get("OwnerUserID")), label_for(inst.get("ChairUserID"))
                with st.container(key=f"pirow_{pid}"):
                    c_prog, c_owner, c_chair, c_n, c_status = st.columns(PI_WIDTHS, vertical_alignment="center")
                    with c_prog:
                        created = inst["CreatedAt"].strftime("%b %d, %Y") if inst.get("CreatedAt") else None
                        st.markdown(
                            f'<div class="ac-prog"><span class="ac-tag">{html.escape(str(inst["ProgramCode"]))}</span>'
                            f'{html.escape(str(inst["ProgramName"]))}</div>'
                            + (f'<div class="ac-prog-sub">Created {created}</div>' if created else ""),
                            unsafe_allow_html=True,
                        )
                    with c_owner:
                        st.markdown('<div class="ac-mlabel">Owner</div>', unsafe_allow_html=True)   # phones only
                        picked = st.selectbox(f"Owner for {pid}", options, index=options.index(cur_owner),
                                              key=f"owner_pick_{pid}", label_visibility="collapsed")
                        # Owner (Program.OwnerUserID): Save shows up when the pick changed
                        if picked != cur_owner and st.button("Save", key=f"owner_save_{pid}",
                                                             use_container_width=True):
                            require_edit()
                            new_uid = None if picked.startswith("—") else user_labels.get(picked)
                            ok, err = set_program_owner(pid, new_uid)
                            if ok:
                                cached_program_instances.clear()
                                st.session_state["pi_flash"] = (True, f"Owner updated for {inst['ProgramCode']}.")
                                st.rerun(scope="fragment")
                            else:
                                st.session_state["pi_flash"] = (False, err)
                                st.rerun(scope="fragment")
                    with c_chair:
                        chair_uid = inst.get("ChairUserID")
                        st.markdown('<div class="ac-mlabel">Program Chair</div>', unsafe_allow_html=True)   # phones only
                        chair_pick = st.selectbox(f"Chair for {pid}", options, index=options.index(cur_chair),
                                                  key=f"chair_pick_{pid}", label_visibility="collapsed")
                        # Chair (Users.CurrentProgramID): Assign shows up when the pick changed
                        if chair_pick != cur_chair and st.button("Assign", key=f"chair_save_{pid}",
                                                                 use_container_width=True):
                            require_edit()
                            new_uid = None if chair_pick.startswith("—") else user_labels.get(chair_pick)
                            # Clear the previous chair's CurrentProgramID (so they don't stay locked to this program)
                            if chair_uid and chair_uid != new_uid:
                                set_user_program(chair_uid, None)
                            ok, err = set_user_program(new_uid, pid) if new_uid else (True, None)
                            if ok:
                                st.cache_data.clear()
                                st.session_state["pi_flash"] = (True, f"Chair updated for {inst['ProgramCode']}.")
                                st.rerun(scope="fragment")
                            else:
                                st.session_state["pi_flash"] = (False, err)
                                st.rerun(scope="fragment")
                    with c_n:
                        st.markdown(f'<span class="ac-mlabel-in">Students</span>'   # label: phones only
                                    f'<span class="ac-num">{int(inst.get("StudentCount") or 0):,}</span>',
                                    unsafe_allow_html=True)
                    with c_status:
                        st.markdown('<span class="ac-mlabel-in">Status</span>'   # label: phones only
                                    + ('<span class="ac-pill ac-pill-ok">Active</span>' if inst.get("IsActive") else
                                       '<span class="ac-pill ac-pill-warn">Inactive</span>'), unsafe_allow_html=True)

            flash = st.session_state.pop("pi_flash", None)
            if flash:
                (st.success if flash[0] else st.error)(flash[1])


program_instances_section()
# ============================================================
# PROGRAM-SPECIFIC THRESHOLDS AND TERMINOLOGIES (card layout)
#   1) At-Risk Threshold (US-27): one number per program, used for every stage
#   2) Data Refresh Schedule: nightly automatic refresh (dashboard-wide)
#   3) Stage Labels (US-30): program-specific names for each stage
#   4) KPI Tiles (US-29): tiles shown on the Executive Overview, per program
#
#   Each card = st.container with keys:  accard_<name>  (the card)
#                                        achead_<name>  (title + description, line under it)
#                                        acbody_<name>  (the inputs)
#                                        acfoot_<name>  (grey bar with the save button)
#   The CSS for these keys is in CARD_CSS below.
# ============================================================
from db_connect import (
    get_all_kpi_tiles,
    save_kpi_tiles,
    reset_kpi_tiles,
)

CARD_CSS = """<style>
.stApp{--ac-card-bg:#FFFFFF; --ac-foot-bg:#FAFAFA; --ac-soft-bg:#F7F8FA; --ac-chip-bg:#F3F4F6;}
html[data-eo-theme="dark"] .stApp{--ac-card-bg:#161D2B; --ac-foot-bg:#1B2333; --ac-soft-bg:#1B2333; --ac-chip-bg:#1E293B;}

/* section label above the cards */
.ac-eyebrow{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#6B7280;
        margin:36px 0 14px 0;}
html[data-eo-theme="dark"] .ac-eyebrow{color:#94A3B8;}

/* card frame */
[class*="st-key-accard_"]{background:var(--ac-card-bg);border:1px solid var(--ac-h-border);border-radius:14px;
        box-shadow:0 1px 3px rgba(16,24,40,.06), 0 1px 2px rgba(16,24,40,.04);
        overflow:hidden;gap:0 !important;transition:box-shadow 200ms ease;}
html[data-eo-theme="dark"] [class*="st-key-accard_"]{box-shadow:0 4px 16px -2px rgba(0,0,0,.4);}
[class*="st-key-achead_"]{padding:24px 28px 20px 28px;border-bottom:1px solid var(--ac-h-border);gap:4px !important;}
[class*="st-key-acbody_"]{padding:24px 28px 24px 28px;gap:14px !important;}
[class*="st-key-acfoot_"]{padding:14px 28px;background:var(--ac-foot-bg);border-top:1px solid var(--ac-h-border);}
.ac-card-title{font-size:20px;font-weight:700;color:var(--ac-h-text);margin:0;line-height:1.3;display:block !important;width:100% !important;}
.ac-card-desc{font-size:14px;color:var(--ac-h-label);margin:4px 0 0 0;line-height:1.5;display:block !important;width:100% !important;}
.ac-foot-note{font-size:14px;color:var(--ac-h-label);}
.ac-foot-note b{color:var(--ac-h-text);}
.ac-field-label{font-size:14px;font-weight:600;color:var(--ac-h-text);margin:0 0 6px 0;
        display:flex;align-items:center;gap:8px;line-height:1.3;}
.ac-field-label .ac-tag{margin-right:0;}
.ac-suffix{font-size:14px;color:var(--ac-h-label);}
.ac-hint{font-size:13px;color:var(--ac-h-label);line-height:1.55;}

/* two cards side by side: same height, footer pinned to the bottom */
.st-key-ac_pair [data-testid="stHorizontalBlock"]{align-items:stretch !important;}
.st-key-ac_pair [data-testid="stColumn"] > div{height:100%;}
.st-key-ac_pair [data-testid="stColumn"] [class*="st-key-accard_"]{height:100%;display:flex;flex-direction:column;}
.st-key-ac_pair [data-testid="stColumn"] [class*="st-key-acbody_"]{flex:1 1 auto;}

/* compact cards (threshold / refresh): no header line, no footer */
.st-key-acbody_threshold,.st-key-acbody_refresh{padding:22px 26px 20px 26px !important;gap:10px !important;}
.st-key-acbody_threshold .ac-card-desc,.st-key-acbody_refresh .ac-card-desc{margin-bottom:6px;}
.ac-note{font-size:13px;color:var(--ac-h-label);display:flex;align-items:center;gap:8px;}
.ac-note-sm{font-size:12px;color:var(--ac-h-label);margin-top:-6px;}
.ac-dot{width:7px;height:7px;border-radius:50%;display:inline-block;}
.ac-dot-ok{background:#16A34A;} .ac-dot-fail{background:#DC2626;}
.ac-tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.04em;color:var(--ac-h-label);
        background:var(--ac-chip-bg);border-radius:5px;padding:2px 7px;margin-right:8px;}

/* KPI tiles table */
.ac-th2{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#6B7280;white-space:nowrap !important;}
html[data-eo-theme="dark"] .ac-th2{color:#94A3B8;}
.st-key-ac_permtable [data-testid="stColumn"]{white-space:nowrap !important;}
[class*="st-key-kpirow_"]{border-bottom:1px solid var(--ac-h-border);padding:6px 0;}
[class*="st-key-kpiord_"]{border:1px solid var(--ac-h-border);border-radius:8px;background:var(--ac-soft-bg);
        padding:0 4px;}
[class*="st-key-kpiord_"] [data-testid="stHorizontalBlock"]{gap:0 !important;align-items:center;}
[class*="st-key-kpiord_"] button{min-height:34px !important;padding:0 6px !important;}
.ac-ord-num{font-weight:700;color:var(--ac-h-text);text-align:center;font-size:14px;}
.ac-chip{display:inline-block;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;
        background:var(--ac-chip-bg);border:1px solid var(--ac-h-border);border-radius:6px;padding:3px 8px;
        color:var(--ac-h-label);}
[class*="st-key-kpidel_"] button{color:#B91B21 !important;}
[class*="st-key-kpidel_"] button p{color:#B91B21 !important;font-size:16px;}
[class*="st-key-kpiadd_"]{border:1px dashed var(--ac-h-border);border-radius:12px;padding:16px 20px;
        background:var(--ac-foot-bg);margin-top:10px;}
[class*="st-key-kpiadd_"] label, [class*="st-key-kpiadd_"] label p{white-space:nowrap !important;}
.ac-add-title{font-size:16px;font-weight:700;color:var(--ac-h-text);margin:0;}
/* Program Instances + Backup cards (same look as the KPI tiles table) */
[class*="st-key-pirow_"],[class*="st-key-bkrow_"]{border-bottom:1px solid var(--ac-h-border);padding:6px 0;}
[class*="st-key-bkrow_"]{padding:10px 0;}
.ac-prog{font-size:14px;font-weight:600;color:var(--ac-h-text);line-height:1.4;}
.ac-prog-sub{font-size:12px;color:var(--ac-h-label);margin-top:2px;}
.ac-num{font-size:14px;font-weight:600;color:var(--ac-h-text);}
.ac-cell{font-size:14px;color:var(--ac-h-text);}
.ac-cell-muted{font-size:13px;color:var(--ac-h-label);}
.ac-pill{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:3px 10px;border:1px solid;
        white-space:nowrap;}
.ac-pill-ok{color:#15803D;background:#ECFDF3;border-color:#BBF7D0;}
.ac-pill-warn{color:#B45309;background:#FFFBEB;border-color:#FDE68A;}
.ac-pill-info{color:#1D4ED8;background:#EFF6FF;border-color:#BFDBFE;}
.ac-pill-muted{color:#4B5563;background:#F3F4F6;border-color:#E5E7EB;}
html[data-eo-theme="dark"] .ac-pill-ok{color:#34D399;background:rgba(16,185,129,.15);border-color:rgba(16,185,129,.3);}
html[data-eo-theme="dark"] .ac-pill-warn{color:#FCD34D;background:rgba(245,158,11,.14);border-color:rgba(245,158,11,.3);}
html[data-eo-theme="dark"] .ac-pill-info{color:#93C5FD;background:rgba(59,130,246,.15);border-color:rgba(59,130,246,.3);}
html[data-eo-theme="dark"] .ac-pill-muted{color:#CBD5E1;background:rgba(148,163,184,.12);border-color:rgba(148,163,184,.24);}
.ac-stats{display:flex;justify-content:flex-end;gap:18px;font-size:13px;color:var(--ac-h-label);padding-top:6px;}
.ac-stats b{color:var(--ac-h-text);font-size:16px;margin-right:3px;}
.st-key-bkrestore{border:1px dashed var(--ac-h-border);border-radius:12px;padding:16px 20px;
        background:var(--ac-foot-bg);margin-top:10px;gap:10px !important;}
/* Tablet: keep the pair side by side but tighter */
@media (max-width: 1150px) and (min-width: 641px) {
  .st-key-ac_pair [data-testid="stHorizontalBlock"] { gap: 12px !important; }
  [class*="st-key-achead_"] { padding: 20px 22px 16px 22px !important; }
  [class*="st-key-acbody_"] { padding: 20px 22px 20px 22px !important; }
}

/* Mobile: stack the pair; every card full-width */
@media (max-width: 640px) {
  .st-key-ac_pair [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 16px !important;
  }
  .st-key-ac_pair [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
  /* KPI tiles editor: switch to stacked rows */
  [class*="st-key-kpirow_"] [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap:

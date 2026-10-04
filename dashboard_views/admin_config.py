# ADMIN CONFIG.
# UPDATED: PY 10/4/26
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
    set_user_program,   # US-30
)
from system_log import get_system_logs_local
from field_mapping import load_mappings, save_mappings
from permissions import require_edit
from dashboard_views.components import _last_sync_time

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
/* Field Mapping: the "Mapped" switch sits at the right edge of the page */
[class*="st-key-fmtog_"]{align-items:flex-end !important;}
[class*="st-key-fmtog_"] [data-testid="stElementContainer"]{width:auto !important;}
.ac-section-caption{font-size:14px !important;line-height:1.5 !important;color:var(--ac-h-label) !important;
        margin:4px 0 0 0 !important;padding:0 !important;}

/* log tables (Permission Audit Log / System Sync Logs): always the full page width, text left-aligned,
   long messages wrap instead of being cut off, header stays visible while the table scrolls */
.ac-table-wrap{width:100%;overflow:auto;border:1px solid var(--ac-h-border);border-radius:10px;}
.ac-table{width:100%;border-collapse:collapse;font-size:13px;color:var(--ac-h-text);}
.ac-table th{position:sticky;top:0;z-index:1;text-align:left;padding:10px 14px;font-size:12px;font-weight:600;
        letter-spacing:.03em;text-transform:uppercase;color:var(--ac-h-label);background:var(--ac-foot-bg,#FAFAFA);
        border-bottom:1px solid var(--ac-h-border);white-space:nowrap;}
.ac-table td{text-align:left;vertical-align:top;padding:9px 14px;border-top:1px solid var(--ac-h-border);
        overflow-wrap:anywhere;}
.ac-table tbody tr:first-child td{border-top:none;}
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
section_header(
    "Program Instances",
    "Every program instance running on the platform. Each row links directly to that program's "
    "configuration (stage labels, KPI tiles, at-risk threshold). New instances appear here automatically.",
)


@st.fragment
def program_instances_section():
    instances = cached_program_instances()

    if not instances:
        st.info("No program instances exist yet. Create one from the Student Roster's Active Program panel.")
        return

    # ---- Summary chips ----
    total = len(instances)
    active_n = sum(1 for r in instances if r.get("IsActive"))
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Total programs:** {total}")
    c2.markdown(f"**Active:** {active_n}")
    c3.markdown(f"**Inactive:** {total - active_n}")

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # ---- Column headers (same style as the User Permissions table) ----
    # Added "Chair" (Users.CurrentProgramID) next to "Owner" (Program.OwnerUserID).
    widths = [0.8, 2.0, 1.8, 1.8, 0.9, 0.8, 2.3]
    for col, label in zip(st.columns(widths, vertical_alignment="bottom"),
                          ["Code", "Program", "Owner", "Chair", "Status", "Students", "Actions"]):
        col.markdown(f'<div class="ac-th">{label}</div>', unsafe_allow_html=True)
    st.markdown('<div class="ac-th-line"></div>', unsafe_allow_html=True)

    # cached user list (shared by every row's picker -> one DB read per page, not per program)
    all_users = cached_users("") or []
    user_labels = {f"{u['FirstName']} {u['LastName']} ({u['UserID']})": u["UserID"] for u in all_users}
    user_options = ["— Unassigned —"] + list(user_labels)

    # ---- One row per program ----
    for inst in instances:
        pid = inst["ProgramID"]
        cols = st.columns(widths, vertical_alignment="center")

        # Code
        with cols[0]:
            st.markdown(f"**{html.escape(str(inst['ProgramCode']))}**")

        # Program name + created date
        with cols[1]:
            st.markdown(
                f"{html.escape(str(inst['ProgramName']))}"
                + (f'<div class="ac-note-sm">Created '
                   f'{inst["CreatedAt"].strftime("%b %d, %Y") if inst.get("CreatedAt") else "—"}</div>'
                   if inst.get("CreatedAt") else ""),
                unsafe_allow_html=True,
            )

        # Owner (Program.OwnerUserID)
        with cols[2]:
            if inst.get("OwnerName"):
                st.markdown(f"{html.escape(str(inst['OwnerName']))}")
                if inst.get("OwnerEmail"):
                    st.markdown(f'<div class="ac-note-sm">{html.escape(str(inst["OwnerEmail"]))}</div>',
                                unsafe_allow_html=True)
            else:
                st.markdown('<span class="ac-note-sm">Unassigned</span>', unsafe_allow_html=True)

        # Chair (Users.CurrentProgramID) — picker + Save
        with cols[3]:
            chair_uid = inst.get("ChairUserID")
            current_chair = next(
                (lbl for lbl, uid in user_labels.items() if uid == chair_uid),
                "— Unassigned —",
            )
            chair_pick = st.selectbox(
                f"Chair for {pid}",
                user_options,
                index=user_options.index(current_chair) if current_chair in user_options else 0,
                key=f"chair_pick_{pid}",
                label_visibility="collapsed",
            )
            if chair_pick != current_chair and st.button("Assign", key=f"chair_save_{pid}",
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

        # Status pill
        with cols[4]:
            if inst.get("IsActive"):
                st.markdown('<span class="ac-chip" style="color:#15803D;background:#ECFDF3;'
                            'border-color:#BBF7D0;">ACTIVE</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="ac-chip" style="color:#B45309;background:#FFFBEB;'
                            'border-color:#FDE68A;">INACTIVE</span>', unsafe_allow_html=True)

        # Student count
        with cols[5]:
            st.markdown(f"{int(inst.get('StudentCount') or 0):,}")

        # Actions: Configure link + owner picker
        with cols[6]:
            act_left, act_right = st.columns([1.2, 1])
            with act_left:
                st.page_link(
                    "dashboard_views/admin_config.py",
                    label="⚙ Configure",
                    query_params={"program": str(pid)},
                )
            with act_right:
                owner_options = ["— Unassigned —"] + list(user_labels)
                current_owner = next(
                    (lbl for lbl, uid in user_labels.items() if uid == inst.get("OwnerUserID")),
                    "— Unassigned —",
                )
                picked = st.selectbox(
                    f"Owner for {pid}",
                    owner_options,
                    index=owner_options.index(current_owner) if current_owner in owner_options else 0,
                    key=f"owner_pick_{pid}",
                    label_visibility="collapsed",
                )
                if picked != current_owner and st.button("Save", key=f"owner_save_{pid}"):
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
        overflow:hidden;gap:0 !important;}
[class*="st-key-achead_"]{padding:24px 28px 20px 28px;border-bottom:1px solid var(--ac-h-border);gap:4px !important;}
[class*="st-key-acbody_"]{padding:24px 28px 24px 28px;gap:14px !important;}
[class*="st-key-acfoot_"]{padding:14px 28px;background:var(--ac-foot-bg);border-top:1px solid var(--ac-h-border);}
.ac-card-title{font-size:20px;font-weight:700;color:var(--ac-h-text);margin:0;line-height:1.3;}
.ac-card-desc{font-size:14px;color:var(--ac-h-label);margin:4px 0 0 0;line-height:1.5;}
.ac-foot-note{font-size:14px;color:var(--ac-h-label);}
.ac-foot-note b{color:var(--ac-h-text);}
.ac-field-label{font-size:14px;font-weight:600;color:var(--ac-h-text);margin:0 0 -6px 0;}
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
.ac-th2{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#6B7280;}
html[data-eo-theme="dark"] .ac-th2{color:#94A3B8;}
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
.ac-add-title{font-size:16px;font-weight:700;color:var(--ac-h-text);margin:0;}
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
    gap: 8px !important;
  }
  [class*="st-key-kpirow_"] [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 8px) !important;
    min-width: 140px !important;
  }
  /* The Add-a-Tile row: stack the fields */
  [class*="st-key-kpiadd_"] [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 10px !important;
  }
  [class*="st-key-kpiadd_"] [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 100% !important;
  }
  /* User Permissions: hide the wide 4-column layout; show name+role stacked */
  .ac-table-wrap { font-size: 12px; }
}
</style>"""
st.markdown(CARD_CSS, unsafe_allow_html=True)


def card_head(name, title, desc):
    """Card title + description (with the line under it)."""
    with st.container(key=f"achead_{name}"):
        st.markdown(f'<div class="ac-card-title">{title}</div><div class="ac-card-desc">{desc}</div>',
                    unsafe_allow_html=True)


def program_options():
    """{"BIA — BS Business Intelligence and Analytics": ProgramID, ...} for the program dropdowns."""
    return {f"{p['ProgramCode']} — {p['ProgramName']}": p["ProgramID"] for p in cached_programs()}


st.markdown('<div class="ac-eyebrow">Program-specific thresholds and terminologies</div>', unsafe_allow_html=True)


# ------------------------------------------------------------
# 1) At-Risk Threshold  (compact card: inputs + Save on one row)
# ------------------------------------------------------------
@st.fragment
def threshold_section():
    with st.container(key="accard_threshold"):
        with st.container(key="acbody_threshold"):
            st.markdown('<div class="ac-card-title">At-Risk Threshold</div>'
                        '<div class="ac-card-desc">Flag students after this many days in one stage.</div>',
                        unsafe_allow_html=True)
            prog_by_label = program_options()
            if not prog_by_label:
                st.info("No programs found.")
                return

            c_prog, c_days, c_btn = st.columns([2.3, 1.1, 0.6], vertical_alignment="bottom")
            with c_prog:
                th_label = st.selectbox("Program", list(prog_by_label), key="th_program")
            th_program_id = prog_by_label[th_label]
            th_current = cached_threshold(th_program_id)
            with c_days:
                th_days = st.number_input("Days", min_value=1, step=1,
                                          value=int(th_current) if th_current else 180,
                                          key=f"th_days_{th_program_id}")
            with c_btn:
                th_save = st.button("Save", type="primary", key="th_save", use_container_width=True)

            st.markdown(f'<div class="ac-note">Currently {th_current} days</div>' if th_current else
                        '<div class="ac-note">No threshold yet, so nobody is flagged</div>',
                        unsafe_allow_html=True)

    if th_save:
        require_edit()   # US-13 gate: View Only users are stopped and the attempt is logged
        ok, msg = set_program_threshold(current_user_id(), th_program_id, int(th_days))
        if ok:
            st.cache_data.clear()   # dashboards (roster / overview) pick up the new flags right away
            st.session_state["th_flash"] = msg
            st.rerun(scope="fragment")
        else:
            st.error(msg)

    th_flash = st.session_state.pop("th_flash", None)
    if th_flash:
        st.toast(th_flash)


# ------------------------------------------------------------
# 2) Data Refresh Schedule  (compact card: inputs + Save on one row)
# ------------------------------------------------------------
@st.fragment
def refresh_schedule_section():
    schedule = cached_schedule()
    cur_h, cur_m = (int(x) for x in schedule["time"].split(":"))

    with st.container(key="accard_refresh"):
        with st.container(key="acbody_refresh"):
            st.markdown('<div class="ac-card-title">Data Refresh Schedule</div>'
                        '<div class="ac-card-desc">When dashboard data refreshes automatically.</div>',
                        unsafe_allow_html=True)

            c_freq, c_time, c_btn = st.columns([2.3, 1.1, 0.6], vertical_alignment="bottom")
            with c_freq:
                st.selectbox("Frequency", ["Nightly (every day)"], disabled=True, key="rf_freq")
            with c_time:
                rf_time = st.time_input(f"Time ({schedule['timezone']})", value=dtime(cur_h, cur_m),
                                        step=900, key="rf_time")
            with c_btn:
                rf_save = st.button("Save", type="primary", key="rf_save", use_container_width=True)

            if schedule["last_run"]:
                try:
                    last_txt = datetime.strptime(schedule["last_run"], "%Y-%m-%d %H:%M:%S") \
                        .strftime("%b %d, %Y · %I:%M %p")
                except ValueError:
                    last_txt = html.escape(str(schedule["last_run"]))
                failed = schedule["last_status"] == "Failed"
                dot = "ac-dot-fail" if failed else "ac-dot-ok"
                extra = " (failed, see System Sync Logs)" if failed else ""
                st.markdown(f'<div class="ac-note"><span class="ac-dot {dot}"></span>'
                            f'Last refresh {last_txt}{extra}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="ac-note">Not run yet</div>', unsafe_allow_html=True)

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
        st.toast(rf_flash)


# ------------------------------------------------------------
# 3) Stage Labels (US-30)
# ------------------------------------------------------------
STAGE_LABEL_FIELDS = [      # (stage key in the database, short tag, name shown in Admin Config)
    ("Coursework", "CW", "Coursework Label"),
    ("CompExam",   "CE", "Comprehensive Exam Label"),
    ("Capstone",   "CP", "Capstone Label"),
]


@st.cache_data(ttl=300, show_spinner=False)
def cached_stage_labels(program_id):
    return get_stage_labels(program_id)


@st.fragment
def stage_labels_section():
    prog_by_label = program_options()
    with st.container(key="accard_labels"):
        with st.container(key="achead_labels"):
            c_title, c_prog = st.columns([2.6, 1.1], vertical_alignment="top")
            with c_title:
                st.markdown(
                    '<div class="ac-card-title">Stage Labels</div>'
                    '<div class="ac-card-desc">Rename each stage for a program (e.g. “Capstone Paper” → “Thesis”). '
                    "The new name shows on Student Profile, Student Roster, Executive Overview and the "
                    "Excel export.</div>",
                    unsafe_allow_html=True,
                )
            with c_prog:
                if prog_by_label:
                    # US-42: pre-select the program the console linked to (if any)
                    target_pid = st.session_state.get("pi_target_program")
                    labels_list = list(prog_by_label)
                    default_idx = 0
                    if target_pid is not None:
                        for i, lbl in enumerate(labels_list):
                            if prog_by_label[lbl] == target_pid:
                                default_idx = i
                                break
                    lbl_program = st.selectbox("Program", labels_list, index=default_idx, key="lbl_program")

        with st.container(key="acbody_labels"):
            if not prog_by_label:
                st.info("No programs found.")
                return
            program_id = prog_by_label[lbl_program]
            current = cached_stage_labels(program_id)

            new_values = {}
            for col, (pillar, tag, field_name) in zip(st.columns(3, gap="small"), STAGE_LABEL_FIELDS):
                with col:
                    st.markdown(f'<div class="ac-field-label"><span class="ac-tag">{tag}</span>{field_name}</div>',
                                unsafe_allow_html=True)
                    new_values[pillar] = st.text_input(field_name, value=current[pillar],
                                                       key=f"lbl_{program_id}_{pillar}",
                                                       label_visibility="collapsed")
                    st.markdown(f'<div class="ac-note-sm">Default: {html.escape(DEFAULT_STAGE_LABELS[pillar])}</div>',
                                unsafe_allow_html=True)

        with st.container(key="acfoot_labels"):
            _, c_btn = st.columns([4, 1], vertical_alignment="center")
            with c_btn:
                lbl_save = st.button("Save Labels", type="primary", key="lbl_save", use_container_width=True)

    if lbl_save:
        require_edit()   # US-13 gate
        changed = {p: v.strip() for p, v in new_values.items() if v.strip() != current[p]}
        if not changed:
            st.toast("Nothing changed.")
            return
        errors = []
        for pillar, label in changed.items():
            ok, msg = set_stage_label(current_user_id(), program_id, pillar, label)
            if not ok:
                errors.append(msg)
        if errors:
            st.error(" ".join(dict.fromkeys(errors)))   # same message only once
        else:
            st.cache_data.clear()   # every page picks up the new names right away
            st.session_state["lbl_flash"] = f"Saved {len(changed)} stage label(s) for {lbl_program}."
            st.rerun(scope="fragment")

    lbl_flash = st.session_state.pop("lbl_flash", None)
    if lbl_flash:
        st.toast(lbl_flash)


with st.container(key="ac_pair"):
    col_left, col_right = st.columns(2, gap="medium")
    with col_left:
        threshold_section()
    with col_right:
        refresh_schedule_section()

st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)
stage_labels_section()


# ------------------------------------------------------------
# 4) KPI Tiles (US-29) — stored as JSON on Program.KpiTiles
#   Changes (label, order, visible, colour, delete, add) are made on a draft
#   and only written to the database when "Save Tiles" is clicked.
# ------------------------------------------------------------
KPI_SOURCES = [
    "total_enrolled", "remaining", "at_risk",
    "on_time_rate", "overall_completion", "completion_rate",
    "cohort_count", "program_label", "student_count",
]
KPI_WIDTHS = [1.25, 3.3, 2.3, 0.9, 0.9, 0.55]   # order | label | source | visible | accent | delete


def _kpi_draft_key(pid):
    return f"kpi_draft_{pid}"


def _kpi_load_draft(pid):
    """(Re)load the tiles from the database into the draft and forget old widget values."""
    tiles = [dict(t) for t in get_all_kpi_tiles(program_id=pid)]
    st.session_state[_kpi_draft_key(pid)] = tiles
    st.session_state[f"kpi_saved_{pid}"] = [dict(t) for t in tiles]
    prefixes = (f"kpi_l_{pid}_", f"kpi_v_{pid}_", f"kpi_c_{pid}_")
    for k in [k for k in st.session_state if str(k).startswith(prefixes)]:
        del st.session_state[k]


def _kpi_norm(tiles):
    """For the "unsaved changes" check: colour case doesn't matter (#FFCA06 == #ffca06)."""
    return [{**t, "color": str(t.get("color", "")).lower()} for t in tiles]


def _kpi_add_tile(pid):
    """on_click for "+ Add": validates, appends to the draft, clears the inputs."""
    key = st.session_state.get(f"kpi_new_key_{pid}", "").strip().lower().replace(" ", "_")
    label = st.session_state.get(f"kpi_new_label_{pid}", "").strip()
    draft = st.session_state[_kpi_draft_key(pid)]
    if not key or not label:
        st.session_state["kpi_flash"] = (False, "Both Key and Label are required to add a tile.")
        return
    if any(t.get("key") == key for t in draft):
        st.session_state["kpi_flash"] = (False, f"A tile with key '{key}' already exists.")
        return
    draft.append({
        "key": key, "label": label,
        "source": st.session_state.get(f"kpi_new_source_{pid}", KPI_SOURCES[0]),
        "order": len(draft) + 1,
        "visible": st.session_state.get(f"kpi_new_visible_{pid}", True),
        "color": st.session_state.get(f"kpi_new_color_{pid}", "#1F3864"),
    })
    st.session_state[f"kpi_new_key_{pid}"] = ""
    st.session_state[f"kpi_new_label_{pid}"] = ""
    st.session_state["kpi_flash"] = (True, f"Added '{label}'. Click Save Tiles to keep it.")


st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)


@st.fragment
def kpi_tiles_section():
    programs = cached_programs()
    with st.container(key="accard_kpi"):
        with st.container(key="achead_kpi"):
            c_title, c_prog = st.columns([2.6, 1.1], vertical_alignment="top")
            with c_title:
                st.markdown(
                    '<div class="ac-card-title">KPI Tiles</div>'
                    '<div class="ac-card-desc">The cards at the top of the Executive Overview, saved per program. '
                    "To see them, pick that program in the Executive Overview's Program filter "
                    "(All Programs always shows the built-in defaults). Accent = the coloured bar on top of the card."
                    "</div>",
                    unsafe_allow_html=True,
                )
            with c_prog:
                if programs:
                    # US-42: pre-select the program the console linked to (if any)
                    target_pid = st.session_state.get("pi_target_program")
                    default_idx = 0
                    if target_pid is not None:
                        for i, p in enumerate(programs):
                            if p["ProgramID"] == target_pid:
                                default_idx = i
                                break
                    prog_choice = st.selectbox(
                        "Program", programs,
                        index=default_idx,
                        format_func=lambda p: f"{p['ProgramCode']} — {p['ProgramName']}",
                        key="kpi_program",
                    )

        with st.container(key="acbody_kpi"):
            if not programs:
                st.info("No programs available yet.")
                return
            pid = prog_choice["ProgramID"]
            if _kpi_draft_key(pid) not in st.session_state:
                _kpi_load_draft(pid)
            draft = st.session_state[_kpi_draft_key(pid)]

            # header row
            for col, label in zip(st.columns(KPI_WIDTHS, vertical_alignment="bottom"),
                                  ["Order", "Label", "Source", "Visible", "Accent", ""]):
                col.markdown(f'<div class="ac-th2">{label}</div>', unsafe_allow_html=True)

            move, delete = None, None
            for i, t in enumerate(draft):
                tkey = t.get("key") or f"tile{i}"
                with st.container(key=f"kpirow_{pid}_{tkey}"):
                    c_ord, c_lbl, c_src, c_vis, c_col, c_del = st.columns(KPI_WIDTHS, vertical_alignment="center")
                    with c_ord:
                        with st.container(key=f"kpiord_{pid}_{tkey}"):
                            o_num, o_up, o_down = st.columns([1, 1, 1], vertical_alignment="center")
                            o_num.markdown(f'<div class="ac-ord-num">{i + 1}</div>', unsafe_allow_html=True)
                            if o_up.button("▲", key=f"kpi_up_{pid}_{tkey}", type="tertiary", disabled=i == 0):
                                move = (i, i - 1)
                            if o_down.button("▼", key=f"kpi_dn_{pid}_{tkey}", type="tertiary",
                                             disabled=i == len(draft) - 1):
                                move = (i, i + 1)
                    with c_lbl:
                        t["label"] = st.text_input("Label", value=t.get("label", ""),
                                                   key=f"kpi_l_{pid}_{tkey}", label_visibility="collapsed")
                    with c_src:
                        st.markdown(f'<span class="ac-chip">{html.escape(str(t.get("source", "")))}</span>',
                                    unsafe_allow_html=True)
                    with c_vis:
                        t["visible"] = st.toggle("Visible", value=bool(t.get("visible", True)),
                                                 key=f"kpi_v_{pid}_{tkey}", label_visibility="collapsed")
                    with c_col:
                        t["color"] = st.color_picker("Accent", value=t.get("color", "#1F3864"),
                                                     key=f"kpi_c_{pid}_{tkey}", label_visibility="collapsed")
                    with c_del:
                        with st.container(key=f"kpidel_{pid}_{tkey}"):
                            if st.button("✕", key=f"kpi_d_{pid}_{tkey}", help="Remove this tile"):
                                delete = i

            if move is not None:
                a, b = move
                draft[a], draft[b] = draft[b], draft[a]
                st.rerun(scope="fragment")
            if delete is not None:
                removed = draft.pop(delete)
                st.session_state["kpi_flash"] = (True, f"Removed '{removed.get('label')}'. "
                                                       "Click Save Tiles to confirm.")
                st.rerun(scope="fragment")

            # ----- Add a tile -----
            with st.container(key=f"kpiadd_{pid}"):
                st.markdown('<div class="ac-add-title">Add a Tile</div>', unsafe_allow_html=True)
                a_key, a_lbl, a_src, a_col, a_vis, a_btn = st.columns([1.6, 1.8, 1.6, 0.6, 0.6, 0.8],
                                                                       vertical_alignment="bottom")
                a_key.text_input("Key (unique)", placeholder="retention_rate", key=f"kpi_new_key_{pid}")
                a_lbl.text_input("Label", placeholder="Retention Rate", key=f"kpi_new_label_{pid}")
                a_src.selectbox("Source", KPI_SOURCES, key=f"kpi_new_source_{pid}")
                a_col.color_picker("Accent", "#1F3864", key=f"kpi_new_color_{pid}")
                a_vis.toggle("Visible", value=True, key=f"kpi_new_visible_{pid}")
                a_btn.button("+ Add", key=f"kpi_add_{pid}", on_click=_kpi_add_tile, args=(pid,),
                             use_container_width=True)

            flash = st.session_state.pop("kpi_flash", None)
            if flash:
                (st.success if flash[0] else st.error)(flash[1])

        with st.container(key="acfoot_kpi"):
            c_reset, c_note, c_save = st.columns([1, 2, 1], vertical_alignment="center")
            with c_reset:
                reset_clicked = st.button("Reset to Defaults", key="kpi_reset")
            with c_note:
                unsaved = _kpi_norm(draft) != _kpi_norm(st.session_state.get(f"kpi_saved_{pid}", []))
                if unsaved:
                    st.markdown('<span class="ac-foot-note">You have unsaved changes</span>',
                                unsafe_allow_html=True)
            with c_save:
                save_clicked = st.button("Save Tiles", type="primary", key="kpi_save_all",
                                         use_container_width=True)

    if save_clicked:
        require_edit()   # US-13 gate
        for n, t in enumerate(draft, start=1):   # order = position in the list
            t["order"] = n
        ok, err = save_kpi_tiles(pid, draft)
        if ok:
            _kpi_load_draft(pid)
            st.cache_data.clear()   # Executive Overview shows the new tiles right away
            st.session_state["kpi_flash"] = (True, "KPI tiles saved.")
        else:
            st.session_state["kpi_flash"] = (False, err)
        st.rerun(scope="fragment")

    if reset_clicked:
        require_edit()   # US-13 gate
        ok, err = reset_kpi_tiles(pid)
        if ok:
            _kpi_load_draft(pid)
            st.cache_data.clear()
            st.session_state["kpi_flash"] = (True, "Reset to built-in defaults.")
        else:
            st.session_state["kpi_flash"] = (False, err)
        st.rerun(scope="fragment")


kpi_tiles_section()
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
                        st.cache_data.clear()   # other pages cache each user's permission for a short time
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
        show_table(audit_rows)
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


@st.cache_data(ttl=30, show_spinner=False)
def cached_sync_logs():
    return get_system_logs_local()


@st.fragment
def sync_logs_section():
    active_login_id = st.session_state.get("session_id", "default_admin")
    st.info(f"Active Session ID for this browser: **{active_login_id}**")

    if st.button("Run Sync Attempt", key="sync_run"):
        # Sync is a read-only operation — no permission gate needed
        with st.spinner("Running sync attempt..."):
            success = trigger_data_sync(login_id=active_login_id)
        cached_sync_logs.clear()      # show the new attempt in the table
        _last_sync_time.clear()       # sidebar's Live Sync Status shows the new time right away
        # Keep the result in session_state: the full-page rerun below used to wipe the message
        # before it could be read ("too fast", or never visible).
        now = datetime.now()
        st.session_state["sync_result"] = {
            "ok": success,
            "ts": now.timestamp(),
            "at": now.strftime("%b %d, %Y · %I:%M:%S %p"),
        }
        st.rerun()   # full page rerun so the sidebar's Live Sync Status updates too

    # Show the result of the last attempt right under the button for 2 minutes
    # (the timestamp stops an old message from looking current when you come back later).
    result = st.session_state.get("sync_result")
    if result and (datetime.now().timestamp() - result["ts"]) < 120:
        if result["ok"]:
            st.success(f"Sync executed successfully! ({result['at']})")
        else:
            st.error(f"Sync failed! The error was logged in the table below. ({result['at']})")

    logs = cached_sync_logs()

    if logs:
        show_table(logs)
    else:
        st.info("No system logs found in the local_logs.db")


sync_logs_section()
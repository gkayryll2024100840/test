import html

import pandas as pd
import streamlit as st

from db_connect import (
    can_edit,
    get_lifecycle_status_options,
    get_student_lifecycle_detail,
    get_student_roster_data,
    get_user_program,
    update_enrollment_status,
    update_lifecycle_statuses,
)
from permissions import require_edit
from dashboard_views.components import (
    DARK_MODE_CSS,
    set_header_context,
)

st.set_page_config(page_title="Student Profile", layout="wide")

# Inject unified dark mode styling
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view student profile.")
    st.stop()

# ---------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------
PILLARS = [
    # key,         tag,  title,                   dropdown options
    ("coursework", "CW", "Coursework Completion", ["Cancelled", "Completed", "Pending"]),
    ("compexam",   "CE", "Comprehensive Exam",    ["In-Progress", "Passed", "Incomplete"]),
    ("capstone",   "CP", "Capstone Paper",        ["In-Progress", "Defended for Completion"]),
]
STATUS_FIELD = {"coursework": "CourseworkStatus", "compexam": "CompExamStatus", "capstone": "CapstoneStatus"}
ENROLLMENT_OPTIONS = ["Enrolled", "Conditionally Enrolled"]

# green = done, yellow = still going, red = stopped / not passed
STATUS_TONE = {
    "completed": "green", "passed": "green", "defended for completion": "green", "enrolled": "green",
    "in-progress": "yellow", "pending": "yellow", "conditionally enrolled": "yellow",
    "incomplete": "red", "cancelled": "red",
}


def tone_of(status):
    return STATUS_TONE.get(str(status).strip().lower(), "yellow")


PAGE_CSS = """
<style>
/* =====================================================================
   SPACING KNOBS — change these to adjust the page (px values)
   ===================================================================== */
.stApp{
  --sp-card-pad: 20px;          /* inside padding of every card (student card, status cards, save bar) */
  --sp-card-radius: 14px;       /* corner roundness of the cards */
  --sp-subtitle-gap: 4px;       /* space between "Student Profile" and "Review and update a student's..." */
  --sp-title-gap: 14px;         /* space between "Review and update..." and the line underneath */
  --sp-block-gap: 18px;         /* space between the big blocks (student card, notice, section, save bar) */
  --sp-section-gap: 12px;       /* space between "Program Lifecycle Status" text and the status cards */
  --sp-pill-title-gap: 16px;    /* space between the CW tag row and the card title */
  --sp-pill-sub-gap: 12px;      /* space between the card subtitle and the status pill */
  --sp-cards-gap: 16px;         /* space between the three status cards (CW / CE / CP) */
}
.stApp{
  --sp-surface:#FFFFFF; --sp-soft:#F9FAFB; --sp-border:#E5E7EB; --sp-text:#0F172A; --sp-muted:#6B7280; --sp-faint:#9CA3AF;
  --sp-shadow:0 1px 2px rgba(16,24,40,.05);
  --g-bg:#ECFDF3; --g-fg:#15803D; --g-bd:#BBF7D0;  --y-bg:#FEF9C3; --y-fg:#854D0E; --y-bd:#FDE047;
  --r-bg:#FEF2F2; --r-fg:#B91C1C; --r-bd:#FECACA;
}
html[data-eo-theme="dark"] .stApp{
  --sp-surface:#161D2B; --sp-soft:#111827; --sp-border:#263044; --sp-text:#F1F5F9; --sp-muted:#94A3B8; --sp-faint:#64748B;
  --sp-shadow:none;
  --g-bg:rgba(16,185,129,.15); --g-fg:#34D399; --g-bd:rgba(16,185,129,.35);
  --y-bg:rgba(234,179,8,.15);  --y-fg:#FDE047; --y-bd:rgba(234,179,8,.35);
  --r-bg:rgba(239,68,68,.14);  --r-fg:#FCA5A5; --r-bd:rgba(239,68,68,.35);
}

/* ---- title row: title + subtitle on the left, student picker on the right, line underneath ---- */
.st-key-sp_top{border-bottom:1px solid var(--sp-border);padding-bottom:var(--sp-title-gap);margin-bottom:6px;}
.st-key-sp_top [data-testid="stHorizontalBlock"]{gap:0 !important;}
/* student picker: fills the right-hand column so its right edge lines up with the cards' right edge */
.st-key-sp_top [data-testid="stColumn"]:last-child{padding:0 !important;}
.st-key-sp_picker, .st-key-sp_picker [data-testid="stVerticalBlock"],
.st-key-sp_picker [data-testid="stElementContainer"], .st-key-sp_picker [data-testid="stSelectbox"],
.st-key-sp_picker [data-baseweb="select"]{width:100% !important;max-width:none !important;align-items:stretch;}

/* markdown blocks fill their box (Streamlit shrinks them otherwise, which broke the right-alignment) */
[class*="st-key-sp_"] [data-testid="stMarkdownContainer"] > div,
.sp-block{width:100%;flex:1 1 auto;}
.sp-page-title{font-size:2.75rem;font-weight:700;line-height:1.15;color:var(--sp-text);letter-spacing:-.01em;}
.sp-page-sub{font-size:14px;color:var(--sp-muted);margin-top:var(--sp-subtitle-gap);}
.st-key-sp_picker [data-testid="stWidgetLabel"]{margin-bottom:4px;min-height:0;}
.st-key-sp_picker [data-testid="stWidgetLabel"] p{font-size:13px;font-weight:600;color:var(--sp-text);text-transform:none;}

/* ---- student card: cells split by full-height lines ---- */
.st-key-sp_head{background:var(--sp-surface);border:1px solid var(--sp-border);border-radius:var(--sp-card-radius);
    box-shadow:var(--sp-shadow);padding:0 !important;overflow:hidden;margin-top:var(--sp-block-gap);}
.st-key-sp_head [data-testid="stHorizontalBlock"]{gap:0 !important;align-items:stretch !important;}
.st-key-sp_head [data-testid="stColumn"]{padding:var(--sp-card-pad) !important;min-height:96px;}
.st-key-sp_head [data-testid="stColumn"] > div{height:100%;justify-content:center;}
.st-key-sp_head [data-testid="stColumn"] + [data-testid="stColumn"]{border-left:1px solid var(--sp-border);}
.sp-who{display:flex;align-items:center;gap:16px;}
.sp-name{font-size:22px;font-weight:700;color:var(--sp-text);line-height:1.2;}
.sp-id{font-size:13px;color:var(--sp-muted);margin-top:2px;}
.sp-id b{color:var(--sp-text);}
.sp-fact-label{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--sp-muted);}
.sp-fact-value{font-size:16px;font-weight:700;color:var(--sp-text);margin-top:8px;}

/* ---- notice ---- */
.sp-note{display:flex;gap:12px;align-items:flex-start;border-radius:12px;padding:12px 16px;font-size:13px;line-height:1.55;
    margin:var(--sp-block-gap) 0 var(--sp-block-gap) 0;background:#FEF9C3;border:1px solid #FDE68A;color:#3F3F46;}
.sp-note b{color:#1F2937;}
html[data-eo-theme="dark"] .sp-note{background:rgba(234,179,8,.10);border-color:rgba(234,179,8,.3);color:#E5E7EB;}
html[data-eo-theme="dark"] .sp-note b{color:#FDE047;}
.sp-note-view{background:var(--sp-soft);border-color:var(--sp-border);color:var(--sp-muted);}
.sp-note-icon{border:1.5px solid #A16207;color:#A16207;border-radius:50%;width:20px;height:20px;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;margin-top:1px;}

/* ---- section header + legend ---- */
.sp-section{font-size:20px;font-weight:700;color:var(--sp-text);}
.sp-section-sub{font-size:13px;color:var(--sp-muted);margin:2px 0 var(--sp-section-gap) 0;}

/* ---- pillar cards ---- */
[class*="st-key-sp_pillar_"]{background:var(--sp-surface);border:1px solid var(--sp-border);border-radius:var(--sp-card-radius);
    padding:var(--sp-card-pad) !important;box-shadow:var(--sp-shadow);gap:0 !important;}
.st-key-sp_pillars [data-testid="stHorizontalBlock"]{gap:var(--sp-cards-gap) !important;}
[class*="st-key-sp_pillar_"] [data-testid="stHorizontalBlock"]{gap:8px !important;}
/* Streamlit pulls the element after a text block up by 1rem; switch that off inside the cards
   so --sp-pill-sub-gap is the real gap between the subtitle and the pill */
[class*="st-key-sp_pillar_"] [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
[class*="st-key-sp_pillar_"] [data-testid="stElementContainer"],
[class*="st-key-sp_pillar_"] [data-testid="stMarkdown"],
[class*="st-key-sp_pillar_"] [data-testid="stMarkdownContainer"]{width:100% !important;}
.sp-pill-top{display:flex;justify-content:space-between;align-items:center;width:100%;}
.sp-tag{display:inline-flex;align-items:center;justify-content:center;min-width:34px;height:26px;padding:0 8px;
    font-size:11px;font-weight:700;letter-spacing:.04em;border-radius:6px;background:rgba(148,163,184,.14);color:var(--sp-muted);}
.sp-override{font-size:12px;color:var(--sp-muted);text-align:right;}
.sp-pillar-title{font-size:19px;font-weight:700;color:var(--sp-text);margin-top:var(--sp-pill-title-gap);line-height:1.3;}
.sp-pillar-sub{font-size:13px;color:var(--sp-muted);margin:4px 0 var(--sp-pill-sub-gap) 0;}
.sp-audit{text-align:right;width:100%;}
.sp-audit-label{font-size:10.5px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--sp-muted);}
.sp-audit-date{font-size:15px;font-weight:400;color:var(--sp-text);margin-top:1px;}
.sp-changed{font-size:11px;font-weight:600;color:#A16207;margin-bottom:2px;}

/* ---- status pills (popover buttons), coloured by tone ---- */
[class*="st-key-sp_pill_"] button{min-height:32px !important;height:32px;padding:0 12px !important;border-radius:8px !important;
    font-size:13px !important;font-weight:700 !important;box-shadow:none !important;width:auto !important;}
[class*="st-key-sp_pill_"] button p{font-size:13px !important;font-weight:700 !important;}
[class*="st-key-sp_pill_green_"] button{background:var(--g-bg) !important;color:var(--g-fg) !important;border:1px solid var(--g-bd) !important;}
[class*="st-key-sp_pill_yellow_"] button{background:var(--y-bg) !important;color:var(--y-fg) !important;border:1px solid var(--y-bd) !important;}
[class*="st-key-sp_pill_red_"] button{background:var(--r-bg) !important;color:var(--r-fg) !important;border:1px solid var(--r-bd) !important;}
[class*="st-key-sp_pill_green_"] button *{color:var(--g-fg) !important;}
[class*="st-key-sp_pill_yellow_"] button *{color:var(--y-fg) !important;}
[class*="st-key-sp_pill_red_"] button *{color:var(--r-fg) !important;}
.sp-static-pill{display:inline-flex;align-items:center;height:32px;padding:0 12px;border-radius:8px;font-size:13px;font-weight:700;}
.sp-static-pill.green{background:var(--g-bg);color:var(--g-fg);border:1px solid var(--g-bd);}
.sp-static-pill.yellow{background:var(--y-bg);color:var(--y-fg);border:1px solid var(--y-bd);}
.sp-static-pill.red{background:var(--r-bg);color:var(--r-fg);border:1px solid var(--r-bd);}

/* ---- save bar ---- */
.st-key-sp_actions{background:var(--sp-soft);border:1px solid var(--sp-border);border-radius:var(--sp-card-radius);
    padding:12px var(--sp-card-pad) !important;margin-top:var(--sp-block-gap);}
.sp-hint{font-size:13px;color:var(--sp-muted);}
.st-key-sp_save button{background:#B31B21 !important;border-color:#B31B21 !important;color:#FFFFFF !important;font-weight:700 !important;}
.st-key-sp_save button *{color:#FFFFFF !important;}
.st-key-sp_discard button{background:var(--sp-surface) !important;}
.st-key-sp_save button:disabled,.st-key-sp_discard button:disabled{opacity:.45;cursor:not-allowed;}
</style>
"""
st.markdown(PAGE_CSS, unsafe_allow_html=True)


def fmt_date(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return pd.to_datetime(value).strftime("%b %d, %Y")
    except Exception:
        return str(value)


def status_pill(slot, options, current, editable, label):
    """A coloured status pill; clicking it opens a list to pick a new status.

    Returns the status currently picked (saved value until the user changes it).
    """
    radio_key = f"sp_pick_{slot}"
    value = st.session_state.get(radio_key, current)
    if value not in options:
        value = current
    tone = tone_of(value)
    if not editable:
        st.markdown(f'<span class="sp-static-pill {tone}">{html.escape(str(value))}</span>', unsafe_allow_html=True)
        return value
    # the tone is part of the container key, so the colour rules in PAGE_CSS apply
    with st.container(key=f"sp_pill_{tone}_{slot}"):
        with st.popover(str(value)):
            st.radio(label, options, index=options.index(value), key=radio_key, label_visibility="collapsed")
    return value


# ---------------------------------------------------------------
# Resolve the active program (set by Student Roster or by the user's pin)
# ---------------------------------------------------------------
user = st.session_state.get("user", {})
role = user.get("role")
user_id = user.get("userid") or user.get("UserID")   # login.py stores keys in lowercase

if not st.session_state.get("active_program_id") and role != "IT/Admin":
    pinned = get_user_program(user_id)
    if pinned:
        st.session_state["active_program_id"] = pinned["ProgramID"]
        st.session_state["active_program_code"] = pinned["ProgramCode"]

active_program_id = st.session_state.get("active_program_id")
active_code = st.session_state.get("active_program_code", "")

if not active_program_id:
    st.warning("⏳ No active program has been set. Please pick one on the Student Roster page first.")
    st.stop()

df = get_student_roster_data(program_id=active_program_id)
header_cohort = "All Cohorts"

# ---------------------------------------------------------------
# Title row: title + subtitle | student picker
# ---------------------------------------------------------------
selected_label = None
student_options = {}
with st.container(key="sp_top"):
    c_title, c_pick = st.columns([4.8, 1.2], vertical_alignment="bottom")   # same split as the student card
    with c_title:
        st.markdown(
            '<div><div class="sp-page-title">Student Profile</div>'
            '<div class="sp-page-sub">Review and update a student\'s program milestones</div></div>',
            unsafe_allow_html=True,
        )
    if not df.empty:
        student_options = {
            f"{row['StudentNumber']} — {row['Student']}": str(row["StudentNumber"])
            for _, row in df.iterrows()
        }
        student_ids = list(student_options.values())
        default_index = 0
        # Navigation from Student Roster (student_profile?student_id=...)
        target_student_id = st.query_params.get("student_id") or st.session_state.get("selected_student_override")
        if target_student_id:
            target_str = str(target_student_id).strip()
            if target_str in student_ids:
                default_index = student_ids.index(target_str)
            st.session_state.pop("selected_student_override", None)
        with c_pick:
            with st.container(key="sp_picker"):
                selected_label = st.selectbox("Select student", list(student_options.keys()), index=default_index)

if df.empty:
    st.info(f"No student records available for the {active_code} program.")

elif selected_label:
    selected_id = student_options[selected_label]
    rows = df[df["StudentNumber"].astype(str) == selected_id]
    student = rows.iloc[0]

    student_name = str(student.get("Student", "Unknown"))
    cohort = str(student.get("Cohort", "N/A"))
    header_cohort = cohort
    current_enrollment = str(student.get("EnrollmentStatus") or "")
    adviser_col = "Adviser" if "Adviser" in rows.columns else "Advisor"
    advisers = [a for a in rows.get(adviser_col, pd.Series(dtype=object)).dropna().unique().tolist() if str(a).strip()]
    adviser_text = ", ".join(map(str, advisers)) or "None Assigned"

    detail = get_student_lifecycle_detail(selected_id) or {}
    current = {k: (detail.get(f"{k}_status") or student.get(STATUS_FIELD[k]) or "") for k, *_ in PILLARS}
    updated = {k: detail.get(f"{k}_updated") for k, *_ in PILLARS}

    editable = bool(user_id) and can_edit(user_id)
    pick_keys = [f"sp_pick_{k}_{selected_id}" for k, *_ in PILLARS] + [f"sp_pick_enroll_{selected_id}"]

    # ----------------- Student card -----------------
    with st.container(key="sp_head"):
        c_who, c_cohort, c_adv, c_enroll = st.columns([2.2, 1.1, 1.5, 1.2])
        with c_who:
            st.markdown(
                f'<div class="sp-block"><div class="sp-name">{html.escape(student_name)}</div>'
                f'<div class="sp-id">Student Number · <b>{html.escape(selected_id)}</b></div></div>',
                unsafe_allow_html=True,
            )
        with c_cohort:
            st.markdown(
                f'<div><div class="sp-fact-label">Current Cohort</div>'
                f'<div class="sp-fact-value">{html.escape(cohort)}</div></div>',
                unsafe_allow_html=True,
            )
        with c_adv:
            st.markdown(
                f'<div><div class="sp-fact-label">Assigned Adviser</div>'
                f'<div class="sp-fact-value">{html.escape(adviser_text)}</div></div>',
                unsafe_allow_html=True,
            )
        with c_enroll:
            st.markdown('<div class="sp-fact-label">Enrollment Status</div>', unsafe_allow_html=True)
            enroll_options = list(ENROLLMENT_OPTIONS)
            if current_enrollment and current_enrollment not in enroll_options:
                enroll_options = [current_enrollment] + enroll_options
            chosen_enrollment = status_pill(f"enroll_{selected_id}", enroll_options,
                                            current_enrollment or enroll_options[0], editable, "Enrollment status")

    if editable:
        st.markdown(
            '<div class="sp-note"><span class="sp-note-icon">!</span><div>'
            "<b>Manual Milestone Override Active:</b> Enrollment, Coursework, Comprehensive Exam, and Capstone "
            "Paper statuses can be updated here. Saving logs each change in its status history table and "
            "updates the student's Last Updated timestamp.</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sp-note sp-note-view"><span class="sp-note-icon">i</span><div>'
            "<b>View-only access:</b> you can see this student's milestones but not change them.</div></div>",
            unsafe_allow_html=True,
        )

    # ----------------- Section header -----------------
    st.markdown(
        '<div class="sp-block"><div class="sp-section">Program Lifecycle Status</div>'
        '<div class="sp-section-sub">Audit milestone checkpoints required for degree conferral</div></div>',
        unsafe_allow_html=True,
    )

    # ----------------- Pillar cards -----------------
    chosen = {}
    with st.container(key="sp_pillars"):
        cols = st.columns(3)
        for col, (key, tag, title, preferred) in zip(cols, PILLARS):
            options = get_lifecycle_status_options(key, preferred)
            if current[key] and current[key] not in options:
                options = [current[key]] + options          # keep an unexpected DB value visible
            with col:
                with st.container(key=f"sp_pillar_{key}"):
                    st.markdown(
                        f'<div class="sp-block"><div class="sp-pill-top"><span class="sp-tag">{tag}</span>'
                        f'<span class="sp-override">{"Step Manual Override" if editable else "Read only"}</span></div>'
                        f'<div class="sp-pillar-title">{title}</div>'
                        f'<div class="sp-pillar-sub">Current Academic Evaluation Status</div></div>',
                        unsafe_allow_html=True,
                    )
                    c_sel, c_date = st.columns([1.2, 1], vertical_alignment="bottom")
                    with c_sel:
                        chosen[key] = status_pill(f"{key}_{selected_id}", options,
                                                  current[key] or options[0], editable, title)
                    with c_date:
                        changed_note = '<div class="sp-changed">● unsaved change</div>' if chosen[key] != current[key] else ""
                        st.markdown(
                            f'<div class="sp-audit">{changed_note}<div class="sp-audit-label">Last Audited</div>'
                            f'<div class="sp-audit-date">{fmt_date(updated[key])}</div></div>',
                            unsafe_allow_html=True,
                        )

    changes = {k: v for k, v in chosen.items() if v != current[k]}
    enrollment_changed = bool(current_enrollment) and chosen_enrollment != current_enrollment
    n_changes = len(changes) + (1 if enrollment_changed else 0)

    # ----------------- Save / discard bar -----------------
    with st.container(key="sp_actions"):
        c_hint, c_discard, c_save = st.columns([5, 1.3, 1.9], vertical_alignment="center")
        with c_hint:
            hint = (f"{n_changes} unsaved change(s)." if n_changes
                    else "Click the status pills above to change student milestone states.")
            if not editable:
                hint = "Your account has View Only access."
            st.markdown(f'<div class="sp-hint">ⓘ {hint}</div>', unsafe_allow_html=True)
        with c_discard:
            if st.button("Discard Changes", key="sp_discard", disabled=not n_changes, width="stretch"):
                for pk in pick_keys:
                    st.session_state.pop(pk, None)
                st.rerun()
        with c_save:
            if st.button("Save Profile Milestones", key="sp_save", disabled=not (n_changes and editable),
                         width="stretch"):
                require_edit()   # View Only users are stopped and the attempt is logged
                results = []
                if changes:
                    results.append(update_lifecycle_statuses(selected_id, changes))
                if enrollment_changed:
                    results.append(update_enrollment_status(selected_id, chosen_enrollment))
                ok = all(r[0] for r in results)
                msg = f"Saved {n_changes} change(s)." if ok else " ".join(r[1] for r in results if not r[0])
                st.session_state["sp_flash"] = (ok, msg)
                for pk in pick_keys:
                    st.session_state.pop(pk, None)
                st.cache_data.clear()   # roster / overview pick up the new statuses right away
                st.rerun()

    # result of the last save, shown under the Save bar
    flash = st.session_state.pop("sp_flash", None)
    if flash:
        (st.success if flash[0] else st.error)(flash[1])

# Yellow header bar: this page's program + the selected student's cohort
set_header_context(program=active_program_id, cohort=header_cohort)
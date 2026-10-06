# STUDENT PROFILE.PY 
# UPDATED: 10-06-26 (speed-optimized + US-30 stage labels + US-46 one-page summary)

import html
import pandas as pd
import streamlit as st

from db_connect import (
    build_student_onepager_html,      # US-46
    can_edit,
    get_all_programs,
    get_lifecycle_status_options,
    get_stage_labels,                 # US-30: program-specific stage names
    get_student_at_risk_flag,         # US-46
    get_student_email,
    get_student_lifecycle_detail,
    get_student_notes,                # US-46
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
    # key,         tag,  title (default; the program's label from Admin Config is shown instead), dropdown options
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


# SPEED: cached wrappers so reruns (opening the dropdown pills, etc.) don't re-query the database.
# The Save button already calls st.cache_data.clear(), so saved changes show up right away.
@st.cache_data(ttl=60, show_spinner=False)
def cached_roster(program_id):
    return get_student_roster_data(program_id=program_id)


@st.cache_data(ttl=30, show_spinner=False)
def cached_can_edit(user_id):
    return can_edit(user_id)   # Save still calls require_edit(), which is the real permission gate


@st.cache_data(ttl=30, show_spinner=False)
def cached_lifecycle_detail(student_id):
    return get_student_lifecycle_detail(student_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_status_options(key, preferred):
    return get_lifecycle_status_options(key, list(preferred))


@st.cache_data(ttl=300, show_spinner=False)
def cached_stage_labels(program_id):
    """US-30: this program's stage names (set in Admin Config → Stage Labels).
    Saving labels there clears this cache, so new names show up right away."""
    return get_stage_labels(program_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_student_email(student_id):
    """Students.StudentEmail for the email button on the student card (None if blank)."""
    return get_student_email(student_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_program_ids():
    """{"MBA": 1, "BIA": 2, ...}: with "All Programs", each student's own program is looked up by its code."""
    return {p["ProgramCode"]: p["ProgramID"] for p in (get_all_programs() or [])}


# PILLARS key -> the stage key used by get_stage_labels()
PILLAR_LABEL_KEY = {"coursework": "Coursework", "compexam": "CompExam", "capstone": "Capstone"}


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
  --sp-title-gap: 10px;         /* space between "Review and update..." and the line underneath (matches Executive Overview) */
  --sp-block-gap: 18px;         /* space between the big blocks (student card, notice, section, save bar) */
  --sp-section-gap: 12px;       /* space between "Program Lifecycle Status" text and the status cards */
  --sp-pill-title-gap: 16px;    /* space between the CW tag row and the card title */
  --sp-pill-sub-gap: 12px;      /* space between the card subtitle and the status pill */
  --sp-cards-gap: 16px;         /* space between the three status cards (CW / CE / CP) */
}
.stApp{
  --sp-surface:#FFFFFF; --sp-soft:#F9FAFB; --sp-border:#E5E7EB; --sp-text:#0F172A; --sp-label:#4B5563; --sp-muted:#6B7280; --sp-faint:#9CA3AF;
  --sp-shadow:0 1px 2px rgba(16,24,40,.05);
  --g-bg:#ECFDF3; --g-fg:#15803D; --g-bd:#BBF7D0;  --y-bg:#FEF9C3; --y-fg:#854D0E; --y-bd:#FDE047;
  --r-bg:#FEF2F2; --r-fg:#B91C1C; --r-bd:#FECACA;
}
html[data-eo-theme="dark"] .stApp{
  --sp-surface:#161D2B; --sp-soft:#111827; --sp-border:#263044; --sp-text:#F1F5F9; --sp-label:#94A3B8; --sp-muted:#94A3B8; --sp-faint:#64748B;
  --sp-shadow:none;
  --g-bg:rgba(16,185,129,.15); --g-fg:#34D399; --g-bd:rgba(16,185,129,.35);
  --y-bg:rgba(234,179,8,.15);  --y-fg:#FDE047; --y-bd:rgba(234,179,8,.35);
  --r-bg:rgba(239,68,68,.14);  --r-fg:#FCA5A5; --r-bd:rgba(239,68,68,.35);
}

/* ---- title row: title + subtitle on the left, student picker on the right, line underneath ---- */
.st-key-sp_top{border-bottom:1px solid var(--sp-border);padding-bottom:var(--sp-title-gap);margin-bottom:6px;}
.st-key-sp_top [data-testid="stHorizontalBlock"]{gap:0 !important;}
/* Streamlit gives markdown blocks a negative bottom margin, which pulled the caption down onto the line.
   Zeroing it makes the gap under the caption exactly --sp-title-gap, like the Executive Overview header. */
.st-key-sp_top [data-testid="stElementContainer"]:has(.sp-page-title),
.st-key-sp_top [data-testid="stMarkdown"]:has(.sp-page-title),
.st-key-sp_top [data-testid="stMarkdownContainer"]:has(.sp-page-title){margin:0 !important;padding:0 !important;}
/* student picker: fills the right-hand column so its right edge lines up with the cards' right edge */
.st-key-sp_top [data-testid="stColumn"]:last-child{padding:0 !important;}
.st-key-sp_picker, .st-key-sp_picker [data-testid="stVerticalBlock"],
.st-key-sp_picker [data-testid="stElementContainer"], .st-key-sp_picker [data-testid="stSelectbox"],
.st-key-sp_picker [data-baseweb="select"]{width:100% !important;max-width:none !important;align-items:stretch;}

/* markdown blocks fill their box (Streamlit shrinks them otherwise, which broke the right-alignment) */
[class*="st-key-sp_"] [data-testid="stMarkdownContainer"] > div,
.sp-block{width:100%;flex:1 1 auto;}
/* title + caption: same look as the Executive Overview header */
.sp-page-title{font-size:2.75rem !important;font-weight:700 !important;line-height:1.15 !important;color:var(--sp-text) !important;
        letter-spacing:-.01em;margin:0 !important;padding:0 !important;opacity:1 !important;}
.sp-page-sub{font-size:14px !important;line-height:1.5 !important;color:var(--sp-label) !important;
        margin:var(--sp-subtitle-gap) 0 0 0 !important;padding:0 !important;opacity:1 !important;}
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
/* name + email button on one line */
.sp-name-row{display:flex;align-items:center;gap:10px;}
.sp-mail, .sp-mail:visited{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;
    border-radius:50%;border:1px solid var(--sp-border);background:var(--sp-surface);color:var(--sp-muted) !important;
    text-decoration:none !important;font-size:15px;line-height:1;flex-shrink:0;transition:all .15s;}
.sp-mail:hover{border-color:#B31B21;color:#B31B21 !important;background:rgba(179,27,33,.06);}
.sp-id{font-size:13px;color:var(--sp-muted);margin-top:2px;}
.sp-id b{color:var(--sp-text);}
.sp-fact-label{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--sp-muted);}
.sp-fact-value{font-size:16px;font-weight:700;color:var(--sp-text);margin-top:8px;}

/* ---- notice ---- */
.sp-note{display:flex;gap:12px;align-items:flex-start;border-radius:12px;padding:12px 16px;font-size:13px;line-height:1.55;
    margin:var(--sp-block-gap) 0 var(--sp-block-gap) 0;background:#FFFBEB;border:1px solid #FFCA06;color:#DFB000;}
/* notice box, exact Figma colors: fill #FFFBEB / outline #FFCA06 / text #DFB000 / icon #FFCA06 */
.sp-note b{color:#DFB000;}
html[data-eo-theme="dark"] .sp-note{background:rgba(234,179,8,.10);border-color:rgba(234,179,8,.3);color:#E5E7EB;}
html[data-eo-theme="dark"] .sp-note b{color:#FDE047;}
.sp-note-view{background:var(--sp-soft);border-color:var(--sp-border);color:var(--sp-muted);}
.sp-note-view b{color:var(--sp-text);}   /* view-only notice keeps its grey look */
.sp-note-view .sp-note-icon{border-color:var(--sp-muted);color:var(--sp-muted);}
.sp-note-icon{border:1.5px solid #FFCA06;color:#FFCA06;border-radius:50%;width:20px;height:20px;flex-shrink:0;
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
[class*="st-key-sp_pill_"] button,
[class*="st-key-sp_pill_"] button *,
.sp-static-pill {
    white-space: nowrap !important;
    word-break: keep-all !important;
    flex-wrap: nowrap !important;
}
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

/* ---- US-46 one-page summary row (between the pillar cards and the save bar) ---- */
.st-key-sp_onepager{
    background:var(--sp-surface);border:1px solid var(--sp-border);
    border-radius:var(--sp-card-radius);padding:14px var(--sp-card-pad) !important;
    margin-top:var(--sp-block-gap);
    display:flex !important;flex-direction:row !important;
    align-items:center !important;justify-content:space-between !important;gap:16px !important;
}
.st-key-sp_onepager [data-testid="stElementContainer"]{width:auto !important;flex:0 0 auto !important;}
.sp-op-label{font-size:13px;font-weight:700;color:var(--sp-text);}
.sp-op-hint{font-size:12px;color:var(--sp-muted);margin-top:2px;}
.st-key-sp_op_btn button{background:#B31B21 !important;border-color:#B31B21 !important;color:#FFFFFF !important;
    font-weight:700 !important;white-space:nowrap !important;}
.st-key-sp_op_btn button *{color:#FFFFFF !important;}

/* ============================================================
   RESPONSIVE DESIGN (Tablets & Phones: Portrait and Landscape)
   ============================================================ */

/* Tablet & Mobile (<= 1150px): stack milestone cards and adjust header */
@media (max-width: 1150px) {
  .sp-page-title { font-size: 2.0rem !important; }
  .st-key-sp_top [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap: 12px !important;
  }
  .st-key-sp_top [data-testid="stColumn"]:first-child {
    flex: 1 1 300px !important;
    min-width: 260px !important;
  }
  .st-key-sp_top [data-testid="stColumn"]:last-child {
    flex: 1 1 260px !important;
    min-width: 240px !important;
  }
  /* Milestone cards stack vertically with 100% width */
  .st-key-sp_pillars [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 14px !important;
  }
  .st-key-sp_pillars [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
}

/* Tablet & Landscape phones (641px - 1150px): wrap save bar cleanly */
@media (max-width: 1150px) and (min-width: 641px) {
  .st-key-sp_actions [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap: 12px !important;
  }
  .st-key-sp_actions [data-testid="stColumn"]:first-child {
    flex: 1 1 100% !important;
    width: 100% !important;
    margin-bottom: 2px;
  }
  .st-key-sp_actions [data-testid="stColumn"]:not(:first-child) {
    flex: 1 1 calc(50% - 12px) !important;
  }
  .st-key-sp_save button,
  .st-key-sp_discard button {
    width: 100% !important;
    min-height: 40px !important;
    white-space: nowrap !important;
  }
}

/* Medium tablets / Landscape phones (<= 950px): student info card */
@media (max-width: 950px) {
  .st-key-sp_head [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
  }
  .st-key-sp_head [data-testid="stColumn"]:first-child {
    flex: 1 1 100% !important;
    width: 100% !important;
    border-bottom: 1px solid var(--sp-border) !important;
  }
  .st-key-sp_head [data-testid="stColumn"]:not(:first-child) {
    flex: 1 1 calc(33.33% - 1px) !important;
    min-width: 130px !important;
  }
}

/* Mobile Phones (<= 640px): portrait phone layout */
@media (max-width: 640px) {
  .sp-page-title {
    font-size: 1.55rem !important;
    line-height: 1.2 !important;
  }
  .sp-page-sub {
    font-size: 13px !important;
  }
  .st-key-sp_top [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 12px !important;
  }
  .st-key-sp_top [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  /* Student info card on phone */
  .st-key-sp_head [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
  }
  .st-key-sp_head [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
    padding: 12px 14px !important;
    min-height: auto !important;
    border-left: none !important;
    border-bottom: 1px solid var(--sp-border) !important;
  }
  .st-key-sp_head [data-testid="stColumn"]:last-child {
    border-bottom: none !important;
  }

  /* Pillar card internals */
  [class*="st-key-sp_pillar_"] [data-testid="stHorizontalBlock"] {
    flex-direction: row !important;
    align-items: center !important;
    justify-content: space-between !important;
  }

  /* Save / Discard bar on phone */
  .st-key-sp_actions {
    padding: 14px !important;
  }
  .st-key-sp_actions [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 10px !important;
  }
  .st-key-sp_actions [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
  .st-key-sp_actions .sp-hint {
    text-align: center;
    margin-bottom: 4px;
    font-size: 12.5px;
  }
  .st-key-sp_save button,
  .st-key-sp_discard button {
    width: 100% !important;
    min-height: 42px !important;
    white-space: nowrap !important;
    font-size: 13.5px !important;
  }

  /* US-46 one-page row: stack label above button on phone */
  .st-key-sp_onepager {
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 10px !important;
    padding: 14px !important;
  }
  .st-key-sp_onepager [data-testid="stElementContainer"] {
    width: 100% !important;
  }
  .st-key-sp_op_btn button {
    width: 100% !important;
    min-height: 42px !important;
    font-size: 13.5px !important;
  }
}

/* Landscape Phones (short viewport height <= 520px) */
@media (max-height: 520px) and (orientation: landscape) {
  .st-key-sp_top { padding-bottom: 6px !important; margin-bottom: 4px !important; }
  .sp-page-title { font-size: 1.45rem !important; }
  .sp-page-sub { font-size: 12px !important; margin-top: 2px !important; }
  .st-key-sp_head { margin-top: 10px !important; }
  .st-key-sp_head [data-testid="stColumn"] { padding: 8px 12px !important; min-height: auto !important; }
  .sp-name { font-size: 17px !important; }
  .sp-note { margin: 10px 0 !important; padding: 8px 12px !important; font-size: 12px !important; }
  .sp-section { font-size: 16px !important; }
  [class*="st-key-sp_pillar_"] { padding: 12px 14px !important; }
  .sp-pillar-title { font-size: 16px !important; margin-top: 8px !important; }
  .st-key-sp_actions { margin-top: 10px !important; padding: 8px 12px !important; }
  .st-key-sp_onepager { margin-top: 10px !important; padding: 8px 12px !important; }
}

/* Phones: the title and the student picker are stacked there, so each is only as tall as its content
   (the 300px / 260px / 100% flex sizes above become HEIGHTS once stacked -> tall, mostly empty boxes) */
@media (max-width: 640px) {
  .st-key-sp_top [data-testid="stColumn"],
  .st-key-sp_top [data-testid="stColumn"]:first-child,
  .st-key-sp_top [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
}

/* Student card, every screen size: Current Cohort / Assigned Adviser are ONE block (label + value), but
   Enrollment Status is two (label, then the pill widget), which made its cell taller, so when the cells are
   centred its label sat higher and its pill lower than the others. Give it the same footprint:
   label box = the label text, value 22px below the label's top, nothing extra below. */
.st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] { gap: 5px !important; }
.st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stElementContainer"]:has(.sp-fact-label) {
  margin-top: -14px !important; margin-bottom: 0 !important;
}
/* the pill: a text block when read-only, a clickable popover (different wrapper) when the user can edit */
.st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] > :not(:has(.sp-fact-label)) {
  height: 11px !important; min-height: 0 !important; overflow: visible !important;   /* same footprint for both */
}
/* phones: the facts are stacked there (nothing to line up with), so the pill keeps its natural size inside the card */
@media (max-width: 640px) {
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] { gap: 4px !important; }
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stElementContainer"]:has(.sp-fact-label) {
    margin-top: 0 !important;
  }
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] > :not(:has(.sp-fact-label)) {
    height: auto !important; min-height: 36px !important;
  }
}
/* tablets (portrait + landscape): the cells are narrow there, so "ENROLLMENT STATUS" can wrap to two lines and
   the desktop footprint above put the pill on top of the label. Natural layout: label, small space, pill. */
@media (min-width: 641px) and (max-width: 1150px) {
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] { gap: 2px !important; }
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stElementContainer"]:has(.sp-fact-label) {
    margin-top: 0 !important; height: auto !important; min-height: 0 !important;
  }
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stMarkdownContainer"]:has(.sp-fact-label) {
    margin-bottom: 0 !important; min-height: 0 !important;   /* label box = the label text (1 or 2 lines) */
  }
  .st-key-sp_head [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] > :not(:has(.sp-fact-label)) {
    height: auto !important; min-height: 32px !important;
  }
}
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

# The program must be picked on the Student Roster first. No pinned / default program is loaded here,
# so opening Student Profile straight from the sidebar shows nothing until that's done.
# "All Programs" on the roster is saved as roster_program_id = None -> students from EVERY program are listed.
if "roster_program_id" not in st.session_state:
    st.warning("⏳ No program selected yet. Go to the Student Roster page and pick a program first.")
    st.stop()

active_program_id = st.session_state.get("roster_program_id")   # None = All Programs
active_code = st.session_state.get("roster_program_code", "") or ("All Programs" if active_program_id is None else "")
all_programs = active_program_id is None

df = cached_roster(active_program_id)
header_cohort = "All Cohorts"

# ---------------------------------------------------------------
# Title row: title + subtitle | student picker
# ---------------------------------------------------------------
selected_label = None
student_options = {}
with st.container(key="sp_top"):
    c_title, c_pick = st.columns([4.8, 1.2], vertical_alignment="top")   # same split as the student card; top = title starts at the top like Executive Overview
    with c_title:
        st.markdown(
            '<div><div class="sp-page-title">Student Profile</div>'
            '<div class="sp-page-sub">Review and update a student\'s program milestones</div></div>',
            unsafe_allow_html=True,
        )
    if not df.empty:
        if all_programs and "ProgramCode" in df.columns:
            # All Programs: show each student's program in the list, e.g. "2024101001 — Andres Abad (MBA)"
            student_options = {
                f"{num} — {name} ({code})" if code else f"{num} — {name}": str(num)
                for num, name, code in zip(df["StudentNumber"], df["Student"], df["ProgramCode"].fillna(""))
            }
        else:
            student_options = {
                f"{num} — {name}": str(num)
                for num, name in zip(df["StudentNumber"], df["Student"])
            }
        student_ids = list(student_options.values())
        labels = list(student_options.keys())
        # A student clicked on the Student Roster (?student_id=...) or on the Executive Overview table
        # (selected_student_override). Applied once, so picking another student in the list still works.
        clicked_id = st.session_state.pop("selected_student_override", None)   # a fresh click: always applied
        target_student_id = clicked_id or st.query_params.get("student_id")
        if target_student_id:
            target_str = str(target_student_id).strip()
            if target_str in student_ids and (clicked_id or st.session_state.get("sp_applied_target") != target_str):
                st.session_state["sp_student"] = labels[student_ids.index(target_str)]
                st.session_state["sp_applied_target"] = target_str
        if st.session_state.get("sp_student") not in labels:
            st.session_state.pop("sp_student", None)   # no student is opened by default
        with c_pick:
            with st.container(key="sp_picker"):
                selected_label = st.selectbox("Select student", labels, index=None, key="sp_student",
                                              placeholder="Choose a student")

if df.empty:
    st.info("No student records available." if all_programs
            else f"No student records available for the {active_code} program.")

elif not selected_label:
    st.info("Select a student from the list above, or click a student's name on the Student Roster.")

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

    detail = cached_lifecycle_detail(selected_id) or {}
    current = {k: (detail.get(f"{k}_status") or student.get(STATUS_FIELD[k]) or "") for k, *_ in PILLARS}
    updated = {k: detail.get(f"{k}_updated") for k, *_ in PILLARS}

    editable = bool(user_id) and cached_can_edit(user_id)
    # US-30: stage names of the student's program (with "All Programs", the student's own program)
    student_program_code = str(student.get("ProgramCode") or "")
    label_program_id = active_program_id if not all_programs else cached_program_ids().get(student_program_code)
    stage_labels = cached_stage_labels(label_program_id)
    pick_keys = [f"sp_pick_{k}_{selected_id}" for k, *_ in PILLARS] + [f"sp_pick_enroll_{selected_id}"]

    # ----------------- Student card -----------------
    with st.container(key="sp_head"):
        c_who, c_cohort, c_adv, c_enroll = st.columns([2.2, 1.1, 1.5, 1.2])
        with c_who:
            email = cached_student_email(selected_id)
            mail_btn = (f'<a class="sp-mail" href="mailto:{html.escape(email, quote=True)}" '
                        f'title="Email {html.escape(email, quote=True)}">✉</a>') if email else ""
            st.markdown(
                f'<div class="sp-block"><div class="sp-name-row"><div class="sp-name">{html.escape(student_name)}</div>'
                f'{mail_btn}</div>'
                f'<div class="sp-id">Student Number · <b>{html.escape(selected_id)}</b>'
                + (f' · Program · <b>{html.escape(student_program_code)}</b>' if student_program_code else '')
                + '</div></div>',
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
            f"<b>Manual Milestone Override Active:</b> Enrollment, {html.escape(stage_labels['Coursework'])}, "
            f"{html.escape(stage_labels['CompExam'])}, and {html.escape(stage_labels['Capstone'])} "
            "statuses can be updated here. Saving logs each change in its status history table and "
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
            title = stage_labels.get(PILLAR_LABEL_KEY[key], title)   # US-30: label for this program
            options = cached_status_options(key, tuple(preferred))
            if current[key] and current[key] not in options:
                options = [current[key]] + options          # keep an unexpected DB value visible
            with col:
                with st.container(key=f"sp_pillar_{key}"):
                    st.markdown(
                        f'<div class="sp-block"><div class="sp-pill-top"><span class="sp-tag">{tag}</span>'
                        f'<span class="sp-override">{"Step Manual Override" if editable else "Read only"}</span></div>'
                        f'<div class="sp-pillar-title">{html.escape(title)}</div>'
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

    # ----------------- US-46 One-page summary -----------------
    # Sits between the pillar cards and the save bar. Single download button (no two-step
    # "click Generate then a second button appears" flow, which shifted the layout on mobile).
    # Pillar titles use the program's stage labels (US-30), not the default PILLARS titles.
    _pillars_display = [
        (stage_labels.get(PILLAR_LABEL_KEY[key], title), current[key] or "—", fmt_date(updated[key]))
        for key, _tag, title, _pref in PILLARS
    ]
    _at_risk_row = get_student_at_risk_flag(selected_id, active_program_id)
    _notes = get_student_notes(selected_id)
    _onepager_html = build_student_onepager_html(
        student_name, selected_id, cohort, adviser_text, _pillars_display, _at_risk_row, _notes
    )

    with st.container(key="sp_onepager"):
        st.markdown(
            '<div><div class="sp-op-label">🖨️ One-Page Advising Summary</div>'
            '<div class="sp-op-hint">Lifecycle status, at-risk flags and adviser notes — '
            'open the file and use your browser\'s Print (Ctrl+P) to save as PDF.</div></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="sp_op_btn"):
            st.download_button(
                "Download Summary (HTML)",
                data=_onepager_html,
                file_name=f"{selected_id}_summary.html",
                mime="text/html",
                key=f"sp_onepager_dl_{selected_id}",
            )

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

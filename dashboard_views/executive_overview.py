# EXEC OVERVIEW MERGE
# EXEC OVERVIEW 9-30-26 (QA fixes: Excel key metrics, Philippine export time, wider Program filter, tablet / phone table)
import html
import io
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import mysql.connector
from db_connect import (
    get_db_connection,
    LIFECYCLE_STATUS_MAP,
    format_mysql_error,
    get_available_cohorts,
    check_column_exists,
    find_invalid_mappings,
    get_schema_load_error,
    get_user_program,
    get_flagged_students,
    get_kpi_tiles,
    get_stage_labels,   # US-30
)
from dashboard_views.components import DARK_MODE_CSS, set_header_context
from field_mapping import load_mappings

st.set_page_config(page_title="Executive Overview", layout="wide")
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view executive reporting.")
    st.stop()


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
INACTIVE_STAGE = "Inactive"   # students with any stage marked Cancelled (dropped out)

STAGE_ORDER = ["Coursework", "Comprehensive Exam", "Capstone", "Completed", INACTIVE_STAGE]

STAGE_COLORS = {
    "Coursework": "#B91B21",
    "Comprehensive Exam": "#FFCA06",
    "Capstone": "#55AB22",
    "Completed": "#4A7CF2",
    INACTIVE_STAGE: "#9CA3AF",   # gray
}

COURSEWORK_DONE = "Completed"
COMPEXAM_DONE = "Passed"
CAPSTONE_DONE = "Defended for Completion"

STAGE_STATUS_COL = {
    "Coursework": "CourseworkStatus",
    "Comprehensive Exam": "CompExamStatus",
    "Capstone": "CapstoneStatus",
}

AT_RISK_STATUSES = {"Incomplete", "Cancelled"}
ON_TIME_TRUE = {"yes", "y", "true", "1", "on time", "on-time"}
LAST_UPDATED_CANDIDATES = ["LastUpdated", "UpdatedAt", "DateUpdated", "LastModified", "ModifiedAt"]
ENROLLMENT_OPTIONS = ["All", "Enrolled", "Conditionally Enrolled"]
TERM_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3, "autumn": 3}
# Times shown in exports use Philippine time (UTC+8, same as the nightly refresh). The server itself
# runs in UTC, so the plain server clock printed a time 8 hours behind.
APP_TZ = timezone(timedelta(hours=8))


def now_local():
    return datetime.now(APP_TZ)


# US-30: stage names come from Admin Config (Program_Stage.StageLabel), per program.
# Inside this file stages keep their fixed keys ("Coursework", "Comprehensive Exam", "Capstone");
# stage_name() turns a key into the label the user should see.
STAGE_PILLAR = {"Coursework": "Coursework", "Comprehensive Exam": "CompExam", "Capstone": "Capstone"}
_stage_labels = {}   # filled at the top of render_executive_overview() for the selected program


def stage_name(stage):
    """Display name for a stage key (program-specific label, US-30)."""
    pillar = STAGE_PILLAR.get(stage)
    return _stage_labels.get(pillar, stage) if pillar else stage


@st.cache_data(ttl=60, show_spinner=False)
def cached_stage_labels(program_id):
    return get_stage_labels(program_id)


@st.cache_data(ttl=300, show_spinner=False)
def cached_kpi_tiles(program_id):
    """KPI tile config (Admin Config clears this cache when tiles are saved)."""
    return get_kpi_tiles(program_id=program_id, visible_only=True)


def eo_col_labels():
    return ["Student", "Cohort", stage_name("Coursework"), stage_name("Comprehensive Exam"),
            stage_name("Capstone"), "Time in Stage", "Flag"]


DRILL_STAGE_KEY = "eo_drill_stage"        # session_state key: the stage currently drilled into
DRILL_CLEAR_LABEL = "← Back to all stages"
DRILL_CHART_VERSION_KEY = "eo_drill_chart_v"   # bumped by "Back" to clear the chart's bar selection

# ---------------------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------------------
PAGE_CSS = """
<style>
/* ---- colour tokens: light by default, dark when Streamlit's theme is dark ---- */
.stApp{
  --eo-surface:#FFFFFF; --eo-surface-2:#F9FAFB; --eo-border:#E5E7EB; --eo-border-soft:#F1F2F4; --eo-line:#D1D5DB;
  --eo-text:#0F172A; --eo-text-2:#111827; --eo-body:#374151; --eo-label:#4B5563; --eo-muted:#6B7280; --eo-faint:#9CA3AF;
  --eo-shadow:0 1px 2px rgba(16,24,40,.05); --eo-tip-shadow:0 8px 24px rgba(16,24,40,.14);
  --eo-up:#2E9E3E; --eo-down:#C62828; --eo-chart-line:#111827; --eo-chart-text:#4B5563; --eo-chart-grid:#E5E7EB;
  --pg-bg:#ECFDF3; --pg-fg:#15803D; --pg-bd:#BBF7D0;   --pr-bg:#FEF2F2; --pr-fg:#B91C1C; --pr-bd:#FECACA;
  --pb-bg:#EFF6FF; --pb-fg:#1D4ED8; --pb-bd:#BFDBFE;   --pa-bg:#FFFBEB; --pa-fg:#B45309; --pa-bd:#FDE68A;
  --px-bg:#F3F4F6; --px-fg:#4B5563; --px-bd:#E5E7EB;
  --py-bg:#FEF9C3; --py-fg:#A16207; --py-bd:#FDE047;
  --eo-seg-bg:#F1F2F4;
}
html[data-eo-theme="dark"] .stApp{
  --eo-surface:#161D2B; --eo-surface-2:#1B2333; --eo-border:#263044; --eo-border-soft:#1E293B; --eo-line:#334155;
  --eo-text:#F1F5F9; --eo-text-2:#E2E8F0; --eo-body:#CBD5E1; --eo-label:#94A3B8; --eo-muted:#94A3B8; --eo-faint:#64748B;
  --eo-shadow:none; --eo-tip-shadow:0 8px 24px rgba(0,0,0,.55);
  --eo-up:#34D399; --eo-down:#F87171; --eo-chart-line:#E2E8F0; --eo-chart-text:#CBD5E1; --eo-chart-grid:#263044;
  --pg-bg:rgba(16,185,129,.15); --pg-fg:#34D399; --pg-bd:rgba(16,185,129,.3);
  --pr-bg:rgba(239,68,68,.14);  --pr-fg:#FCA5A5; --pr-bd:rgba(239,68,68,.3);
  --pb-bg:rgba(59,130,246,.15); --pb-fg:#93C5FD; --pb-bd:rgba(59,130,246,.3);
  --pa-bg:rgba(245,158,11,.14); --pa-fg:#FCD34D; --pa-bd:rgba(245,158,11,.3);
  --px-bg:rgba(148,163,184,.12);--px-fg:#CBD5E1; --px-bd:rgba(148,163,184,.24);
  --py-bg:rgba(234,179,8,.15);  --py-fg:#FDE047; --py-bd:rgba(234,179,8,.35);
  --eo-seg-bg:#111827;
}
/* Plotly draws with inline colours; these rules make chart text/lines/grid follow the theme */
.stApp .js-plotly-plot .xtick text,
.stApp .js-plotly-plot .bars .textpoint text{fill:var(--eo-chart-text) !important;}
.stApp .st-key-eo_trend_completion .js-plotly-plot .scatterlayer .textpoint text{fill:var(--eo-chart-line) !important;}
.stApp .st-key-eo_trend_completion .js-plotly-plot .scatterlayer .js-line{stroke:var(--eo-chart-line) !important;}
.stApp .st-key-eo_trend_completion .js-plotly-plot .scatterlayer .point{fill:var(--eo-chart-line) !important;}
/* the two chart cards: same height, top-aligned (the app-wide CSS centres columns vertically) */
.st-key-eo_charts [data-testid="stHorizontalBlock"]{align-items:stretch !important;}
.st-key-eo_charts > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{justify-content:flex-start !important;}
.st-key-eo_charts [data-testid="stVerticalBlockBorderWrapper"]{height:100%;}
/* CHARTS FILL THEIR CARDS: an app-wide rule in components.py turns every element inside a column into a
   flex row, which shrink-wrapped each chart to Plotly's default 700px width (empty space on the right).
   The long selector is on purpose: it has to out-rank that rule. */
.st-key-eo_charts div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has(.js-plotly-plot),
.st-key-eo_charts div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]){
    display:block !important;width:100% !important;min-height:0 !important;}
.st-key-eo_charts [data-testid="stPlotlyChart"]{width:100% !important;}
/* CENTRE each chart inside its card. Plotly draws inside a box with a fixed pixel width (.svg-container);
   when that box is narrower than the card it hugs the left, so the box itself gets auto side margins. */
.st-key-eo_charts .js-plotly-plot{display:block !important;width:100% !important;}
.st-key-eo_charts .js-plotly-plot .plot-container{width:100% !important;display:flex !important;justify-content:center !important;}
.st-key-eo_charts .js-plotly-plot .svg-container{margin-left:auto !important;margin-right:auto !important;
    flex:0 0 auto;max-width:100%;}
/* trend card title row: title + subtitle on the left, Completion % / Students at Risk switch on the right */
.st-key-eo_trend_head [data-testid="stHorizontalBlock"]{align-items:flex-start !important;}
.st-key-eo_trend_switch{display:flex;justify-content:flex-end;width:100%;margin-top:4px;}
.st-key-eo_trend_switch [data-testid="stElementContainer"]{justify-content:flex-end !important;width:100%;}
.st-key-eo_trend_switch [data-testid="stButtonGroup"],
.st-key-eo_trend_switch [role="radiogroup"]{justify-content:flex-end;flex-wrap:nowrap;margin-left:auto;}
/* selected option in the brand red */
.st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"],
.st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"] p{color:#B91B21 !important;}
.st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"]{border-color:#B91B21 !important;
        background:rgba(185,27,33,.06) !important;}
html[data-eo-theme="dark"] .st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"],
html[data-eo-theme="dark"] .st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"] p{color:#F87171 !important;}
.st-key-eo_trend_switch [data-testid^="stBaseButton-segmented_control"] p{font-size:13px;font-weight:600;white-space:nowrap;}
.stApp .js-plotly-plot .gridlayer path{stroke:var(--eo-chart-grid) !important;}
.stApp .js-plotly-plot .xlines-above{stroke:var(--eo-line) !important;}
/* page padding + Streamlit header are handled by render_app_shell() in components.py (shared across pages) */

/* FILTER BOX WIDTH: Program, Cohort and Enrollment Status all use this same width.
   Change the three 300px values together (300px fits "Master of Business Administration"). */
.st-key-eo_filters [data-testid="stColumn"],
.st-key-eo_filters [data-testid="column"] {
    flex: 0 0 300px !important;
    width: 300px !important;
    min-width: 300px !important;
}
/* export buttons (Excel + PDF): the last two columns in the filter row, pushed to the far right */
.st-key-eo_filters [data-testid="stColumn"]:nth-last-child(-n+2),
.st-key-eo_filters [data-testid="column"]:nth-last-child(-n+2) {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
}
.st-key-eo_filters [data-testid="stColumn"]:nth-last-child(2),
.st-key-eo_filters [data-testid="column"]:nth-last-child(2) {
    margin-left: auto !important;
}
/* every filter dropdown fills its own box (same approach the Student Roster filters use) */
.st-key-eo_filters [data-testid="stElementContainer"]:has([data-testid="stSelectbox"]),
.st-key-eo_filters [data-testid="stSelectbox"],
.st-key-eo_filters [data-baseweb="select"] {
    width: 100% !important;
    max-width: none !important;
    min-width: 0 !important;
}

/* page header = title + caption, with the divider line under both (one element = no extra Streamlit gaps) */
.eo-header{padding-bottom:10px;border-bottom:1px solid var(--eo-border);margin:0;}
.eo-title{font-size:2.75rem;font-weight:700;line-height:1.15;color:var(--eo-text);letter-spacing:-.01em;margin:0;}
/* caption under the title: change margin-top to move it closer to / further from the title */
.eo-caption{color:var(--eo-label);font-size:14px;line-height:1.5;margin:4px 0 0 0;}
/* SPACE BETWEEN THE TITLE LINE AND THE FILTERS: change padding-top */
.st-key-eo_filters{padding-top:16px;}
/* SPACE BETWEEN EACH FILTER LABEL (e.g. "Enrollment Status") AND ITS DROPDOWN: change margin-bottom */
.st-key-eo_filters [data-testid="stWidgetLabel"]{margin-bottom:4px;min-height:0;}
.eo-subtitle{color:var(--eo-label);font-size:14px;margin:-14px 0 14px 0;}
.eo-kpi-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin:6px 0 18px 0;}
@media (max-width:1200px){.eo-kpi-row{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media (max-width:700px){.eo-kpi-row{grid-template-columns:repeat(1,minmax(0,1fr));}}
.eo-kpi{background:var(--eo-surface);border:1px solid var(--eo-border);border-radius:12px;padding:18px 20px;
        box-shadow:var(--eo-shadow);min-height:122px;display:flex;flex-direction:column;}
.eo-kpi-label{font-size:12px;letter-spacing:.03em;text-transform:uppercase;color:var(--eo-label);}
.eo-kpi-value{font-size:34px;font-weight:700;color:var(--eo-text);line-height:1.1;margin:12px 0 8px 0;}
.eo-kpi-sub{font-size:12px;color:var(--eo-muted);margin-top:auto;}
.eo-kpi{position:relative;}
.eo-info{position:absolute;top:14px;right:14px;width:20px;height:20px;border-radius:50%;
        border:1.5px solid var(--eo-muted);color:var(--eo-muted);font-family:inherit;font-size:12px;font-weight:600;
        line-height:17px;font-style:normal;text-align:center;cursor:help;outline:none;}
.eo-info:hover,.eo-info:focus{border-color:var(--eo-text);color:var(--eo-text);}
.eo-tip{visibility:hidden;opacity:0;transition:opacity .15s;position:absolute;top:28px;right:-8px;z-index:1000;
        width:390px;max-width:90vw;background:var(--eo-surface);border:1px solid var(--eo-border);border-radius:10px;padding:14px 16px;
        box-shadow:var(--eo-tip-shadow);font-family:inherit;font-size:13px;line-height:1.6;
        font-weight:400;letter-spacing:0;text-transform:none;color:var(--eo-body);text-align:left;cursor:default;
        white-space:normal;}
.eo-info:hover .eo-tip,.eo-info:focus .eo-tip,.eo-info:focus-within .eo-tip{visibility:visible;opacity:1;}
.eo-tip-formula{font-weight:600;color:var(--eo-text);margin-bottom:10px;white-space:normal;}
/* let the tooltip spill outside Streamlit's markdown wrappers instead of being clipped */
[data-testid="stElementContainer"]:has(.eo-kpi-row),
[data-testid="element-container"]:has(.eo-kpi-row),
[data-testid="stMarkdown"]:has(.eo-kpi-row),
[data-testid="stMarkdownContainer"]:has(.eo-kpi-row){overflow:visible !important;position:relative;z-index:20;}
.eo-tip-row{display:flex;align-items:baseline;gap:6px;}
.eo-tip-dots{flex:1;border-bottom:1px solid var(--eo-line);transform:translateY(-4px);}
.eo-tip-caption{margin-top:8px;padding-top:8px;border-top:1px solid var(--eo-border-soft);font-size:12px;color:var(--eo-muted);}
.eo-placeholder{color:var(--eo-faint);font-style:italic;}
.eo-flat{color:var(--eo-muted);}
.eo-up{color:var(--eo-up);} .eo-down{color:var(--eo-down);} .eo-risk{color:var(--eo-down);}

div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--eo-surface);border:1px solid var(--eo-border) !important;
        border-radius:12px !important;box-shadow:var(--eo-shadow);}
.eo-card-head{display:flex;flex-direction:column;align-items:flex-start;}
.eo-card-title{display:block;font-size:20px;font-weight:700;color:var(--eo-text);margin:4px 0 2px 4px;}
.eo-card-sub{display:block;font-size:12px;color:var(--eo-muted);margin:0 0 4px 4px;}

.eo-table-wrap{background:var(--eo-surface);border:1px solid var(--eo-border);border-radius:12px;overflow:auto;
        max-height:560px;margin-top:18px;box-shadow:var(--eo-shadow);}
.eo-table{width:100%;border-collapse:collapse;font-size:14px;color:var(--eo-text-2);margin:0;}
.eo-table th{position:sticky;top:0;z-index:1;background:var(--eo-surface-2);text-align:left;font-size:12px;
        font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--eo-muted);
        padding:12px 18px;border:none;border-bottom:1px solid var(--eo-border);}
.eo-table td{padding:10px 18px;border:none;border-bottom:1px solid var(--eo-border-soft);vertical-align:middle;white-space:nowrap;}
.eo-table tr:last-child td{border-bottom:none;}
.eo-student{display:flex;align-items:center;gap:12px;}
.eo-avatar{width:34px;height:34px;border-radius:50%;background:#475569;color:#FFFFFF;font-size:13px;
        font-weight:600;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.eo-name{font-weight:600;color:var(--eo-text-2);} .eo-id{font-size:12px;color:var(--eo-muted);}
.eo-pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid;}
.pill-green{background:var(--pg-bg);color:var(--pg-fg);border-color:var(--pg-bd);}
.pill-red{background:var(--pr-bg);color:var(--pr-fg);border-color:var(--pr-bd);}
.pill-blue{background:var(--pb-bg);color:var(--pb-fg);border-color:var(--pb-bd);}
.pill-amber{background:var(--pa-bg);color:var(--pa-fg);border-color:var(--pa-bd);}
.pill-yellow{background:var(--py-bg);color:var(--py-fg);border-color:var(--py-bd);}
.pill-gray{background:var(--px-bg);color:var(--px-fg);border-color:var(--px-bd);}
.eo-muted{color:var(--eo-muted);}

/* ---- student table (built from Streamlit rows so the names can open Student Profile) ---- */
.st-key-eo_table{background:var(--eo-surface);border:1px solid var(--eo-border);border-radius:12px;
        box-shadow:var(--eo-shadow);margin-top:18px;gap:0 !important;overflow:hidden;}
.st-key-eo_table_head{background:var(--eo-surface-2);border-bottom:1px solid var(--eo-border);padding:12px 18px;}
.eo-th{font-size:12px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--eo-muted);}
.st-key-eo_table_rows{gap:0 !important;}
.st-key-eo_table_rows [data-testid="stHorizontalBlock"]{padding:10px 18px;border-bottom:1px solid var(--eo-border-soft);
        align-items:center;}
/* name + student number sit right on top of each other */
.st-key-eo_table_rows [data-testid="stColumn"],
.st-key-eo_table_rows [data-testid="stColumn"] > div,
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stVerticalBlock"]{gap:0 !important;row-gap:0 !important;}
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stElementContainer"],
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stMarkdown"],
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stTooltipHoverTarget"]{min-height:0 !important;height:auto !important;}
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stElementContainer"]{margin:0 !important;}
.st-key-eo_table_rows [data-testid="stButton"]{margin:0 !important;padding:0 !important;line-height:1.3;}
.st-key-eo_table_rows .eo-id{margin-top:2px;line-height:1.3;}   /* space between name and student number */
.st-key-eo_table [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
.eo-cell{font-size:14px;color:var(--eo-text-2);}
/* student name = clickable link-style button that opens their Student Profile */
/* strip the button look completely (any button type, overrides the app-wide button styling):
   no box, no border, no fill, no shadow, no focus ring -> just the name as text */
.st-key-eo_table_rows [data-testid="stButton"] button,
.st-key-eo_table_rows [data-testid^="stBaseButton"],
.st-key-eo_table_rows [data-testid="stButton"] button:hover,
.st-key-eo_table_rows [data-testid="stButton"] button:focus,
.st-key-eo_table_rows [data-testid="stButton"] button:focus-visible,
.st-key-eo_table_rows [data-testid="stButton"] button:active{
        border:none !important;outline:none !important;box-shadow:none !important;background:transparent !important;
        padding:0 !important;margin:0 !important;min-height:0 !important;height:auto !important;width:auto !important;
        max-width:100% !important;border-radius:0 !important;justify-content:flex-start !important;text-align:left !important;}
.st-key-eo_table_rows [data-testid="stButton"] button p{font-size:14px !important;font-weight:600 !important;
        color:var(--eo-text-2) !important;margin:0 !important;line-height:1.3 !important;
        white-space:normal !important;overflow:visible !important;text-overflow:clip !important;text-decoration:none !important;}
.st-key-eo_table_rows [data-testid="stButton"] button:hover p{color:#B91B21 !important;text-decoration:underline !important;}
.st-key-eo_table_rows button[kind="tertiary"],
.st-key-eo_table_rows [data-testid="stBaseButton-tertiary"]{padding:0 !important;min-height:0 !important;height:auto !important;
        line-height:1.3 !important;justify-content:flex-start;}
.st-key-eo_table_rows button[kind="tertiary"] p,
.st-key-eo_table_rows [data-testid="stBaseButton-tertiary"] p{font-size:14px;font-weight:600;color:var(--eo-text-2);margin:0 !important;line-height:1.3;}
.st-key-eo_table_rows button[kind="tertiary"]:hover p,
.st-key-eo_table_rows [data-testid="stBaseButton-tertiary"]:hover p{color:#B91B21;text-decoration:underline;}

/* ===== TABLET / PHONE =====
   The student table has 7 columns, which needs about 1100px. On narrower screens it keeps that readable width
   and scrolls sideways (header and rows scroll together) instead of squeezing the columns together. */
.st-key-eo_table{overflow-x:auto !important;overflow-y:visible;-webkit-overflow-scrolling:touch;}
@media (max-width:1100px){
  .st-key-eo_table [data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;min-width:1100px;}
  .st-key-eo_table [data-testid="stColumn"]{min-width:0 !important;}
  .st-key-eo_table_head,.st-key-eo_table_rows{min-width:1100px;}
}
.st-key-eo_table .eo-pill{white-space:normal;line-height:1.25;}
.st-key-eo_table .eo-th{white-space:normal;overflow-wrap:anywhere;line-height:1.25;}
</style>
"""

PILL_CLASS = {
    "Completed": "pill-green",
    "Passed": "pill-green",
    "Defended for Completion": "pill-green",
    "Cancelled": "pill-red",
    "In-Progress": "pill-yellow",
    "Pending": "pill-yellow",
    "Incomplete": "pill-red",
}


# ---------------------------------------------------------------------------
# DATA ACCESS
# ---------------------------------------------------------------------------
def _find_last_updated_column(cur):
    """Which LastUpdated-style column Student_Lifecycle has, found with ONE query (was one per candidate)."""
    try:
        placeholders = ", ".join(["%s"] * len(LAST_UPDATED_CANDIDATES))
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Student_Lifecycle' "
            f"AND COLUMN_NAME IN ({placeholders})",
            LAST_UPDATED_CANDIDATES,
        )
        found = set()
        for row in cur.fetchall():
            name = row["COLUMN_NAME"] if isinstance(row, dict) else row[0]
            found.add(name.decode() if isinstance(name, (bytes, bytearray)) else name)
    except Exception:
        return None
    return next((c for c in LAST_UPDATED_CANDIDATES if c in found), None)


@st.cache_data(ttl=300)
def _load_programs():
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT DATABASE() AS db")
        db_name = cur.fetchone()["db"]
        cur.execute(
            "SELECT ProgramID, ProgramCode, ProgramName "
            "FROM Program WHERE IsActive = 1 ORDER BY ProgramName"
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    if not rows:
        raise RuntimeError(f"no active rows in Program (app is connected to database '{db_name}')")
    return rows


def get_program_options():
    all_option = {"ProgramID": None, "ProgramCode": "All", "ProgramName": "All Programs"}
    try:
        return [all_option] + _load_programs()
    except mysql.connector.Error as err:
        st.warning(f"Couldn't load programs: {format_mysql_error(err)}")
    except Exception as e:
        st.warning(f"Couldn't load programs: {e}")
    return [all_option]


@st.cache_data(ttl=300, show_spinner="Loading executive data…")
def get_executive_data() -> pd.DataFrame:
    """One row per student with lifecycle statuses, adviser, and LastUpdated."""
    conn = get_db_connection()          # ONE connection for everything below
    try:
        cur = conn.cursor()
        last_col = _find_last_updated_column(cur)
        cur.close()
        df = _run_executive_query(conn, last_col)
    finally:
        conn.close()
    return _prepare_executive_df(df)


def _run_executive_query(conn, last_col) -> pd.DataFrame:
    last_sql = f"sl.`{last_col}` AS LastUpdated" if last_col else "NULL AS LastUpdated"

    query = f"""
    SELECT
        s.StudentNumber,
        s.ProgramID,
        p.ProgramCode,
        s.FirstName,
        s.LastName,
        s.Cohort,
        s.EnrollmentStatus,
        adv.Adviser,
        sl.CourseworkStatus,
        sl.CompExamStatus,
        sl.CapstoneStatus,
        sl.GraduateOnTime,
        {last_sql}
    FROM Students s
    LEFT JOIN Program p ON s.ProgramID = p.ProgramID
    LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
    LEFT JOIN (
        SELECT sa.StudentNumber,
               GROUP_CONCAT(a.AdviserName ORDER BY a.AdviserName SEPARATOR ', ') AS Adviser
        FROM Student_Adviser sa
        JOIN Adviser a ON sa.AdviserID = a.AdviserID
        GROUP BY sa.StudentNumber
    ) adv ON adv.StudentNumber = s.StudentNumber
    """
    cur = conn.cursor()
    try:
        cur.execute(query)
        rows = cur.fetchall()
        columns = list(cur.column_names)
    finally:
        cur.close()
    return pd.DataFrame(rows, columns=columns)


def _prepare_executive_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates(subset="StudentNumber", keep="first").reset_index(drop=True)

    for col in ["CourseworkStatus", "CompExamStatus", "CapstoneStatus"]:
        df[col] = (
            df[col].astype(str).str.strip().str.lower()
            .map(LIFECYCLE_STATUS_MAP)
            .fillna(df[col])
        )

    # same rules as determine_active_stage(), done for all rows at once instead of row by row
    cw_done = df["CourseworkStatus"].eq(COURSEWORK_DONE)
    ce_done = df["CompExamStatus"].eq(COMPEXAM_DONE)
    cs_done = df["CapstoneStatus"].eq(CAPSTONE_DONE)
    # any stage marked Cancelled = the student dropped out -> Inactive (unless they finished everything)
    is_cancelled = df[["CourseworkStatus", "CompExamStatus", "CapstoneStatus"]].eq("Cancelled").any(axis=1)

    # first matching rule wins
    df["ActiveStage"] = np.select(
        [cw_done & ce_done & cs_done, is_cancelled, ~cw_done, ~ce_done],
        ["Completed", INACTIVE_STAGE, "Coursework", "Comprehensive Exam"],
        default="Capstone",
    )
    df["IsComplete"] = df["ActiveStage"].eq("Completed")
    df["IsInactive"] = df["ActiveStage"].eq(INACTIVE_STAGE)
    current_status = np.select(
        [df["ActiveStage"].eq(stage) for stage in STAGE_STATUS_COL],
        [df[col].astype(object) for col in STAGE_STATUS_COL.values()],
        default=None,
    )
    df["IsAtRisk"] = pd.Series(current_status, index=df.index).isin(AT_RISK_STATUSES)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# FIELD MAPPING CHECK (US-10)
#   Same rule as the Student Roster: if any saved mapping in Admin Configuration
#   points to a column that doesn't exist, the page shows an error instead of data.
#   Uses the schema snapshot in db_connect, so this costs no extra database queries
#   on most reruns (the snapshot refreshes every 60 s, or via "Re-check schema").
# ---------------------------------------------------------------------------
def check_field_mappings():
    """Returns an error message if the saved field mappings are invalid, else None."""
    try:
        mappings = load_mappings()
    except Exception as e:
        return f"Could not load field mappings: {e}"
    invalid = find_invalid_mappings(mappings)
    if not invalid:
        return None
    schema_error = get_schema_load_error()
    if schema_error:
        return f"Could not verify field mappings: {schema_error}"
    details = "; ".join(f"'{label}': '{path}'" for label, path in invalid)
    return f"Invalid or unverified mapping(s) - {details}"


# ---------------------------------------------------------------------------
# BUSINESS LOGIC
# ---------------------------------------------------------------------------
def determine_active_stage(row) -> str:
    """Single-row version of the rules in _prepare_executive_df (kept in sync)."""
    statuses = (row.get("CourseworkStatus"), row.get("CompExamStatus"), row.get("CapstoneStatus"))
    if statuses == (COURSEWORK_DONE, COMPEXAM_DONE, CAPSTONE_DONE):
        return "Completed"
    if "Cancelled" in statuses:
        return INACTIVE_STAGE
    if row.get("CourseworkStatus") != COURSEWORK_DONE:
        return "Coursework"
    if row.get("CompExamStatus") != COMPEXAM_DONE:
        return "Comprehensive Exam"
    return "Capstone"


def cohort_sort_key(cohort):
    """'1Q2425' -> (2024, 1). Falls back to the old '2025 - Fall' style."""
    s = str(cohort).strip().upper()
    m = re.fullmatch(r"(\d)Q(\d{2})(\d{2})", s)
    if m:
        return (2000 + int(m.group(2)), int(m.group(1)), s)
    low = s.lower()
    year = re.search(r"(19|20)\d{2}", low)
    term = next((v for k, v in TERM_ORDER.items() if k in low), 0)
    return (int(year.group()) if year else 0, term, low)


def pct_1dp(part, whole) -> float:
    """part / whole as a percentage with 1 decimal, rounded HALF UP - the same as SQL ROUND() and Excel.
    (Python's own round() sends an exact half to the EVEN digit, so 31.25 came out as 31.2 on the dashboard
    while SQL and Excel showed 31.3.)"""
    if not whole:
        return 0.0
    return float((Decimal(int(part)) * 100 / Decimal(int(whole))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def completion_rate(df: pd.DataFrame) -> float:
    return pct_1dp(df["IsComplete"].sum(), len(df)) if not df.empty else 0.0


def on_time_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    flags = df["GraduateOnTime"].astype(str).str.strip().str.lower().isin(ON_TIME_TRUE)
    return pct_1dp(flags.sum(), len(df))


def lifecycle_counts(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["ActiveStage"].value_counts().reindex(STAGE_ORDER, fill_value=0)
    return counts.rename_axis("Stage").reset_index(name="Count")


def cohort_history(df: pd.DataFrame) -> pd.DataFrame:
    has_flags = "IsFlagged" in df.columns
    rows = [
        {"Cohort": c, "Completion": completion_rate(g), "OnTime": on_time_rate(g),
         "Remaining": int((~g["IsComplete"] & ~g["IsInactive"]).sum()),
         # students flagged At Risk in this cohort (count + % of the cohort)
         "AtRisk": int(g["IsFlagged"].sum()) if has_flags else 0,
         "AtRiskPct": pct_1dp(g["IsFlagged"].sum(), len(g)) if has_flags and len(g) else 0.0}
        for c, g in df.groupby("Cohort")
    ]
    hist = pd.DataFrame(rows, columns=["Cohort", "Completion", "OnTime", "Remaining", "AtRisk", "AtRiskPct"])
    if hist.empty:
        return hist
    hist = hist.iloc[sorted(range(len(hist)), key=lambda i: cohort_sort_key(hist.loc[i, "Cohort"]))]
    return hist.reset_index(drop=True)


def cohort_compare(hist: pd.DataFrame, metric: str, cohort: str):
    """Compare the selected cohort (term) with the one before it.

    Returns (reason, info): reason is "all" (no single cohort picked), "first" (no earlier
    cohort), or "ok" with info = {"delta", "prev_cohort", "prev_value"}.
    """
    if cohort == "All Cohorts":
        return "all", None
    cohorts = list(hist["Cohort"]) if not hist.empty else []
    if cohort not in cohorts or cohorts.index(cohort) == 0:
        return "first", None
    idx = cohorts.index(cohort)
    prev = hist.loc[idx - 1, metric]
    return "ok", {
        "delta": round(hist.loc[idx, metric] - prev, 1),
        "prev_cohort": hist.loc[idx - 1, "Cohort"],
        "prev_value": prev,
    }


# ---------------------------------------------------------------------------
# UI PIECES
# ---------------------------------------------------------------------------
def render_drill_breadcrumb(stage, count):
    """Breadcrumb bar shown above the student table when a stage is drilled into."""
    chip = (f'<span style="display:inline-flex;align-items:center;gap:8px;'
            f'padding:4px 12px;border-radius:999px;background:rgba(185,27,33,.08);'
            f'border:1px solid rgba(185,27,33,.25);color:#B91B21;font-size:13px;font-weight:600;">'
            f'Stage · {html.escape(stage_name(stage))} · {count} student{"s" if count != 1 else ""}</span>')

    c_left, c_right = st.columns([3, 1], vertical_alignment="center")
    with c_left:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<span style="font-size:13px;color:var(--eo-muted);">Cohort by Lifecycle Stage</span>'
            f'<span style="color:var(--eo-faint);">›</span>{chip}</div>',
            unsafe_allow_html=True,
        )
    with c_right:
        if st.button(DRILL_CLEAR_LABEL, key="eo_drill_back", use_container_width=True):
            st.session_state.pop(DRILL_STAGE_KEY, None)
            # new chart key = the chart forgets the clicked bar (otherwise it re-opens the drill-down)
            st.session_state[DRILL_CHART_VERSION_KEY] = st.session_state.get(DRILL_CHART_VERSION_KEY, 0) + 1
            st.rerun()

def delta_html(hist, metric, cohort, kind="pct", higher_is_better=True):
    """Current vs previous term. Green = better, red = worse, grey = no change / nothing to compare."""
    reason, info = cohort_compare(hist, metric, cohort)
    if reason == "all":
        return '<span class="eo-placeholder">Select a cohort to compare</span>'
    if reason == "first":
        return '<span class="eo-placeholder">No previous term</span>'

    delta, prev_c, prev_v = info["delta"], html.escape(str(info["prev_cohort"])), info["prev_value"]
    if kind == "pct":
        amount, prev_txt = f"{abs(delta):.1f} pts", f"{prev_v:.1f}%"
    else:
        amount = f"{abs(int(delta)):,} student{'s' if abs(int(delta)) != 1 else ''}"
        prev_txt = f"{int(prev_v):,}"
    if delta == 0:
        return f'<span class="eo-flat">&#9679; No change vs {prev_c} ({prev_txt})</span>'
    arrow = "▲" if delta > 0 else "▼"
    cls = "eo-up" if (delta > 0) == higher_is_better else "eo-down"
    return f'<span class="{cls}">{arrow} {amount} vs {prev_c} ({prev_txt})</span>'


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def kpi_card(label, value, sub_html="&nbsp;", info_html=None, accent=None):
    """One KPI tile. accent = the tile's colour from Admin Config → KPI Tiles (US-29),
    drawn as a thin bar along the top edge of the card."""
    info = (f'<div class="eo-info" tabindex="0">i<div class="eo-tip">{info_html}</div></div>'
            if info_html else "")
    style = (f' style="border-top:4px solid {accent};"'
             if accent and _HEX_COLOR.match(str(accent)) else "")
    return (
        f'<div class="eo-kpi"{style}>{info}<div class="eo-kpi-label">{label}</div>'
        f'<div class="eo-kpi-value">{value}</div>'
        f'<div class="eo-kpi-sub">{sub_html}</div></div>'
    )


def render_kpi_row(cards):
    st.markdown(f'<div class="eo-kpi-row">{"".join(cards)}</div>', unsafe_allow_html=True)


def remaining_info_html(df: pd.DataFrame) -> str:
    """Tooltip for the Remaining Students tile: the formula, then the split by lifecycle stage."""
    total = len(df)
    completed = int(df["IsComplete"].sum())
    inactive = int(df["IsInactive"].sum())
    breakdown = (
        df.loc[~df["IsComplete"] & ~df["IsInactive"], "ActiveStage"].value_counts()
        .reindex(["Coursework", "Comprehensive Exam", "Capstone"], fill_value=0)
    )
    rows = "".join(
        f'<div class="eo-tip-row"><span style="color:{STAGE_COLORS[stage]};font-weight:600;">{html.escape(stage_name(stage))}</span>'
        f'<span class="eo-tip-dots"></span><span>{n:,}</span></div>'
        for stage, n in breakdown.items()
    )
    return (
        f'<div class="eo-tip-formula">Total Enrolled ({total:,}) &minus; Completed ({completed:,}) '
        f'&minus; Inactive ({inactive:,}) = Total ({total - completed - inactive:,})</div>{rows}'
        '<div class="eo-tip-caption">Remaining students are computed as Total Enrolled minus Completed '
        'and Inactive (dropped out), then split by the lifecycle stage each student is currently in.</div>'
    )


def card_header(title, subtitle):
    st.markdown(
        f'<div class="eo-card-head"><div class="eo-card-title">{title}</div>'
        f'<div class="eo-card-sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


TREND_HEIGHT = 300   # same height as the bar chart, so both cards line up

BASE_LAYOUT = dict(
    height=300,
    autosize=True,
    margin=dict(l=10, r=10, t=30, b=34),     # room under the bars / line for the stage + cohort names
    xaxis=dict(automargin=True),
    plot_bgcolor="rgba(0,0,0,0)",     # transparent: the card colour shows through (light or dark)
    paper_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
    font=dict(size=12, color="#6B7280"),
)


def lifecycle_bar(counts: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=[stage_name(s) for s in counts["Stage"]],   # US-30 labels (customdata keeps the stage key)
            y=counts["Count"],
            marker_color=[STAGE_COLORS[s] for s in counts["Stage"]],
            text=counts["Count"],
            textposition="outside",
            textfont=dict(size=12, color="#4B5563"),
            cliponaxis=False,
            customdata=counts["Stage"].tolist(),      # ← what gets reported when a bar is clicked
            hovertemplate="%{x}: %{y} students<extra></extra>",
        )
    )
    fig.update_layout(**BASE_LAYOUT, bargap=0.3)
    fig.update_yaxes(visible=False, range=[0, max(int(counts["Count"].max()), 1) * 1.2])
    fig.update_xaxes(showgrid=False, showline=True, linecolor="#D1D5DB",
                     tickfont=dict(size=11, color="#6B7280"))
    return fig


def at_risk_trend(hist: pd.DataFrame) -> go.Figure:
    """Students flagged At Risk per cohort (same look as the completion trend, in the at-risk red)."""
    red = "#C62828"
    fig = go.Figure(
        go.Scatter(
            x=hist["Cohort"],
            y=hist["AtRisk"],
            mode="lines+markers+text",
            line=dict(color=red, width=1.5),
            marker=dict(size=6, color=red),
            text=[f"<b>{int(n)}</b>" for n in hist["AtRisk"]],
            textposition="top center",
            textfont=dict(size=12, color=red),
            cliponaxis=False,
            customdata=hist["AtRiskPct"],
            hovertemplate="%{x}: %{y} students at risk (%{customdata:.1f}% of cohort)<extra></extra>",
        )
    )
    lo, hi = hist["AtRisk"].min(), hist["AtRisk"].max()
    pad = max((hi - lo) * 0.35, 2)
    fig.update_layout(**BASE_LAYOUT)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=False,
                     showticklabels=False, range=[max(lo - pad, 0), hi + pad])
    fig.update_xaxes(showgrid=False, type="category", tickfont=dict(size=10, color="#6B7280"))
    return fig


def completion_trend(hist: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=hist["Cohort"],
            y=hist["Completion"],
            mode="lines+markers+text",
            line=dict(color="#111827", width=1.5),
            marker=dict(size=6, color="#111827"),
            text=[f"<b>{v:.1f}%</b>" for v in hist["Completion"]],
            textposition="top center",
            textfont=dict(size=12, color="#111827"),
            cliponaxis=False,
            hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
        )
    )
    lo, hi = hist["Completion"].min(), hist["Completion"].max()
    pad = max((hi - lo) * 0.35, 5)
    fig.update_layout(**BASE_LAYOUT)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=False,
                     showticklabels=False, range=[max(lo - pad, 0), hi + pad])
    fig.update_xaxes(showgrid=False, type="category", tickfont=dict(size=10, color="#6B7280"))
    return fig


def status_pill(value):
    if value is None or pd.isna(value) or str(value).strip().lower() in ("", "none", "nan"):
        return '<span class="eo-muted">—</span>'
    value = str(value)
    # case/spacing-insensitive match, so "In Progress" / "in-progress" still get their colour
    lookup = {k.lower().replace(" ", "-"): v for k, v in PILL_CLASS.items()}
    cls = lookup.get(value.strip().lower().replace(" ", "-"), "pill-gray")
    return f'<span class="eo-pill {cls}">{html.escape(value)}</span>'


STUDENT_PROFILE_PAGE = "dashboard_views/student_profile.py"   # same page the Student Roster links to
EO_ROWS_VISIBLE = 10    # students shown before the table scrolls
EO_MAX_ROWS = 50        # rows built at first (a big drill-down, e.g. 122 Completed, is slow to draw)
EO_ROW_HEIGHT_PX = 64   # height of one row in px (nudge if 10 rows show a bit more / less)
EO_COL_WIDTHS = [2.4, 1.1, 1.3, 1.3, 1.7, 1.1, 1.0]
EO_COL_LABELS = ["Student", "Cohort", "Coursework", "Comp. Exam", "Capstone", "Time in Stage", "Flag"]


@st.cache_data(ttl=300, show_spinner=False)
def get_stage_flags() -> pd.DataFrame:
    """Time in stage + At-Risk flag for every student, from the v_student_stage_flags view.

    The view compares each student's days in their current stage with the program's
    At-Risk threshold (set in Admin Configuration). Completed and Cancelled students are
    never flagged. Saving a new threshold clears this cache, so the table updates right away.
    """
    flags = get_flagged_students()
    if flags is None or flags.empty:
        return pd.DataFrame(columns=["StudentNumber", "DaysInStage", "ExpectedDays", "IsFlagged", "FlagReason"])
    flags = flags.rename(columns={"days_in_stage": "DaysInStage", "expected_days": "ExpectedDays",
                                  "is_flagged": "IsFlagged", "flag_reason": "FlagReason"})
    flags["StudentNumber"] = flags["StudentNumber"].astype(str)
    return flags[["StudentNumber", "DaysInStage", "ExpectedDays", "IsFlagged", "FlagReason"]]


def add_stage_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Adds DaysInStage / ExpectedDays / IsFlagged / FlagReason to the student rows."""
    out = df.copy()
    out["_sn"] = out["StudentNumber"].astype(str)
    try:
        flags = get_stage_flags().rename(columns={"StudentNumber": "_sn"})
    except Exception as e:
        st.warning(f"Couldn't load at-risk flags: {e}")
        flags = pd.DataFrame(columns=["_sn", "DaysInStage", "ExpectedDays", "IsFlagged", "FlagReason"])
    out = out.merge(flags, on="_sn", how="left").drop(columns="_sn")
    out["IsFlagged"] = pd.to_numeric(out["IsFlagged"], errors="coerce").fillna(0).astype(int).astype(bool)
    return out


def time_in_stage(row):
    """Days the student has been in their current stage (None -> shows "—")."""
    days = row.get("DaysInStage")
    return int(days) if days is not None and pd.notna(days) else None


def risk_flag(row, days):
    """True when the student is past the program's At-Risk threshold and not finished."""
    return bool(row.get("IsFlagged"))


def open_student_profile(student_id, program_id, program_code):
    """Go to Student Profile for this student (also sets the program Student Profile needs)."""
    st.session_state["roster_program_id"] = program_id
    st.session_state["roster_program_code"] = program_code or ""
    st.session_state["active_program_id"] = program_id
    st.session_state["active_program_code"] = program_code or ""
    st.session_state["selected_student_override"] = str(student_id)
    st.switch_page(STUDENT_PROFILE_PAGE)


def render_student_table(df: pd.DataFrame, drill_stage=None):
    """Student table.

    Default: "Students At Risk" = only students past their program's At-Risk threshold,
    longest time in stage first.
    drill_stage (US-21): ALL students in that lifecycle stage (at-risk ones first).
    """
    if drill_stage:
        title = f"Students in {html.escape(stage_name(drill_stage))}"
        subtitle = "Every student currently in this stage. At-risk students are listed first."
    else:
        title = "Students At Risk — Requires Follow-Up"
        subtitle = ("Auto-flagged when a student stays in a stage longer than the "
                    "program's At-Risk threshold (US-26 / US-27)")
    st.markdown(
        '<div class="eo-card-head" style="margin-top:18px;">'
        f'<div class="eo-card-title">{title}</div>'
        f'<div class="eo-card-sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )

    if not drill_stage:
        df = df[df["IsFlagged"]] if "IsFlagged" in df.columns else df.iloc[0:0]
        if df.empty:
            st.success("No students are at risk for these filters.")
            return
    elif df.empty:
        st.info(f"No students are currently in the '{stage_name(drill_stage)}' stage with these filters.")
        return

    sort_cols, ascending = ["DaysInStage", "LastName"], [False, True]
    if drill_stage and "IsFlagged" in df.columns:
        sort_cols, ascending = ["IsFlagged"] + sort_cols, [False] + ascending
    df = df.sort_values(sort_cols, ascending=ascending, na_position="last")

    # speed: draw the first EO_MAX_ROWS rows; "Show all" draws the rest
    total_rows = len(df)
    show_all_key = f"eo_show_all_{drill_stage or 'risk'}"
    truncated = total_rows > EO_MAX_ROWS and not st.session_state.get(show_all_key)
    if truncated:
        df = df.head(EO_MAX_ROWS)

    with st.container(key="eo_table"):
        # header row (stays put while the rows scroll)
        with st.container(key="eo_table_head"):
            for col, label in zip(st.columns(EO_COL_WIDTHS, vertical_alignment="center"), eo_col_labels()):
                col.markdown(f'<div class="eo-th">{label}</div>', unsafe_allow_html=True)

        height = EO_ROW_HEIGHT_PX * EO_ROWS_VISIBLE if len(df) > EO_ROWS_VISIBLE else None
        scroll_kwargs = {"height": height} if height else {}   # never pass height=None (older Streamlit rejects it)
        with st.container(border=False, key="eo_table_rows", **scroll_kwargs):
            for r in df.to_dict("records"):
                sid = str(r["StudentNumber"])
                first = str(r["FirstName"] or "").strip()
                last = str(r["LastName"] or "").strip()
                name = f"{first} {last}".strip() or "Unnamed student"
                cohort = r["Cohort"] if pd.notna(r["Cohort"]) else "—"
                days = time_in_stage(r)
                flag = risk_flag(r, days)

                c = st.columns(EO_COL_WIDTHS, vertical_alignment="center")
                with c[0]:
                    # no help= tooltip here: its wrapper added extra space under the name
                    if st.button(name, key=f"eo_open_{sid}", type="tertiary"):
                        open_student_profile(sid, r["ProgramID"], r.get("ProgramCode"))
                    st.markdown(f'<div class="eo-id">{html.escape(sid)}</div>', unsafe_allow_html=True)
                c[1].markdown(f'<div class="eo-cell">{html.escape(str(cohort))}</div>', unsafe_allow_html=True)
                c[2].markdown(status_pill(r["CourseworkStatus"]), unsafe_allow_html=True)
                c[3].markdown(status_pill(r["CompExamStatus"]), unsafe_allow_html=True)
                c[4].markdown(status_pill(r["CapstoneStatus"]), unsafe_allow_html=True)
                c[5].markdown(
                    f'<div class="eo-cell">{days:,} days</div>' if days is not None
                    else '<span class="eo-muted">—</span>',
                    unsafe_allow_html=True,
                )
                c[6].markdown(
                    f'<span class="eo-pill pill-red" title="{html.escape(str(r.get("FlagReason") or ""))}">AT RISK</span>'
                    if flag
                    else '<span class="eo-muted">—</span>',
                    unsafe_allow_html=True,
                )

    if truncated:
        c_note, c_btn = st.columns([4, 1], vertical_alignment="center")
        c_note.caption(f"Showing the first {EO_MAX_ROWS} of {total_rows} students.")
        if c_btn.button(f"Show all {total_rows}", key=f"{show_all_key}_btn", use_container_width=True):
            st.session_state[show_all_key] = True
            st.rerun()


# ---------------------------------------------------------------------------
# EXPORT (filtered student list -> CSV, logged for audit)
# ---------------------------------------------------------------------------
EXPORT_COLUMNS = {                      # DataFrame column -> header in the exported file
    "StudentNumber": "Student Number",
    "FirstName": "First Name",
    "LastName": "Last Name",
    "ProgramCode": "Program",
    "Cohort": "Cohort",
    "EnrollmentStatus": "Enrollment Status",
    "Adviser": "Adviser(s)",
    "ActiveStage": "Current Stage",
    "CourseworkStatus": "Coursework Status",
    "CompExamStatus": "Comp Exam Status",
    "CapstoneStatus": "Capstone Status",
    "DaysInStage": "Time in Stage (days)",
    "ExpectedDays": "At-Risk Threshold (days)",
    "FlagReason": "Flag Reason",
    "GraduateOnTime": "Graduate On Time",
    "LastUpdated": "Last Updated",
}


def at_risk_students(df: pd.DataFrame) -> pd.DataFrame:
    """Same rows as the "Students At Risk" table on the page (active filters already applied)."""
    if "IsFlagged" not in df.columns:
        return df.iloc[0:0]
    return df[df["IsFlagged"]]


def export_table(df: pd.DataFrame) -> pd.DataFrame:
    """The at-risk table as it goes into the export: readable headers, longest time in stage first,
    dates as text."""
    out = df[[c for c in EXPORT_COLUMNS if c in df.columns]].copy()
    if "ActiveStage" in out:
        out["ActiveStage"] = out["ActiveStage"].map(stage_name)   # US-30 labels
    if "LastUpdated" in out:
        out["LastUpdated"] = out["LastUpdated"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
    for c in ("DaysInStage", "ExpectedDays"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")
    sort_cols = [c for c in ("DaysInStage", "LastName", "FirstName") if c in out]
    out = out.sort_values(sort_cols, ascending=[c != "DaysInStage" for c in sort_cols], na_position="last")
    out = out.astype(object).where(out.notna(), "")
    headers = dict(EXPORT_COLUMNS)   # US-30: status columns use the program's stage labels
    headers["CourseworkStatus"] = f"{stage_name('Coursework')} Status"
    headers["CompExamStatus"] = f"{stage_name('Comprehensive Exam')} Status"
    headers["CapstoneStatus"] = f"{stage_name('Capstone')} Status"
    return out.rename(columns=headers)


def compare_text(hist, metric, cohort, kind="pct", higher_is_better=True) -> str:
    """Plain-text version of the KPI comparison line (for Excel)."""
    reason, info = cohort_compare(hist, metric, cohort)
    if reason == "all":
        return "Select a cohort to compare"
    if reason == "first":
        return "No previous term"
    delta, prev_c, prev_v = info["delta"], info["prev_cohort"], info["prev_value"]
    if kind == "pct":
        amount, prev_txt = f"{abs(delta):.1f} pts", f"{prev_v:.1f}%"
    else:
        amount = f"{abs(int(delta)):,} student{'s' if abs(int(delta)) != 1 else ''}"
        prev_txt = f"{int(prev_v):,}"
    if delta == 0:
        return f"No change vs {prev_c} ({prev_txt})"
    better = (delta > 0) == higher_is_better
    return f"{'▲' if delta > 0 else '▼'} {amount} vs {prev_c} ({prev_txt}) — {'better' if better else 'worse'}"


def _tidy_chart(chart, GraphicalProperties, LineProperties):
    """Title above the plot (not on top of it) and light grey axis lines."""
    chart.title.overlay = False
    for ax in (chart.x_axis, chart.y_axis):
        ax.spPr = GraphicalProperties(ln=LineProperties(solidFill="D1D5DB"))


def _value_labels(DataLabelList):
    """Chart labels that show only the number (not the series/category name)."""
    lbl = DataLabelList()
    lbl.showVal = True
    lbl.showSerName = lbl.showCatName = lbl.showLegendKey = lbl.showPercent = False
    return lbl


def build_export_xlsx(df, hist, filters: dict, exported_by: str, exported_at: str) -> bytes:
    """Excel export with two tabs: 'Overview' (filters, KPIs, both charts) and
    'At-Risk Students' (the same students as the "Students At Risk" table on the page)."""
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.series import DataPoint
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.drawing.line import LineProperties
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    navy, grey = "0F172A", "6B7280"
    head_fill = PatternFill("solid", fgColor="1F2937")
    band_fill = PatternFill("solid", fgColor="F3F4F6")
    thin = Border(bottom=Side(style="thin", color="E5E7EB"))
    section = Font(bold=True, size=11, color=navy)

    wb = Workbook()
    ov = wb.active
    ov.title = "Overview"
    ov.sheet_view.showGridLines = False

    ov["A1"] = "Executive Overview"
    ov["A1"].font = Font(bold=True, size=18, color=navy)
    ov["A2"] = f"Exported {exported_at} by {exported_by}"
    ov["A2"].font = Font(italic=True, size=9, color=grey)

    # --- Filters ---
    ov["A4"] = "FILTERS"; ov["A4"].font = section
    for i, (k, v) in enumerate(filters.items(), start=5):
        ov.cell(i, 1, k).font = Font(color=grey)
        ov.cell(i, 2, v).font = Font(bold=True)

    # --- Lifecycle stage data (the key metrics below are worked out from this table) ---
    counts = lifecycle_counts(df)
    ov["A16"] = "COHORT BY LIFECYCLE STAGE"; ov["A16"].font = section
    ov["A17"], ov["B17"] = "Stage", "Students"
    for c in ("A17", "B17"):
        ov[c].font = Font(bold=True, color="FFFFFF"); ov[c].fill = head_fill
    for i, (stage, n) in enumerate(zip(counts["Stage"], counts["Count"]), start=18):
        ov.cell(i, 1, stage_name(stage)); ov.cell(i, 2, int(n))
        for c in (1, 2):
            ov.cell(i, c).border = thin
    # rows 18-22 = Coursework, Comprehensive Exam, Capstone, Completed, Inactive
    yes = int(df["GraduateOnTime"].astype(str).str.strip().str.lower().isin(ON_TIME_TRUE).sum())
    ov["A23"] = 'Graduate On Time = "yes"'; ov["B23"] = yes
    ov["A23"].font = ov["B23"].font = Font(italic=True, color=grey)

    # --- KPIs ---
    cohort = filters.get("Cohort", "All Cohorts")
    ov["A10"] = "KEY METRICS"; ov["A10"].font = section
    # Real numbers, not Excel formulas: formulas show up EMPTY when the file opens in Protected View
    # (files downloaded from the web), in Excel preview panes, and on phones, until editing is enabled.
    total_n = int(counts["Count"].sum())
    completed_n = int(counts.loc[counts["Stage"] == "Completed", "Count"].sum())
    inactive_n = int(counts.loc[counts["Stage"] == INACTIVE_STAGE, "Count"].sum())
    kpis = [
        ("Total Enrolled", total_n, "#,##0", ""),
        ("On-Time Graduation Rate", (yes / total_n) if total_n else 0, "0.0%",
         compare_text(hist, "OnTime", cohort)),
        ("Overall Completion", (completed_n / total_n) if total_n else 0, "0.0%",
         compare_text(hist, "Completion", cohort)),
        ("Remaining Students", total_n - completed_n - inactive_n, "#,##0",
         compare_text(hist, "Remaining", cohort, kind="count", higher_is_better=False)),
    ]
    for i, (label, value, fmt, cmp_txt) in enumerate(kpis, start=11):
        ov.cell(i, 1, label).font = Font(color=grey)
        cell = ov.cell(i, 2, value)
        cell.number_format, cell.font = fmt, Font(bold=True, size=12, color=navy)
        cmp_cell = ov.cell(i, 3, cmp_txt)
        color = "2E9E3E" if "better" in cmp_txt else "C62828" if "worse" in cmp_txt else "9CA3AF"
        cmp_cell.font = Font(size=9, color=color, italic=color == "9CA3AF")
    ov["C10"] = f"Students at Risk: {int(at_risk_students(df).shape[0]):,}"
    ov["C10"].font = Font(bold=True, color="C62828")
    ov["A15"] = "Remaining Students = Total Enrolled − Completed − Inactive, split by current lifecycle stage."
    ov["A15"].font = Font(size=9, italic=True, color=grey)

    # --- Completion trend data ---
    recent = hist.tail(4).reset_index(drop=True)
    ov["A25"] = "OVERALL COMPLETION % — TREND (last 4 cohorts, program-wide)"; ov["A25"].font = section
    ov["A26"], ov["B26"] = "Cohort", "Completion %"
    for c in ("A26", "B26"):
        ov[c].font = Font(bold=True, color="FFFFFF"); ov[c].fill = head_fill
    for i, r in recent.iterrows():
        ov.cell(27 + i, 1, r["Cohort"])
        v = ov.cell(27 + i, 2, round(float(r["Completion"]) / 100, 4))
        v.number_format = "0.0%"
        for c in (1, 2):
            ov.cell(27 + i, c).border = thin

    ov.column_dimensions["A"].width = 30
    ov.column_dimensions["B"].width = 16
    ov.column_dimensions["C"].width = 40

    # --- Charts ---
    bar = BarChart()
    bar.title, bar.legend, bar.varyColors = "Cohort by Lifecycle Stage", None, False
    bar.y_axis.majorGridlines = None
    bar.add_data(Reference(ov, min_col=2, min_row=17, max_row=22), titles_from_data=True)
    bar.set_categories(Reference(ov, min_col=1, min_row=18, max_row=22))
    series = bar.series[0]
    for idx, stage in enumerate(STAGE_ORDER):
        pt = DataPoint(idx=idx)
        pt.graphicalProperties.solidFill = STAGE_COLORS[stage].lstrip("#")
        pt.graphicalProperties.line.noFill = True
        series.dPt.append(pt)
    series.dLbls = _value_labels(DataLabelList)
    bar.x_axis.delete = bar.y_axis.delete = False      # openpyxl 3.1 hides axes otherwise
    _tidy_chart(bar, GraphicalProperties, LineProperties)
    bar.width, bar.height = 17, 8.5
    ov.add_chart(bar, "E3")

    if len(recent) >= 2:
        line = LineChart()
        line.title, line.legend, line.varyColors = "Overall Completion % — Trend", None, False
        line.y_axis.number_format = "0%"
        line.add_data(Reference(ov, min_col=2, min_row=26, max_row=26 + len(recent)), titles_from_data=True)
        line.set_categories(Reference(ov, min_col=1, min_row=27, max_row=26 + len(recent)))
        s0 = line.series[0]
        s0.graphicalProperties.line.solidFill, s0.graphicalProperties.line.width = "111827", 19050
        s0.marker.symbol, s0.marker.size = "circle", 6
        s0.marker.graphicalProperties = GraphicalProperties(solidFill="111827")   # same colour every point
        s0.marker.graphicalProperties.line.solidFill = "111827"
        s0.smooth = False
        s0.dLbls = _value_labels(DataLabelList); s0.dLbls.position = "t"
        line.x_axis.delete = line.y_axis.delete = False
        line.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E5E7EB"))
        _tidy_chart(line, GraphicalProperties, LineProperties)
        line.width, line.height = 17, 8.5
        ov.add_chart(line, "E21")

    # --- Students At Risk trend (same numbers as the "Students at Risk" view of the trend chart) ---
    ov["A33"] = "STUDENTS AT RISK — TREND (last 4 cohorts, program-wide)"; ov["A33"].font = section
    ov["A34"], ov["B34"], ov["C34"] = "Cohort", "Students at Risk", "% of Cohort"
    for c in ("A34", "B34", "C34"):
        ov[c].font = Font(bold=True, color="FFFFFF"); ov[c].fill = head_fill
    for i, r in recent.iterrows():
        ov.cell(35 + i, 1, r["Cohort"])
        ov.cell(35 + i, 2, int(r.get("AtRisk", 0) or 0))
        pct = ov.cell(35 + i, 3, round(float(r.get("AtRiskPct", 0) or 0) / 100, 4))
        pct.number_format = "0.0%"
        for c in (1, 2, 3):
            ov.cell(35 + i, c).border = thin

    if len(recent) >= 2:
        risk = LineChart()
        risk.title, risk.legend, risk.varyColors = "Students At Risk — Trend", None, False
        risk.y_axis.number_format = "0"
        risk.add_data(Reference(ov, min_col=2, min_row=34, max_row=34 + len(recent)), titles_from_data=True)
        risk.set_categories(Reference(ov, min_col=1, min_row=35, max_row=34 + len(recent)))
        r0 = risk.series[0]
        r0.graphicalProperties.line.solidFill, r0.graphicalProperties.line.width = "C62828", 19050
        r0.marker.symbol, r0.marker.size = "circle", 6
        r0.marker.graphicalProperties = GraphicalProperties(solidFill="C62828")
        r0.marker.graphicalProperties.line.solidFill = "C62828"
        r0.smooth = False
        r0.dLbls = _value_labels(DataLabelList); r0.dLbls.position = "t"
        risk.x_axis.delete = risk.y_axis.delete = False
        risk.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E5E7EB"))
        _tidy_chart(risk, GraphicalProperties, LineProperties)
        risk.width, risk.height = 17, 8.5
        ov.add_chart(risk, "E39")

    # --- At-Risk Students tab (same rows as the on-page table, with the active filters) ---
    st_ws = wb.create_sheet("At-Risk Students")
    table = export_table(at_risk_students(df))
    st_ws.append(list(table.columns))
    for row in table.itertuples(index=False):
        st_ws.append([None if pd.isna(v) else v for v in row])
    if table.empty:
        st_ws.append(["No students are at risk for these filters."])
    for c in st_ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), head_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r in range(2, st_ws.max_row + 1):
        if r % 2 == 1:
            for c in st_ws[r]:
                c.fill = band_fill
    for i, col in enumerate(table.columns, start=1):
        longest = max([len(str(col))] + [len(str(v)) for v in table[col].head(300)])
        st_ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 10), 40)
    st_ws.freeze_panes = "A2"
    if st_ws.max_row > 1:
        st_ws.auto_filter.ref = st_ws.dimensions

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@st.cache_data(ttl=300, show_spinner=False, max_entries=20)
def cached_export_xlsx(df, hist, filters_json, exported_by, labels_key, exported_at):
    """The Excel file is rebuilt only when the filters / data / stage labels change (or the minute
    changes, because the export time is printed in the file), not on every click on the page."""
    return build_export_xlsx(df, hist, json.loads(filters_json), exported_by, exported_at)


# ---------------------------------------------------------------------------
# PDF EXPORT (same content as the Excel export, as a printable report)
#   Page 1: filters, the KPI cards exactly as shown on screen, Cohort by Lifecycle Stage chart,
#           Completion % and Students at Risk trend charts.
#   Page 2+: the At-Risk Students table (same rows as the on-page table).
#   Charts are drawn by reportlab itself (no browser / kaleido needed on the server).
# ---------------------------------------------------------------------------
def _pdf_text(s) -> str:
    """Plain text for the PDF: the built-in PDF fonts have no ▲ ▼ ● glyphs (they'd print as black boxes)."""
    s = str(s if s is not None else "")
    for a, b in (("▲ ", "+"), ("▼ ", "-"), ("▲", "+"), ("▼", "-"), ("● ", ""), ("●", ""), ("&#9679; ", "")):
        s = s.replace(a, b)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def kpi_pdf_items(cards_data):
    """(label, value, sub_html, accent) from the on-screen KPI tiles -> plain items for the PDF."""
    items = []
    for label, value, sub_html, accent in cards_data:
        tone = "up" if 'class="eo-up"' in (sub_html or "") else \
               "down" if ('class="eo-down"' in (sub_html or "") or 'class="eo-risk"' in (sub_html or "")) else "flat"
        items.append((_pdf_text(label), _pdf_text(value), _pdf_text(sub_html), tone,
                      accent if accent and _HEX_COLOR.match(str(accent)) else "#D1D5DB"))
    return tuple(items)


def build_export_pdf(df, hist, filters: dict, exported_by: str, kpi_items, exported_at: str) -> bytes:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    C = colors.HexColor
    navy, grey, border = C("#0F172A"), C("#6B7280"), C("#E5E7EB")
    tone_color = {"up": C("#2E9E3E"), "down": C("#C62828"), "flat": C("#9CA3AF")}
    page_w, page_h = landscape(letter)
    margin = 0.5 * inch
    usable_w = page_w - 2 * margin

    def style(name, **kw):
        base = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=navy, alignment=TA_LEFT)
        base.update(kw)
        return ParagraphStyle(name, **base)

    s_title = style("t", fontName="Helvetica-Bold", fontSize=20, leading=24)
    s_meta = style("m", fontSize=8, textColor=grey)
    s_section = style("s", fontName="Helvetica-Bold", fontSize=11, leading=14)
    s_kpi_label = style("kl", fontSize=7, leading=9, textColor=C("#4B5563"))
    s_kpi_value = style("kv", fontName="Helvetica-Bold", fontSize=18, leading=22)
    s_cell = style("c", fontSize=7.5, leading=9)
    s_head = style("h", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(grey)
        canvas.drawString(margin, 0.3 * inch, "ETYSB Dashboard · Executive Overview")
        canvas.drawRightString(page_w - margin, 0.3 * inch, f"Page {doc.page}")
        canvas.restoreState()

    story = [
        Paragraph("Executive Overview", s_title),
        Paragraph(f"Exported {html.escape(exported_at)} by {html.escape(str(exported_by))}", s_meta),
        Spacer(1, 6),
        Paragraph("  ·  ".join(f'<font color="#6B7280">{html.escape(k)}:</font> <b>{html.escape(str(v))}</b>'
                               for k, v in filters.items()), style("f", fontSize=9)),
        Spacer(1, 10),
    ]

    # ---- KPI cards (same tiles, labels, order and accent colours as on screen) ----
    if kpi_items:
        cells, accents = [], []
        for label, value, sub, tone, accent in kpi_items:
            cells.append([Paragraph(html.escape(label.upper()), s_kpi_label),
                          Paragraph(html.escape(value), s_kpi_value),
                          Paragraph(html.escape(sub) or "&nbsp;",
                                    style("ks", fontSize=7, leading=9, textColor=tone_color[tone]))])
            accents.append(C(accent))
        n = len(cells)
        gap = 8
        col_w = (usable_w - gap * (n - 1)) / n
        row, widths = [], []
        for i, cell in enumerate(cells):
            inner = Table([[c] for c in cell], colWidths=[col_w - 16])
            inner.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                       ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
            row.append(inner); widths.append(col_w)
            if i < n - 1:
                row.append(""); widths.append(gap)
        kpi_table = Table([row], colWidths=widths)
        ts = [("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]
        for i in range(n):
            col = i * 2
            ts += [("BOX", (col, 0), (col, 0), 0.6, border),
                   ("LINEABOVE", (col, 0), (col, 0), 3, accents[i])]
        kpi_table.setStyle(TableStyle(ts))
        story += [kpi_table, Spacer(1, 14)]

    # ---- Charts: one per row, full width, styled like the Excel export's charts ----
    #   rounded frame, centred title, value axis with numbers, light gridlines on the trends,
    #   value labels above each bar / point.
    from reportlab.graphics.shapes import Rect
    from reportlab.graphics.widgets.markers import makeMarker

    counts = lifecycle_counts(df)
    recent = hist.tail(4).reset_index(drop=True)
    chart_w = usable_w

    def nice_axis(lo, hi, ticks=6):
        """Round axis limits + step (e.g. 0 / 140 / 20), like Excel picks them."""
        span = max(hi - lo, 1e-9)
        raw = span / ticks
        mag = 10 ** int(np.floor(np.log10(raw)))
        step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
        return np.floor(lo / step) * step, np.ceil(hi / step) * step, step

    def frame(height, title):
        """Drawing with a rounded border and a centred title (the 'chart card')."""
        d = Drawing(chart_w, height)
        d.add(Rect(0.5, 0.5, chart_w - 1, height - 1, rx=8, ry=8,
                   strokeColor=C("#9CA3AF"), strokeWidth=0.8, fillColor=None))
        d.add(String(chart_w / 2, height - 18, title, fontName="Helvetica-Bold", fontSize=10,
                     fillColor=navy, textAnchor="middle"))
        return d

    def style_axes(chart, value_fmt, grid):
        va, ca = chart.valueAxis, chart.categoryAxis
        va.labels.fontName, va.labels.fontSize, va.labels.fillColor = "Helvetica", 8, C("#4B5563")
        va.labelTextFormat = value_fmt
        va.strokeColor = C("#D1D5DB") if not grid else None
        va.visibleGrid = grid
        va.gridStrokeColor, va.gridStrokeWidth = C("#E5E7EB"), 0.6
        va.visibleTicks = False
        ca.labels.fontName, ca.labels.fontSize, ca.labels.fillColor = "Helvetica", 8, C("#111827")
        ca.labels.dy = -4
        ca.strokeColor = C("#D1D5DB")
        ca.visibleTicks = False

    def bar_chart():
        height = 3.4 * inch
        d = frame(height, "Cohort by Lifecycle Stage")
        values = [int(v) for v in counts["Count"]]
        lo, hi, step = nice_axis(0, max(max(values), 1) * 1.08)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 50, 42, chart_w - 80, height - 80
        bc.data = [values]
        bc.valueAxis.valueMin, bc.valueAxis.valueMax, bc.valueAxis.valueStep = 0, hi, step
        style_axes(bc, "%d", grid=False)
        bc.categoryAxis.categoryNames = [stage_name(s) for s in counts["Stage"]]
        bc.barWidth, bc.groupSpacing = 10, 14   # relative units: bar ≈ 40% of each slot, like Excel
        bc.bars.strokeColor = None
        for i, stage in enumerate(counts["Stage"]):
            bc.bars[(0, i)].fillColor = C(STAGE_COLORS[stage])
        bc.barLabelFormat = "%d"
        bc.barLabels.nudge = 8
        bc.barLabels.fontName, bc.barLabels.fontSize, bc.barLabels.fillColor = "Helvetica", 8, C("#111827")
        d.add(bc)
        return d

    def line_chart(title, values, labels, color, axis_fmt, label_fmt, start_at_zero):
        height = 3.25 * inch
        d = frame(height, title)
        if len(values) < 2:
            d.add(String(chart_w / 2, height / 2, "At least two cohorts are needed to show a trend.",
                         fontName="Helvetica", fontSize=9, fillColor=grey, textAnchor="middle"))
            return d
        lo_v, hi_v = min(values), max(values)
        lo, hi, step = nice_axis(0 if start_at_zero else max(lo_v - (hi_v - lo_v) * 0.6 - 1, 0),
                                 hi_v + max((hi_v - lo_v) * 0.15, 1))
        lc = HorizontalLineChart()
        lc.x, lc.y, lc.width, lc.height = 50, 42, chart_w - 80, height - 80
        lc.data = [values]
        lc.valueAxis.valueMin, lc.valueAxis.valueMax, lc.valueAxis.valueStep = lo, hi, step
        style_axes(lc, axis_fmt, grid=True)
        lc.categoryAxis.categoryNames = [str(x) for x in labels]
        lc.joinedLines = 1
        lc.lines[0].strokeColor, lc.lines[0].strokeWidth = C(color), 1.6
        lc.lines[0].symbol = makeMarker("FilledCircle", size=5, fillColor=C(color), strokeColor=C(color))
        lc.lineLabelFormat = label_fmt
        lc.lineLabels.fontName, lc.lineLabels.fontSize = "Helvetica", 8
        lc.lineLabels.fillColor, lc.lineLabels.dy = C("#111827"), 10
        d.add(lc)
        return d

    # page 1: KPI cards + the stage bar chart; page 2: the two trend charts
    story += [bar_chart(), PageBreak(),
              line_chart("Overall Completion % — Trend", [float(v) for v in recent["Completion"]],
                         recent["Cohort"], "#111827", "%d%%", "%.1f%%", start_at_zero=True),
              Spacer(1, 14),
              line_chart("Students At Risk — Trend", [int(v) for v in recent.get("AtRisk", [])],
                         recent["Cohort"], "#C62828", "%d", "%d", start_at_zero=False)]

    # ---- At-Risk Students table ----
    story += [PageBreak(), Paragraph("Students At Risk — Requires Follow-Up", s_section),
              Paragraph("Students who have stayed in their current stage longer than the program's "
                        "At-Risk threshold (with the filters above).", s_meta), Spacer(1, 8)]
    risk = at_risk_students(df)
    if risk.empty:
        story.append(Paragraph("No students are at risk for these filters.", style("e", textColor=grey)))
    else:
        risk = risk.sort_values(["DaysInStage", "LastName"], ascending=[False, True], na_position="last")
        headers = ["Student No.", "Name", "Program", "Cohort", "Current Stage",
                   stage_name("Coursework"), stage_name("Comprehensive Exam"), stage_name("Capstone"),
                   "Days in Stage", "Threshold"]
        data = [[Paragraph(html.escape(h), s_head) for h in headers]]
        for r in risk.to_dict("records"):
            def v(x):
                return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
            days = r.get("DaysInStage")
            exp = r.get("ExpectedDays")
            data.append([Paragraph(html.escape(v(c)), s_cell) for c in (
                r.get("StudentNumber"), f'{v(r.get("FirstName"))} {v(r.get("LastName"))}'.strip(),
                r.get("ProgramCode"), r.get("Cohort"), stage_name(r.get("ActiveStage")),
                r.get("CourseworkStatus"), r.get("CompExamStatus"), r.get("CapstoneStatus"),
                f"{int(days):,}" if days is not None and pd.notna(days) else "",
                f"{int(exp):,}" if exp is not None and pd.notna(exp) else "",
            )])
        widths = [0.9, 1.6, 0.7, 0.7, 1.2, 1.1, 1.1, 1.2, 0.8, 0.7]
        scale = usable_w / sum(widths)
        table = Table(data, colWidths=[w * scale for w in widths], repeatRows=1)
        ts = [("BACKGROUND", (0, 0), (-1, 0), C("#1F2937")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LINEBELOW", (0, 1), (-1, -1), 0.4, border),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for i in range(2, len(data), 2):
            ts.append(("BACKGROUND", (0, i), (-1, i), C("#F3F4F6")))
        table.setStyle(TableStyle(ts))
        story.append(table)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=0.6 * inch,
                            title="Executive Overview", author=str(exported_by))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# Bump this whenever build_export_pdf() changes: it's part of the cache key, so an already-built
# PDF from the old layout is never handed out again (Streamlit doesn't notice changes inside
# build_export_pdf on its own and would keep serving the cached old file for up to 5 minutes).
PDF_EXPORT_VERSION = 3


@st.cache_data(ttl=300, show_spinner=False, max_entries=20)
def cached_export_pdf(df, hist, filters_json, exported_by, labels_key, kpi_items, exported_at,
                      version=PDF_EXPORT_VERSION):
    """PDF is rebuilt only when the filters / data / labels / KPI tiles / export minute / PDF layout version change."""
    return build_export_pdf(df, hist, json.loads(filters_json), exported_by, kpi_items, exported_at)


def export_file_name(program_label, cohort, status, ext="xlsx") -> str:
    parts = ["at_risk_students", program_label, cohort, status, now_local().strftime("%Y-%m-%d")]
    return "_".join(re.sub(r"[^A-Za-z0-9]+", "-", str(p)).strip("-") for p in parts) + f".{ext}"


def _current_user_label() -> str:
    user = st.session_state.get("user")
    if isinstance(user, dict):
        for key in ("Username", "username", "Email", "email", "UserID", "user_id", "Name", "name"):
            if user.get(key):
                return str(user[key])
    return str(user) if user else "unknown"


@st.cache_resource
def _ensure_export_log_table():
    """Creates the audit table the first time it's needed (runs once per app process)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Export_Log (
                ExportID   INT AUTO_INCREMENT PRIMARY KEY,
                ExportedBy VARCHAR(255) NOT NULL,
                ExportedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                Page       VARCHAR(100) NOT NULL,
                Filters    VARCHAR(500),
                RowCount   INT,
                FileName   VARCHAR(255)
            )
            """
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return True


def log_export(filters: dict, row_count: int, file_name: str):
    """on_click callback for the export button: writes one audit row per export."""
    try:
        _ensure_export_log_table()
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO Export_Log (ExportedBy, Page, Filters, RowCount, FileName) "
                "VALUES (%s, %s, %s, %s, %s)",
                (_current_user_label(), "Executive Overview (PDF)" if file_name.endswith(".pdf")
                 else "Executive Overview (Excel)", json.dumps(filters), row_count, file_name),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
    except Exception as e:  # never block the download because logging failed
        st.toast(f"Export downloaded, but it couldn't be logged: {e}")

# ---------------------------------------------------------------------------
# US-29: KPI tile metric resolvers
# ---------------------------------------------------------------------------
def resolve_kpi_value(source, df, program_label, selected_cohort, hist):
    """Return the value and optional tooltip for a KPI tile source key."""
    src = (source or "").strip().lower()

    if src == "total_enrolled":
        return f"{len(df):,}", None
    if src == "remaining":
        return f"{int((~df['IsComplete'] & ~df['IsInactive']).sum()):,}", remaining_info_html(df)
    if src == "at_risk":
        return f"{int(df['IsFlagged'].sum()):,}", None
    if src == "on_time_rate":
        return f"{on_time_rate(df):.1f}%", None
    if src == "overall_completion":
        return f"{completion_rate(df):.1f}%", None
    if src == "completion_rate":
        return f"{completion_rate(df):.1f}%", None
    if src == "cohort_count":
        try:
            return f"{df['Cohort'].nunique():,}", None
        except Exception:
            return "0", None
    if src == "program_label":
        return program_label or "—", None
    if src == "student_count":
        return f"{len(df):,}", None

    return "—", None


def resolve_kpi_subtext(source, df, program_label, selected_cohort, hist):
    """The small line under a KPI value."""
    src = (source or "").strip().lower()

    if src == "total_enrolled":
        return f"{html.escape(program_label)} · {html.escape(selected_cohort)}"
    if src == "on_time_rate":
        return delta_html(hist, "OnTime", selected_cohort)
    if src == "overall_completion" or src == "completion_rate":
        return delta_html(hist, "Completion", selected_cohort)
    if src == "remaining":
        return delta_html(hist, "Remaining", selected_cohort, kind="count", higher_is_better=False)
    if src == "at_risk":
        return ('<span class="eo-risk">Past the at-risk threshold</span>' if df["IsFlagged"].any()
                else "Past the at-risk threshold")
    if src == "cohort_count":
        return "distinct cohorts in view"
    return "&nbsp;"
# ---------------------------------------------------------------------------
# PAGE ASSEMBLY
# ---------------------------------------------------------------------------
def render_executive_overview():
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    # plain div instead of st.title: no hover link icon, and the line sits right under the text
    st.markdown(
        '<div class="eo-header">'
        '<div class="eo-title">Executive Overview</div>'
        '<div class="eo-caption">High-level summary of active cohort health, completion metrics, '
        'and at-risk student statuses.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ---- Field mapping gate: no data is shown while a mapping is broken ----
    mapping_error = check_field_mappings()
    if mapping_error:
        st.error(
            "Executive Overview is unavailable because a field mapping is invalid. "
            "Ask an admin to fix it in Admin Configuration → Field Mapping."
        )
        st.caption(mapping_error)
        return

    # ---- Data ----
    try:
        all_df = get_executive_data()
    except mysql.connector.Error as err:
        st.error(format_mysql_error(err))
        return
    except Exception as e:
        st.error(f"Failed to fetch executive overview data: {e}")
        return

    # ---- Filters: Program | Cohort | Enrollment ----
    with st.container(key="eo_filters"):
        f1, f2, f3, f4, f5 = st.columns(5, gap="small", vertical_alignment="bottom")   # f4 = Excel, f5 = PDF

        with f3:
            selected_status = st.selectbox("Enrollment Status", ENROLLMENT_OPTIONS)

        # Program is chosen before Cohort in code (the cohort list depends on it)
        with f1:
            programs_by_id = {p["ProgramID"]: p for p in get_program_options()}
            selected_program_id = st.selectbox(
                "Program", list(programs_by_id),
                format_func=lambda pid: programs_by_id[pid]["ProgramName"],
            )
            selected_program = programs_by_id[selected_program_id]
            # US-30: this program's stage names ("All Programs" -> the default names)
            _stage_labels.clear()
            _stage_labels.update(cached_stage_labels(selected_program["ProgramID"]))

        program_df = all_df
        if selected_program["ProgramID"] is not None:
            program_df = all_df[all_df["ProgramID"] == selected_program["ProgramID"]]

        with f2:
            cohorts = sorted(program_df["Cohort"].dropna().unique(), key=cohort_sort_key, reverse=True)
            selected_cohort = st.selectbox("Cohort", ["All Cohorts"] + list(cohorts))

    # yellow header bar follows these filters
    set_header_context(program=selected_program["ProgramID"], cohort=selected_cohort)

    # Program + status filters apply everywhere; cohort applies to everything except the trend
    status_df = program_df
    if selected_status != "All":
        status_df = program_df[
            program_df["EnrollmentStatus"].astype(str).str.strip().str.lower() == selected_status.lower()
        ]
    df = status_df
    if selected_cohort != "All Cohorts":
        df = status_df[status_df["Cohort"] == selected_cohort]

    # Time in Stage + At-Risk flag (threshold from Admin Configuration); added before the cohort
    # filter so the at-risk trend can compare cohorts
    status_df = add_stage_flags(status_df)
    df = status_df
    if selected_cohort != "All Cohorts":
        df = status_df[status_df["Cohort"] == selected_cohort]

    hist = cohort_history(status_df)

    # ---- KPI tiles (US-29), worked out first because the PDF export includes them ----
    program_label = (
        "All Programs" if selected_program["ProgramID"] is None
        else (selected_program["ProgramCode"] or selected_program["ProgramName"])
    )
    tiles = cached_kpi_tiles(selected_program["ProgramID"])
    cards_data = []   # (label, value, sub_html, accent) for each tile, in order
    for t in tiles or []:
        src = (t.get("source") or "").strip().lower()
        label = html.escape(str(t.get("label", "")))
        if src == "total_enrolled" and selected_status != "All":   # keep the enrollment-filter wording
            label = f"Total {html.escape(selected_status)}"
        value, info = resolve_kpi_value(src, df, program_label, selected_cohort, hist)
        sub = resolve_kpi_subtext(src, df, program_label, selected_cohort, hist)
        cards_data.append((label, value, sub, t.get("color"), info))

    # ---- Export (far right of the filter row) ----
    program_label_for_file = (
        "All-Programs" if selected_program["ProgramID"] is None else selected_program["ProgramCode"]
    )
    file_name = export_file_name(program_label_for_file, selected_cohort, selected_status)
    # one export time (Philippine time, to the minute) shared by the Excel and the PDF
    exported_at = now_local().strftime("%b %d, %Y %H:%M")
    export_filters = {
        "Enrollment Status": selected_status,
        "Cohort": selected_cohort,
        "Program": selected_program["ProgramName"],
    }
    with f4:
        st.download_button(
            "⬇ Export Excel",
            data=cached_export_xlsx(df, hist, json.dumps(export_filters, sort_keys=True), _current_user_label(),
                                    tuple(sorted(_stage_labels.items())), exported_at) if not df.empty else b"",
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=df.empty,
            help="Excel file with the current filters: Overview tab (KPIs + charts) and "
                 "At-Risk Students tab (the Students At Risk table below)",
            on_click=log_export,
            args=(export_filters, int(at_risk_students(df).shape[0]), file_name),
        )
    pdf_name = export_file_name(program_label_for_file, selected_cohort, selected_status, ext="pdf")
    with f5:
        st.download_button(
            "⬇ Export PDF",
            data=cached_export_pdf(df, hist, json.dumps(export_filters, sort_keys=True), _current_user_label(),
                                   tuple(sorted(_stage_labels.items())),
                                   kpi_pdf_items([c[:4] for c in cards_data]),
                                   exported_at, PDF_EXPORT_VERSION) if not df.empty else b"",
            file_name=pdf_name,
            mime="application/pdf",
            disabled=df.empty,
            help="Printable PDF report with the current filters: KPI cards, the charts, "
                 "and the Students At Risk table",
            on_click=log_export,
            args=(export_filters, int(at_risk_students(df).shape[0]), pdf_name),
            key="eo_export_pdf",
        )

    # ---- KPI row (US-29: driven by Program.KpiTiles config) ----
    if not cards_data:
        st.info("No KPI tiles are configured for this program. Add them in Admin Config.")
    else:
        render_kpi_row([kpi_card(label, value, sub, info_html=info, accent=accent)
                        for label, value, sub, accent, info in cards_data])

    # ---- Charts ----
    charts_row = st.container(key="eo_charts")
    c1, c2 = charts_row.columns(2, gap="medium")
    chart_config = {"displayModeBar": False}

    with c1:
        with st.container(border=True):
            card_header("Cohort by Lifecycle Stage",
                        "Students per stage, including inactive (dropped out). "
                        "Click a bar to see the students in that stage.")
            stage_counts = lifecycle_counts(df)
            chart_event = st.plotly_chart(
                lifecycle_bar(stage_counts),
                use_container_width=True,
                config=chart_config,
                key=f"eo_lifecycle_chart_{st.session_state.get(DRILL_CHART_VERSION_KEY, 0)}",
                on_select="rerun",
                selection_mode="points",
            )
            # Read the click: the selected bar's stage comes back in customdata
            try:
                pts = chart_event.selection.points
            except Exception:
                pts = []
            if pts:
                clicked_stage = pts[0].get("customdata")
                if clicked_stage and st.session_state.get(DRILL_STAGE_KEY) != clicked_stage:
                    st.session_state[DRILL_STAGE_KEY] = clicked_stage
                    st.rerun()

    with c2:
        with st.container(border=True):
            recent = hist.tail(4)
            # title + subtitle on the left, Completion % / Students at Risk switch on the same line (right)
            options = ["Completion %", "Students at Risk"]
            if st.session_state.get("eo_trend_view") not in (None, *options):
                st.session_state.pop("eo_trend_view")   # old option name from an earlier version
            with st.container(key="eo_trend_head"):
                h_title, h_switch = st.columns([1.15, 1], vertical_alignment="top")
                with h_switch:
                    with st.container(key="eo_trend_switch"):
                        if hasattr(st, "segmented_control"):      # pill toggle (Streamlit 1.40+)
                            trend_view = st.segmented_control("Trend", options, default="Completion %",
                                                              label_visibility="collapsed", key="eo_trend_view")
                        else:                                    # older Streamlit: plain radio buttons
                            trend_view = st.radio("Trend", options, horizontal=True,
                                                  label_visibility="collapsed", key="eo_trend_view")
                trend_view = trend_view or "Completion %"      # clicking the selected pill again un-selects it
                with h_title:
                    if trend_view == "Students at Risk":
                        card_header("Students At Risk — Trend",
                                    f"Last {len(recent)} cohorts · past the At-Risk threshold")
                    else:
                        card_header("Overall Completion % — Trend", f"Last {len(recent)} cohorts, program-wide")
            if trend_view == "Students at Risk":
                if len(recent) >= 2:
                    with st.container(key="eo_trend_risk"):
                        st.plotly_chart(at_risk_trend(recent).update_layout(height=TREND_HEIGHT),
                                        use_container_width=True, config=chart_config)
                else:
                    st.info("At least two cohorts are needed to show a trend.")
            else:
                if len(recent) >= 2:
                    with st.container(key="eo_trend_completion"):
                        st.plotly_chart(completion_trend(recent).update_layout(height=TREND_HEIGHT),
                                        use_container_width=True, config=chart_config)
                else:
                    st.info("At least two cohorts are needed to show a trend.")

    # ---- Student table (US-21: a clicked bar shows every student in that stage) ----
    drill_stage = st.session_state.get(DRILL_STAGE_KEY)
    if drill_stage:
        drilled_df = df[df["ActiveStage"] == drill_stage]
        render_drill_breadcrumb(drill_stage, len(drilled_df))
        render_student_table(drilled_df, drill_stage=drill_stage)
    else:
        render_student_table(df)

if __name__ == "__main__":
    render_executive_overview()

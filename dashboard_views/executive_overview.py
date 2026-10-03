# EXEC OVERVIEW MERGE
# EXEC OVERVIEW 9-30-26 (QA fixes: Excel key metrics, Philippine export time, wider Program filter, tablet / phone table)
# 10-03-26: SPEED - the Completion % / Students at Risk switch only reruns its own card (st.fragment),
#           not the whole page. No extra database queries.
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
from perf import timed   # TEMP: timing ([TIMING] lines in the terminal)
from prefetch import start_prefetch, finish_prefetch

# SPEED: cached database reads are kept for 1 hour (was 1-5 minutes). On the free Aiven server every query
# takes ~1-2 s, so an expired cache = a slow page. Anything saved in the app (and "Refresh Now") still clears
# the cache right away; only changes made directly in MySQL (outside the app) take up to 1 hour to show.
CACHE_TTL = 3600

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
APP_TZ = timezone(timedelta(hours=8))


def now_local():
    return datetime.now(APP_TZ)


STAGE_PILLAR = {"Coursework": "Coursework", "Comprehensive Exam": "CompExam", "Capstone": "Capstone"}
_stage_labels = {}


def stage_name(stage):
    """Display name for a stage key (program-specific label, US-30)."""
    pillar = STAGE_PILLAR.get(stage)
    return _stage_labels.get(pillar, stage) if pillar else stage


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def cached_stage_labels(program_id):
    return get_stage_labels(program_id)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def cached_kpi_tiles(program_id):
    """KPI tile config (Admin Config clears this cache when tiles are saved)."""
    return get_kpi_tiles(program_id=program_id, visible_only=True)


def eo_col_labels():
    return ["Student", "Cohort", stage_name("Coursework"), stage_name("Comprehensive Exam"),
            stage_name("Capstone"), "Time in Stage", "Flag"]


DRILL_STAGE_KEY = "eo_drill_stage"
DRILL_CLEAR_LABEL = "← Back to all stages"
DRILL_CHART_VERSION_KEY = "eo_drill_chart_v"

# ---------------------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------------------
PAGE_CSS = """
<style>
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
.stApp .js-plotly-plot .xtick text,
.stApp .js-plotly-plot .bars .textpoint text{fill:var(--eo-chart-text) !important;}
.stApp .st-key-eo_trend_completion .js-plotly-plot .scatterlayer .textpoint text{fill:var(--eo-chart-line) !important;}
.stApp .st-key-eo_trend_completion .js-plotly-plot .scatterlayer .js-line{stroke:var(--eo-chart-line) !important;}
.stApp .st-key-eo_trend_completion .js-plotly-plot .scatterlayer .point{fill:var(--eo-chart-line) !important;}
.st-key-eo_charts [data-testid="stHorizontalBlock"]{align-items:stretch !important;}
.st-key-eo_charts > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{justify-content:flex-start !important;}
.st-key-eo_charts [data-testid="stVerticalBlockBorderWrapper"]{height:100%;}
.st-key-eo_charts div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has(.js-plotly-plot),
.st-key-eo_charts div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]){
    display:block !important;width:100% !important;min-height:0 !important;}
.st-key-eo_charts [data-testid="stPlotlyChart"]{width:100% !important;}
.st-key-eo_charts .js-plotly-plot{display:block !important;width:100% !important;}
.st-key-eo_charts .js-plotly-plot .plot-container{width:100% !important;display:flex !important;justify-content:center !important;}
.st-key-eo_charts .js-plotly-plot .svg-container{margin-left:auto !important;margin-right:auto !important;
    flex:0 0 auto;max-width:100%;}
.st-key-eo_trend_head [data-testid="stHorizontalBlock"]{
    align-items:flex-start !important;
    flex-wrap:wrap !important;
    gap:12px !important;
}
.st-key-eo_trend_head [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child{
    flex:1 1 260px !important;
    min-width:240px !important;
}
.st-key-eo_trend_head [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child{
    flex:0 0 auto !important;
    min-width:max-content !important;
}
.st-key-eo_trend_head .eo-card-title{
    white-space:normal !important;
    line-height:1.25 !important;
}
.st-key-eo_trend_head .eo-card-sub{
    margin:0 0 4px 4px !important;
}
.st-key-eo_trend_switch{display:flex;justify-content:flex-end;width:100%;margin-top:2px;}
.st-key-eo_trend_switch [data-testid="stElementContainer"]{justify-content:flex-end !important;width:100%;}
.st-key-eo_trend_switch [data-testid="stButtonGroup"],
.st-key-eo_trend_switch [role="radiogroup"]{justify-content:flex-end;flex-wrap:nowrap;margin-left:auto;}
.st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"],
.st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"] p{color:#B91B21 !important;}
.st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"]{border-color:#B91B21 !important;
        background:rgba(185,27,33,.06) !important;}
html[data-eo-theme="dark"] .st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"],
html[data-eo-theme="dark"] .st-key-eo_trend_switch [data-testid="stBaseButton-segmented_controlActive"] p{color:#F87171 !important;}
.st-key-eo_trend_switch [data-testid^="stBaseButton-segmented_control"] p{font-size:13px;font-weight:600;white-space:nowrap;}
.stApp .js-plotly-plot .gridlayer path{stroke:var(--eo-chart-grid) !important;}
.stApp .js-plotly-plot .xlines-above{stroke:var(--eo-line) !important;}

.st-key-eo_filters [data-testid="stColumn"],
.st-key-eo_filters [data-testid="column"] {
    flex: 0 0 300px !important;
    width: 300px !important;
    min-width: 300px !important;
}
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
.st-key-eo_filters [data-testid="stElementContainer"]:has([data-testid="stSelectbox"]),
.st-key-eo_filters [data-testid="stSelectbox"],
.st-key-eo_filters [data-baseweb="select"] {
    width: 100% !important;
    max-width: none !important;
    min-width: 0 !important;
}

@media (max-width: 1024px) {
  .st-key-eo_filters [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap: 10px !important;
  }
  .st-key-eo_filters [data-testid="stColumn"],
  .st-key-eo_filters [data-testid="column"] {
    flex: 1 1 calc(33.33% - 10px) !important;
    width: auto !important;
    min-width: 160px !important;
  }
  .st-key-eo_filters [data-testid="stColumn"]:nth-last-child(-n+2),
  .st-key-eo_filters [data-testid="column"]:nth-last-child(-n+2) {
    flex: 1 1 calc(50% - 10px) !important;
    width: auto !important;
    margin-left: 0 !important;
    margin-top: 6px !important;
  }
  .st-key-eo_filters [data-testid="stColumn"]:nth-last-child(-n+2) button,
  .st-key-eo_filters [data-testid="column"]:nth-last-child(-n+2) button {
    width: 100% !important;
  }
}
@media (max-width: 768px) {
  .st-key-eo_filters [data-testid="stColumn"],
  .st-key-eo_filters [data-testid="column"] {
    flex: 1 1 calc(50% - 10px) !important;
  }
}

.eo-header{padding-bottom:10px;border-bottom:1px solid var(--eo-border);margin:0;}
.eo-title{font-size:2.75rem;font-weight:700;line-height:1.15;color:var(--eo-text);letter-spacing:-.01em;margin:0;}
.eo-caption{color:var(--eo-label);font-size:14px;line-height:1.5;margin:4px 0 0 0;}
@media (max-width: 1024px) {
  .eo-title{font-size:2.15rem !important;}
  .eo-caption{font-size:13px !important;}
}
@media (max-width: 768px) {
  .eo-title{font-size:1.85rem !important;}
}

.st-key-eo_filters{padding-top:16px;}
.st-key-eo_filters [data-testid="stWidgetLabel"]{margin-bottom:4px;min-height:0;}
.eo-subtitle{color:var(--eo-label);font-size:14px;margin:-14px 0 14px 0;}

.eo-kpi-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin:6px 0 18px 0;}
@media (max-width:1200px) and (min-width:881px){
  .eo-kpi-row{grid-template-columns:repeat(5,minmax(0,1fr)) !important;gap:10px !important;}
  .eo-kpi{padding:12px 14px !important;min-height:98px !important;}
  .eo-kpi-value{font-size:26px !important;margin:6px 0 4px 0 !important;}
  .eo-kpi-label{font-size:10.5px !important;}
  .eo-kpi-sub{font-size:11px !important;}
}
@media (max-width:880px) and (min-width:601px){
  .eo-kpi-row{grid-template-columns:repeat(3,minmax(0,1fr)) !important;gap:10px !important;}
  .eo-kpi{padding:12px 14px !important;min-height:95px !important;}
  .eo-kpi-value{font-size:26px !important;margin:6px 0 4px 0 !important;}
  .eo-kpi-label{font-size:10.5px !important;}
  .eo-kpi-sub{font-size:11px !important;}
}
@media (max-width:600px){
  .eo-kpi-row{grid-template-columns:repeat(2,minmax(0,1fr)) !important;gap:8px !important;}
  .eo-kpi{padding:10px 12px !important;min-height:90px !important;}
  .eo-kpi-value{font-size:22px !important;margin:4px 0 3px 0 !important;}
  .eo-kpi-label{font-size:10px !important;}
}

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

@media (max-width: 1150px) {
  .st-key-eo_charts > [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 16px !important;
  }
  .st-key-eo_charts > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
  .st-key-eo_charts > [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
}

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
        padding:12px 18px;border:none;border-bottom:1px solid var(--eo-border);white-space:nowrap !important;}
.eo-table td{padding:10px 18px;border:none;border-bottom:1px solid var(--eo-border-soft);vertical-align:middle;white-space:nowrap !important;}
.eo-table tr:last-child td{border-bottom:none;}
.eo-student{display:flex;align-items:center;gap:12px;}
.eo-avatar{width:34px;height:34px;border-radius:50%;background:#475569;color:#FFFFFF;font-size:13px;
        font-weight:600;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.eo-name{font-weight:600;color:var(--eo-text-2);white-space:nowrap !important;word-break:keep-all !important;}
.eo-id{font-size:12px;color:var(--eo-muted);white-space:nowrap !important;word-break:keep-all !important;}
.eo-pill{display:inline-flex !important;align-items:center !important;justify-content:center !important;
        white-space:nowrap !important;line-height:1 !important;padding:4px 10px;border-radius:999px;
        font-size:12px;font-weight:600;border:1px solid;width:auto !important;max-width:none !important;
        word-break:keep-all !important;flex-wrap:nowrap !important;}
.pill-green{background:var(--pg-bg);color:var(--pg-fg);border-color:var(--pg-bd);}
.pill-red{background:var(--pr-bg);color:var(--pr-fg);border-color:var(--pr-bd);}
.pill-blue{background:var(--pb-bg);color:var(--pb-fg);border-color:var(--pb-bd);}
.pill-amber{background:var(--pa-bg);color:var(--pa-fg);border-color:var(--pa-bd);}
.pill-yellow{background:var(--py-bg);color:var(--py-fg);border-color:var(--py-bd);}
.pill-gray{background:var(--px-bg);color:var(--px-fg);border-color:var(--px-bd);}
.eo-muted{color:var(--eo-muted);}

.st-key-eo_table{background:var(--eo-surface);border:1px solid var(--eo-border);border-radius:12px;
        box-shadow:var(--eo-shadow);margin-top:18px;gap:0 !important;overflow-x:auto !important;
        -webkit-overflow-scrolling:touch !important;width:100% !important;}
.st-key-eo_table_head{background:var(--eo-surface-2);border-bottom:1px solid var(--eo-border);padding:12px 18px;
        min-width:1000px !important;}
.st-key-eo_table_head [data-testid="stHorizontalBlock"]{min-width:1000px !important;}
.eo-th{font-size:12px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--eo-muted);
       white-space:nowrap !important;word-break:keep-all !important;}
.st-key-eo_table_rows{gap:0 !important;min-width:1000px !important;overflow-x:hidden !important;}
.st-key-eo_table_rows > div{min-width:1000px !important;}
.st-key-eo_table_rows [data-testid="stHorizontalBlock"]{padding:10px 18px;border-bottom:1px solid var(--eo-border-soft);
        align-items:center;min-width:1000px !important;}
.st-key-eo_table [data-testid="stHorizontalBlock"]{gap:12px !important;column-gap:12px !important;}
.st-key-eo_table_rows [data-testid="stColumn"],
.st-key-eo_table_rows [data-testid="stColumn"] > div,
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stVerticalBlock"]{gap:0 !important;row-gap:0 !important;}
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stElementContainer"],
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stMarkdown"],
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stTooltipHoverTarget"]{min-height:0 !important;height:auto !important;}
.st-key-eo_table_rows [data-testid="stColumn"] [data-testid="stElementContainer"]{margin:0 !important;}
.st-key-eo_table_rows [data-testid="stButton"]{margin:0 !important;padding:0 !important;line-height:1.3;}
.st-key-eo_table_rows .eo-id{margin-top:2px;line-height:1.3;}
.st-key-eo_table [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
.eo-cell{font-size:14px;color:var(--eo-text-2);}
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
    """Which LastUpdated-style column Student_Lifecycle has, found with ONE query."""
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


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _load_programs():
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT ProgramID, ProgramCode, ProgramName "
            "FROM Program WHERE IsActive = 1 ORDER BY ProgramName"
        )
        rows = cur.fetchall()
        db_name = None
        if not rows:
            cur.execute("SELECT DATABASE() AS db")
            db_name = cur.fetchone()["db"]
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
    except mysql

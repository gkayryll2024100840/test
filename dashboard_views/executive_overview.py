# EXEC OVERVIEW
# UPDATED: 9/30/2026 (5:45 pm)

import html
import io
import json
import re
from datetime import datetime
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
    get_stage_labels,
)
from dashboard_views.components import DARK_MODE_CSS, set_header_context
from field_mapping import load_mappings

st.set_page_config(page_title="Executive Overview", layout="wide")
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view executive reporting.")
    st.stop()


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
INACTIVE_STAGE = "Inactive"

STAGE_ORDER = ["Coursework", "Comprehensive Exam", "Capstone", "Completed", INACTIVE_STAGE]

STAGE_COLORS = {
    "Coursework": "#B91B21",
    "Comprehensive Exam": "#FFCA06",
    "Capstone": "#55AB22",
    "Completed": "#4A7CF2",
    INACTIVE_STAGE: "#9CA3AF",
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
STAGE_PILLAR = {"Coursework": "Coursework", "Comprehensive Exam": "CompExam", "Capstone": "Capstone"}
_stage_labels = {}


def stage_name(stage):
    pillar = STAGE_PILLAR.get(stage)
    return _stage_labels.get(pillar, stage) if pillar else stage


@st.cache_data(ttl=60, show_spinner=False)
def cached_stage_labels(program_id):
    return get_stage_labels(program_id)


@st.cache_data(ttl=60, show_spinner=False)
def cached_kpi_tiles(program_id):
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
  --px-bg:rgba(148,163,184

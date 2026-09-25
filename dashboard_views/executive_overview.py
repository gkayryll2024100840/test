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
    get_user_program,
)
from dashboard_views.components import DARK_MODE_CSS

st.set_page_config(page_title="Executive Overview", layout="wide")
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view executive reporting.")
    st.stop()


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
STAGE_ORDER = ["Coursework", "Comprehensive Exam", "Capstone", "Completed"]

STAGE_COLORS = {
    "Coursework": "#C0392B",
    "Comprehensive Exam": "#B8860B",
    "Capstone": "#1F3864",
    "Completed": "#2E7D32",
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


# ---------------------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------------------
PAGE_CSS = """
<style>
.block-container,
[data-testid="stMainBlockContainer"] {
    padding-top: 1.5rem !important;
}
header[data-testid="stHeader"] { display: none; }

.st-key-eo_filters [data-testid="stColumn"],
.st-key-eo_filters [data-testid="column"] {
    flex: 0 0 220px !important;
    width: 220px !important;
    min-width: 220px !important;
}
/* export button: last column in the filter row, pushed to the far right */
.st-key-eo_filters [data-testid="stColumn"]:last-child,
.st-key-eo_filters [data-testid="column"]:last-child {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
    margin-left: auto !important;
}

/* page title with the divider line right under it (one element = no extra Streamlit gaps) */
.eo-title{font-size:2.75rem;font-weight:700;line-height:1.15;color:#0F172A;letter-spacing:-.01em;
        padding-bottom:6px;border-bottom:1px solid #E5E7EB;margin:0;}
/* SPACE BETWEEN THE TITLE LINE AND THE FILTERS: change padding-top */
.st-key-eo_filters{padding-top:16px;}
/* SPACE BETWEEN EACH FILTER LABEL (e.g. "Enrollment Status") AND ITS DROPDOWN: change margin-bottom */
.st-key-eo_filters [data-testid="stWidgetLabel"]{margin-bottom:4px;min-height:0;}
.eo-subtitle{color:#4B5563;font-size:14px;margin:-14px 0 14px 0;}
.eo-kpi-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin:6px 0 18px 0;}
@media (max-width:1200px){.eo-kpi-row{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media (max-width:700px){.eo-kpi-row{grid-template-columns:repeat(1,minmax(0,1fr));}}
.eo-kpi{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:18px 20px;
        box-shadow:0 1px 2px rgba(16,24,40,.05);min-height:122px;display:flex;flex-direction:column;}
.eo-kpi-label{font-size:12px;letter-spacing:.03em;text-transform:uppercase;color:#4B5563;}
.eo-kpi-value{font-size:34px;font-weight:700;color:#0F172A;line-height:1.1;margin:12px 0 8px 0;}
.eo-kpi-sub{font-size:12px;color:#6B7280;margin-top:auto;}
.eo-kpi{position:relative;}
.eo-info{position:absolute;top:14px;right:14px;width:20px;height:20px;border-radius:50%;
        border:1.5px solid #6B7280;color:#6B7280;font-family:inherit;font-size:12px;font-weight:600;
        line-height:17px;font-style:normal;text-align:center;cursor:help;outline:none;}
.eo-info:hover,.eo-info:focus{border-color:#0F172A;color:#0F172A;}
.eo-tip{visibility:hidden;opacity:0;transition:opacity .15s;position:absolute;top:28px;right:-8px;z-index:1000;
        width:390px;max-width:90vw;background:#FFFFFF;border:1px solid #E5E7EB;border-radius:10px;padding:14px 16px;
        box-shadow:0 8px 24px rgba(16,24,40,.14);font-family:inherit;font-size:13px;line-height:1.6;
        font-weight:400;letter-spacing:0;text-transform:none;color:#374151;text-align:left;cursor:default;
        white-space:normal;}
.eo-info:hover .eo-tip,.eo-info:focus .eo-tip,.eo-info:focus-within .eo-tip{visibility:visible;opacity:1;}
.eo-tip-formula{font-weight:600;color:#0F172A;margin-bottom:10px;white-space:nowrap;}
/* let the tooltip spill outside Streamlit's markdown wrappers instead of being clipped */
[data-testid="stElementContainer"]:has(.eo-kpi-row),
[data-testid="element-container"]:has(.eo-kpi-row),
[data-testid="stMarkdown"]:has(.eo-kpi-row),
[data-testid="stMarkdownContainer"]:has(.eo-kpi-row){overflow:visible !important;position:relative;z-index:20;}
.eo-tip-row{display:flex;align-items:baseline;gap:6px;}
.eo-tip-dots{flex:1;border-bottom:1px solid #D1D5DB;transform:translateY(-4px);}
.eo-tip-caption{margin-top:8px;padding-top:8px;border-top:1px solid #F1F2F4;font-size:12px;color:#6B7280;}
.eo-placeholder{color:#9CA3AF;font-style:italic;}
.eo-flat{color:#6B7280;}
.eo-up{color:#2E9E3E;} .eo-down{color:#C62828;} .eo-risk{color:#C62828;}

div[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF;border:1px solid #E5E7EB !important;
        border-radius:12px !important;box-shadow:0 1px 2px rgba(16,24,40,.05);}
.eo-card-head{display:flex;flex-direction:column;align-items:flex-start;}
.eo-card-title{display:block;font-size:20px;font-weight:700;color:#0F172A;margin:4px 0 2px 4px;}
.eo-card-sub{display:block;font-size:12px;color:#6B7280;margin:0 0 4px 4px;}

.eo-table-wrap{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;overflow:auto;
        max-height:560px;margin-top:18px;box-shadow:0 1px 2px rgba(16,24,40,.05);}
.eo-table{width:100%;border-collapse:collapse;font-size:14px;color:#111827;margin:0;}
.eo-table th{position:sticky;top:0;z-index:1;background:#F9FAFB;text-align:left;font-size:12px;
        font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:#6B7280;
        padding:12px 18px;border:none;border-bottom:1px solid #E5E7EB;}
.eo-table td{padding:10px 18px;border:none;border-bottom:1px solid #F1F2F4;vertical-align:middle;white-space:nowrap;}
.eo-table tr:last-child td{border-bottom:none;}
.eo-student{display:flex;align-items:center;gap:12px;}
.eo-avatar{width:34px;height:34px;border-radius:50%;background:#475569;color:#FFFFFF;font-size:13px;
        font-weight:600;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.eo-name{font-weight:600;color:#111827;} .eo-id{font-size:12px;color:#6B7280;}
.eo-pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid;}
.pill-green{background:#ECFDF3;color:#15803D;border-color:#BBF7D0;}
.pill-red{background:#FEF2F2;color:#B91C1C;border-color:#FECACA;}
.pill-blue{background:#EFF6FF;color:#1D4ED8;border-color:#BFDBFE;}
.pill-amber{background:#FFFBEB;color:#B45309;border-color:#FDE68A;}
.pill-gray{background:#F3F4F6;color:#4B5563;border-color:#E5E7EB;}
.eo-muted{color:#6B7280;}
</style>
"""

PILL_CLASS = {
    "Completed": "pill-green",
    "Passed": "pill-green",
    "Defended for Completion": "pill-green",
    "Cancelled": "pill-red",
    "In-Progress": "pill-blue",
    "Pending": "pill-amber",
    "Incomplete": "pill-amber",
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
    df["ActiveStage"] = np.select(
        [~cw_done, ~ce_done, ~cs_done],
        ["Coursework", "Comprehensive Exam", "Capstone"],
        default="Completed",
    )
    df["IsComplete"] = df["ActiveStage"].eq("Completed")
    current_status = np.select(
        [df["ActiveStage"].eq(stage) for stage in STAGE_STATUS_COL],
        [df[col].astype(object) for col in STAGE_STATUS_COL.values()],
        default=None,
    )
    df["IsAtRisk"] = pd.Series(current_status, index=df.index).isin(AT_RISK_STATUSES)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# BUSINESS LOGIC
# ---------------------------------------------------------------------------
def determine_active_stage(row) -> str:
    if row.get("CourseworkStatus") != COURSEWORK_DONE:
        return "Coursework"
    if row.get("CompExamStatus") != COMPEXAM_DONE:
        return "Comprehensive Exam"
    if row.get("CapstoneStatus") != CAPSTONE_DONE:
        return "Capstone"
    return "Completed"


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


def completion_rate(df: pd.DataFrame) -> float:
    return round(df["IsComplete"].mean() * 100, 1) if not df.empty else 0.0


def on_time_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    flags = df["GraduateOnTime"].astype(str).str.strip().str.lower().isin(ON_TIME_TRUE)
    return round(flags.mean() * 100, 1)


def lifecycle_counts(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["ActiveStage"].value_counts().reindex(STAGE_ORDER, fill_value=0)
    return counts.rename_axis("Stage").reset_index(name="Count")


def cohort_history(df: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"Cohort": c, "Completion": completion_rate(g), "OnTime": on_time_rate(g),
         "Remaining": int((~g["IsComplete"]).sum())}
        for c, g in df.groupby("Cohort")
    ]
    hist = pd.DataFrame(rows, columns=["Cohort", "Completion", "OnTime", "Remaining"])
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


def kpi_card(label, value, sub_html="&nbsp;", info_html=None):
    info = (f'<div class="eo-info" tabindex="0">i<div class="eo-tip">{info_html}</div></div>'
            if info_html else "")
    return (
        f'<div class="eo-kpi">{info}<div class="eo-kpi-label">{label}</div>'
        f'<div class="eo-kpi-value">{value}</div>'
        f'<div class="eo-kpi-sub">{sub_html}</div></div>'
    )


def render_kpi_row(cards):
    st.markdown(f'<div class="eo-kpi-row">{"".join(cards)}</div>', unsafe_allow_html=True)


def remaining_info_html(df: pd.DataFrame) -> str:
    """Tooltip for the Remaining Students tile: the formula, then the split by lifecycle stage."""
    total, completed = len(df), int(df["IsComplete"].sum())
    breakdown = (
        df.loc[~df["IsComplete"], "ActiveStage"].value_counts()
        .reindex(["Coursework", "Comprehensive Exam", "Capstone"], fill_value=0)
    )
    rows = "".join(
        f'<div class="eo-tip-row"><span style="color:{STAGE_COLORS[stage]};font-weight:600;">{stage}</span>'
        f'<span class="eo-tip-dots"></span><span>{n:,}</span></div>'
        for stage, n in breakdown.items()
    )
    return (
        f'<div class="eo-tip-formula">Total Enrolled ({total:,}) &minus; Completed ({completed:,}) '
        f'= Total ({total - completed:,})</div>{rows}'
        '<div class="eo-tip-caption">Remaining students are computed as Total Enrolled minus Completed, '
        'then split by the lifecycle stage each student is currently in.</div>'
    )


def card_header(title, subtitle):
    st.markdown(
        f'<div class="eo-card-head"><div class="eo-card-title">{title}</div>'
        f'<div class="eo-card-sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


BASE_LAYOUT = dict(
    height=300,
    margin=dict(l=10, r=10, t=30, b=10),
    plot_bgcolor="white",
    paper_bgcolor="white",
    showlegend=False,
    font=dict(size=12, color="#6B7280"),
)


def lifecycle_bar(counts: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=counts["Stage"],
            y=counts["Count"],
            marker_color=[STAGE_COLORS[s] for s in counts["Stage"]],
            text=counts["Count"],
            textposition="outside",
            textfont=dict(size=12, color="#4B5563"),
            cliponaxis=False,
            hovertemplate="%{x}: %{y} students<extra></extra>",
        )
    )
    fig.update_layout(**BASE_LAYOUT, bargap=0.3)
    fig.update_yaxes(visible=False, range=[0, max(int(counts["Count"].max()), 1) * 1.2])
    fig.update_xaxes(showgrid=False, showline=True, linecolor="#D1D5DB",
                     tickfont=dict(size=11, color="#6B7280"))
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
    cls = PILL_CLASS.get(value, "pill-gray")
    return f'<span class="eo-pill {cls}">{html.escape(value)}</span>'


def render_student_table(df: pd.DataFrame):
    if df.empty:
        st.info("No students match these filters.")
        return

    df = df.sort_values(["LastUpdated", "LastName"], ascending=[False, True], na_position="last")

    rows = []
    for r in df.to_dict("records"):
        first = str(r["FirstName"] or "").strip()
        last = str(r["LastName"] or "").strip()
        name = f"{first} {last}".strip() or "Unnamed student"
        initials = ((first[:1] + last[:1]) or name[:1]).upper()
        adviser = r["Adviser"] if pd.notna(r["Adviser"]) else "—"
        cohort = r["Cohort"] if pd.notna(r["Cohort"]) else "—"
        updated = r["LastUpdated"].strftime("%b %d, %Y") if pd.notna(r["LastUpdated"]) else "—"

        rows.append(
            "<tr>"
            f'<td><div class="eo-student"><div class="eo-avatar">{html.escape(initials)}</div>'
            f'<div><div class="eo-name">{html.escape(name)}</div>'
            f'<div class="eo-id">{html.escape(str(r["StudentNumber"]))}</div></div></div></td>'
            f"<td>{html.escape(str(cohort))}</td>"
            f"<td>{html.escape(str(adviser))}</td>"
            f"<td>{status_pill(r['CourseworkStatus'])}</td>"
            f"<td>{status_pill(r['CompExamStatus'])}</td>"
            f"<td>{updated}</td>"
            "</tr>"
        )

    header = (
        "<tr><th>Student Name &amp; ID</th><th>Current Cohort</th><th>Assigned Adviser</th>"
        "<th>Coursework Status</th><th>Comp. Exam Status</th><th>Last Updated</th></tr>"
    )

    st.markdown(
        f'<div class="eo-table-wrap"><table class="eo-table"><thead>{header}</thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


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
    "GraduateOnTime": "Graduate On Time",
    "LastUpdated": "Last Updated",
}


def export_table(df: pd.DataFrame) -> pd.DataFrame:
    """The student table as it goes into the export: readable headers, sorted, dates as text."""
    out = df[[c for c in EXPORT_COLUMNS if c in df.columns]].copy()
    if "LastUpdated" in out:
        out["LastUpdated"] = out["LastUpdated"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
    out = out.sort_values(["ProgramCode", "Cohort", "LastName", "FirstName"], na_position="last")
    out = out.astype(object).where(out.notna(), "")
    return out.rename(columns=EXPORT_COLUMNS)


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


def _value_labels(DataLabelList):
    """Chart labels that show only the number (not the series/category name)."""
    lbl = DataLabelList()
    lbl.showVal = True
    lbl.showSerName = lbl.showCatName = lbl.showLegendKey = lbl.showPercent = False
    return lbl


def build_export_xlsx(df, hist, filters: dict, exported_by: str) -> bytes:
    """Excel export with two tabs: 'Overview' (filters, KPIs, both charts) and 'Students' (the table)."""
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.series import DataPoint
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
    ov["A2"] = f"Exported {datetime.now():%b %d, %Y %H:%M} by {exported_by}"
    ov["A2"].font = Font(italic=True, size=9, color=grey)

    # --- Filters ---
    ov["A4"] = "FILTERS"; ov["A4"].font = section
    for i, (k, v) in enumerate(filters.items(), start=5):
        ov.cell(i, 1, k).font = Font(color=grey)
        ov.cell(i, 2, v).font = Font(bold=True)

    # --- Lifecycle stage data (the KPIs below are formulas on this table) ---
    counts = lifecycle_counts(df)
    ov["A16"] = "COHORT BY LIFECYCLE STAGE"; ov["A16"].font = section
    ov["A17"], ov["B17"] = "Stage", "Students"
    for c in ("A17", "B17"):
        ov[c].font = Font(bold=True, color="FFFFFF"); ov[c].fill = head_fill
    for i, (stage, n) in enumerate(zip(counts["Stage"], counts["Count"]), start=18):
        ov.cell(i, 1, stage); ov.cell(i, 2, int(n))
        for c in (1, 2):
            ov.cell(i, c).border = thin
    # rows 18-21 = Coursework, Comprehensive Exam, Capstone, Completed
    yes = int(df["GraduateOnTime"].astype(str).str.strip().str.lower().isin(ON_TIME_TRUE).sum())
    ov["A22"] = 'Graduate On Time = "yes"'; ov["B22"] = yes
    ov["A22"].font = ov["B22"].font = Font(italic=True, color=grey)

    # --- KPIs ---
    cohort = filters.get("Cohort", "All Cohorts")
    ov["A10"] = "KEY METRICS"; ov["A10"].font = section
    kpis = [
        ("Total Enrolled", "=SUM(B18:B21)", "#,##0", ""),
        ("On-Time Graduation Rate", "=IF(B11=0,0,B22/B11)", "0.0%",
         compare_text(hist, "OnTime", cohort)),
        ("Overall Completion", "=IF(B11=0,0,B21/B11)", "0.0%",
         compare_text(hist, "Completion", cohort)),
        ("Remaining Students", "=B11-B21", "#,##0",
         compare_text(hist, "Remaining", cohort, kind="count", higher_is_better=False)),
    ]
    for i, (label, formula, fmt, cmp_txt) in enumerate(kpis, start=11):
        ov.cell(i, 1, label).font = Font(color=grey)
        cell = ov.cell(i, 2, formula)
        cell.number_format, cell.font = fmt, Font(bold=True, size=12, color=navy)
        cmp_cell = ov.cell(i, 3, cmp_txt)
        color = "2E9E3E" if "better" in cmp_txt else "C62828" if "worse" in cmp_txt else "9CA3AF"
        cmp_cell.font = Font(size=9, color=color, italic=color == "9CA3AF")
    ov["A15"] = "Remaining Students = Total Enrolled − Completed, split by current lifecycle stage."
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
    bar.title, bar.style, bar.legend = "Cohort by Lifecycle Stage", 10, None
    bar.y_axis.title, bar.y_axis.majorGridlines = "Students", None
    bar.add_data(Reference(ov, min_col=2, min_row=17, max_row=21), titles_from_data=True)
    bar.set_categories(Reference(ov, min_col=1, min_row=18, max_row=21))
    series = bar.series[0]
    for idx, stage in enumerate(STAGE_ORDER):
        pt = DataPoint(idx=idx)
        pt.graphicalProperties.solidFill = STAGE_COLORS[stage].lstrip("#")
        pt.graphicalProperties.line.noFill = True
        series.dPt.append(pt)
    series.dLbls = _value_labels(DataLabelList)
    bar.x_axis.delete = bar.y_axis.delete = False      # openpyxl 3.1 hides axes otherwise
    bar.width, bar.height = 17, 8.5
    ov.add_chart(bar, "E3")

    if len(recent) >= 2:
        line = LineChart()
        line.title, line.style, line.legend = "Overall Completion % — Trend", 12, None
        line.y_axis.number_format, line.y_axis.title = "0%", "Completion"
        line.add_data(Reference(ov, min_col=2, min_row=26, max_row=26 + len(recent)), titles_from_data=True)
        line.set_categories(Reference(ov, min_col=1, min_row=27, max_row=26 + len(recent)))
        s0 = line.series[0]
        s0.graphicalProperties.line.solidFill, s0.graphicalProperties.line.width = "111827", 19050
        s0.marker.symbol, s0.marker.size = "circle", 6
        s0.smooth = False
        s0.dLbls = _value_labels(DataLabelList); s0.dLbls.position = "t"
        line.x_axis.delete = line.y_axis.delete = False
        line.width, line.height = 17, 8.5
        ov.add_chart(line, "E21")

    # --- Students tab ---
    st_ws = wb.create_sheet("Students")
    table = export_table(df)
    st_ws.append(list(table.columns))
    for row in table.itertuples(index=False):
        st_ws.append(list(row))
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


def export_file_name(program_label, cohort, status) -> str:
    parts = ["executive_overview", program_label, cohort, status, datetime.now().strftime("%Y-%m-%d")]
    return "_".join(re.sub(r"[^A-Za-z0-9]+", "-", str(p)).strip("-") for p in parts) + ".xlsx"


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
                (_current_user_label(), "Executive Overview", json.dumps(filters), row_count, file_name),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
    except Exception as e:  # never block the download because logging failed
        st.toast(f"Export downloaded, but it couldn't be logged: {e}")


# ---------------------------------------------------------------------------
# PAGE ASSEMBLY
# ---------------------------------------------------------------------------
def render_executive_overview():
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    # plain div instead of st.title: no hover link icon, and the line sits right under the text
    st.markdown('<div class="eo-title">Executive Overview</div>', unsafe_allow_html=True)

    # ---- Data ----
    try:
        all_df = get_executive_data()
    except mysql.connector.Error as err:
        st.error(format_mysql_error(err))
        return
    except Exception as e:
        st.error(f"Failed to fetch executive overview data: {e}")
        return

    # ---- Filters: Enrollment | Cohort | Program ----
    with st.container(key="eo_filters"):
        f1, f2, f3, f4 = st.columns(4, gap="small", vertical_alignment="bottom")

        with f1:
            selected_status = st.selectbox("Enrollment Status", ENROLLMENT_OPTIONS)

        # Program is chosen before Cohort in code (it still displays third)
        with f3:
            programs_by_id = {p["ProgramID"]: p for p in get_program_options()}
            selected_program_id = st.selectbox(
                "Program", list(programs_by_id),
                format_func=lambda pid: programs_by_id[pid]["ProgramName"],
            )
            selected_program = programs_by_id[selected_program_id]

        program_df = all_df
        if selected_program["ProgramID"] is not None:
            program_df = all_df[all_df["ProgramID"] == selected_program["ProgramID"]]

        with f2:
            cohorts = sorted(program_df["Cohort"].dropna().unique(), key=cohort_sort_key, reverse=True)
            selected_cohort = st.selectbox("Cohort", ["All Cohorts"] + list(cohorts))

    # Program + status filters apply everywhere; cohort applies to everything except the trend
    status_df = program_df
    if selected_status != "All":
        status_df = program_df[
            program_df["EnrollmentStatus"].astype(str).str.strip().str.lower() == selected_status.lower()
        ]
    df = status_df
    if selected_cohort != "All Cohorts":
        df = status_df[status_df["Cohort"] == selected_cohort]

    hist = cohort_history(status_df)

    # ---- Export (far right of the filter row) ----
    program_label_for_file = (
        "All-Programs" if selected_program["ProgramID"] is None else selected_program["ProgramCode"]
    )
    file_name = export_file_name(program_label_for_file, selected_cohort, selected_status)
    export_filters = {
        "Enrollment Status": selected_status,
        "Cohort": selected_cohort,
        "Program": selected_program["ProgramName"],
    }
    with f4:
        st.download_button(
            "⬇ Export Excel",
            data=build_export_xlsx(df, hist, export_filters, _current_user_label()) if not df.empty else b"",
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=df.empty,
            help="Excel file with the current filters: Overview tab (KPIs + charts) and Students tab",
            on_click=log_export,
            args=(export_filters, len(df), file_name),
        )

    # ---- KPI row ----
    total_label = "Total Enrolled" if selected_status == "All" else f"Total {selected_status}"
    program_label = (
        "All Programs" if selected_program["ProgramID"] is None
        else (selected_program["ProgramCode"] or selected_program["ProgramName"])
    )

    render_kpi_row([
        kpi_card(total_label, f"{len(df):,}", f"{html.escape(program_label)} · {html.escape(selected_cohort)}"),
        kpi_card("On-Time Graduation Rate", f"{on_time_rate(df):.1f}%",
                 delta_html(hist, "OnTime", selected_cohort)),
        kpi_card("Overall Completion", f"{completion_rate(df):.1f}%",
                 delta_html(hist, "Completion", selected_cohort)),
        kpi_card("Remaining Students", f"{int((~df['IsComplete']).sum()):,}",
                 delta_html(hist, "Remaining", selected_cohort, kind="count", higher_is_better=False),
                 info_html=remaining_info_html(df)),
        kpi_card("Students at Risk", "&nbsp;"),
    ])

    # ---- Charts ----
    c1, c2 = st.columns(2, gap="medium")
    chart_config = {"displayModeBar": False}

    with c1:
        with st.container(border=True):
            card_header("Cohort by Lifecycle Stage", "Students currently active per stage")
            st.plotly_chart(lifecycle_bar(lifecycle_counts(df)),
                            use_container_width=True, config=chart_config)

    with c2:
        with st.container(border=True):
            recent = hist.tail(4)
            card_header("Overall Completion % — Trend",
                        f"Last {len(recent)} cohorts, program-wide")
            if len(recent) >= 2:
                st.plotly_chart(completion_trend(recent),
                                use_container_width=True, config=chart_config)
            else:
                st.info("At least two cohorts are needed to show a trend.")

    # ---- Student table ----
    render_student_table(df)


if __name__ == "__main__":
    render_executive_overview()
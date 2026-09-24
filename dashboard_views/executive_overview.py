import html
import re
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
    get_all_programs,
    get_enrollment_count,
    get_user_program,
)
from dashboard_views.components import DARK_MODE_CSS

st.set_page_config(page_title="Executive Overview", layout="wide")
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view executive reporting.")
    st.stop()

# ---------------------------------------------------------------
# Resolve the active program (set by Student Roster or by the user's pin)
# ---------------------------------------------------------------
user = st.session_state.get("user", {})
role = user.get("role")

if not st.session_state.get("active_program_id") and role != "IT/Admin":
    pinned = get_user_program(user.get("UserID"))
    if pinned:
        st.session_state["active_program_id"] = pinned["ProgramID"]
        st.session_state["active_program_code"] = pinned["ProgramCode"]

active_program_id = st.session_state.get("active_program_id")
active_code = st.session_state.get("active_program_code", "")

if not active_program_id:
    st.warning("⏳ No active program has been set. Please pick one on the Student Roster page first.")
    st.stop()

st.title(f"Executive Overview — {active_code} Program")

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

# Which lifecycle column holds the status of each active stage
STAGE_STATUS_COL = {
    "Coursework": "CourseworkStatus",
    "Comprehensive Exam": "CompExamStatus",
    "Capstone": "CapstoneStatus",
}

# A student is "at risk" when the status of their CURRENT stage is one of these.
# (Swap this for a due-date check once the lifecycle table stores stage deadlines.)
AT_RISK_STATUSES = {"Incomplete", "Cancelled"}

# Values in GraduateOnTime that count as "yes" (handles Yes / Y / 1 / TRUE)
ON_TIME_TRUE = {"yes", "y", "true", "1", "on time", "on-time"}

# Column names we'll look for on Student_Lifecycle for the "Last Updated" column
LAST_UPDATED_CANDIDATES = ["LastUpdated", "UpdatedAt", "DateUpdated", "LastModified", "ModifiedAt"]

ENROLLMENT_OPTIONS = ["All", "Enrolled", "Conditionally Enrolled"]
TERM_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3, "autumn": 3}


# ---------------------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------------------
PAGE_CSS = """
<style>
/* Remove Streamlit's default top padding */
.block-container,
[data-testid="stMainBlockContainer"] {
    padding-top: 1.5rem !important;
}

/* Optional: hide the thin header bar at the very top */
header[data-testid="stHeader"] {
    display: none;
}

/* Fixed-width filter dropdowns */
.st-key-eo_filters [data-testid="stColumn"],
.st-key-eo_filters [data-testid="column"] {
    flex: 0 0 220px !important;
    width: 220px !important;
    min-width: 220px !important;
}

.eo-subtitle{color:#4B5563;font-size:14px;margin:-14px 0 14px 0;}
.eo-kpi-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin:6px 0 18px 0;}
@media (max-width:1200px){.eo-kpi-row{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media (max-width:700px){.eo-kpi-row{grid-template-columns:repeat(1,minmax(0,1fr));}}
.eo-kpi{background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:18px 20px;
        box-shadow:0 1px 2px rgba(16,24,40,.05);min-height:122px;display:flex;flex-direction:column;}
.eo-kpi-label{font-size:12px;letter-spacing:.03em;text-transform:uppercase;color:#4B5563;}
.eo-kpi-value{font-size:34px;font-weight:700;color:#0F172A;line-height:1.1;margin:12px 0 8px 0;}
.eo-kpi-sub{font-size:12px;color:#6B7280;margin-top:auto;}
.eo-up{color:#2E9E3E;} .eo-down{color:#C62828;} .eo-risk{color:#C62828;}

div[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF;border:1px solid #E5E7EB !important;
        border-radius:12px !important;box-shadow:0 1px 2px rgba(16,24,40,.05);}
.eo-card-title{font-size:20px;font-weight:700;color:#0F172A;margin:4px 0 2px 4px;}
.eo-card-sub{font-size:12px;color:#6B7280;margin:0 0 4px 4px;}

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
@st.cache_data(ttl=300)
def get_executive_lifecycle_data(program_id: int, cohort_filter: str = "All Cohorts") -> pd.DataFrame:
    """Pulls one row per student in the given program with lifecycle statuses."""
    try:
        conn = get_db_connection()

        query = """
            SELECT
                s.StudentNumber,
                s.Cohort,
                s.EnrollmentStatus,
                sl.CourseworkStatus,
                sl.CompExamStatus,
                sl.CapstoneStatus,
                sl.GraduateOnTime,
                sl.GraduateDate
            FROM Students s
            LEFT JOIN Student_Lifecycle sl
                ON s.StudentNumber = sl.StudentNumber
            WHERE s.ProgramID = %s
        """
        params = [program_id]

        if cohort_filter and cohort_filter != "All Cohorts":
            query += " AND s.Cohort = %s"
            params.append(cohort_filter)

        df = pd.read_sql(query, conn, params=tuple(params))
        conn.close()

        # Normalize lifecycle status columns the same way db_connect does
        for col in ["CourseworkStatus", "CompExamStatus", "CapstoneStatus"]:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .map(LIFECYCLE_STATUS_MAP)
                    .fillna(df[col])
                )

        return df

    except mysql.connector.Error as err:
        st.error(format_mysql_error(err))
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to fetch executive overview data: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# DATA ACCESS LAYER
# ---------------------------------------------------------------------------
def _find_last_updated_column():
    """Uses db_connect's cached schema snapshot to see if a 'last updated' column exists."""
    for col in LAST_UPDATED_CANDIDATES:
        try:
            if check_column_exists(f"Student_Lifecycle.{col}"):
                return col
        except Exception:
            pass
    return None


def determine_active_stage(row) -> str:
    """Returns the student's current stage using the per-stage 'done' values."""
    if row.get("CourseworkStatus") != COURSEWORK_DONE:
        return "Coursework"
    if row.get("CompExamStatus") != COMPEXAM_DONE:
        return "Comprehensive Exam"
    if row.get("CapstoneStatus") != CAPSTONE_DONE:
        return "Capstone"
    return "Completed"

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
        raise RuntimeError(f"no active rows in Programs (app is connected to database '{db_name}')")
    return rows


def get_program_options():
    """'All Programs' plus every active program, for the Program dropdown."""
    all_option = {"ProgramID": None, "ProgramCode": "All", "ProgramName": "All Programs"}
    try:
        return [all_option] + _load_programs()
    except mysql.connector.Error as err:
        st.warning(f"Couldn't load programs: {format_mysql_error(err)}")
    except Exception as e:
        st.warning(f"Couldn't load programs: {e}")
    return [all_option]

@st.cache_data(ttl=300)
def get_executive_data() -> pd.DataFrame:
    """
    One row per student (all cohorts). Filtering happens in pandas so the
    cohort trend chart and the KPI cards share the same data set.
    Raises on DB errors; the caller shows the message.
    """
    last_col = _find_last_updated_column()
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
    
    conn = get_db_connection()
    try:
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    # A student with two advisers would appear twice -- keep one row per student
    df = df.drop_duplicates(subset="StudentNumber", keep="first").reset_index(drop=True)

    for col in ["CourseworkStatus", "CompExamStatus", "CapstoneStatus"]:
        df[col] = (
            df[col].astype(str).str.strip().str.lower()
            .map(LIFECYCLE_STATUS_MAP)
            .fillna(df[col])
        )

    df["ActiveStage"] = df.apply(determine_active_stage, axis=1)
    df["IsComplete"] = df["ActiveStage"] == "Completed"
    df["IsAtRisk"] = df.apply(
        lambda r: r["ActiveStage"] in STAGE_STATUS_COL
        and r.get(STAGE_STATUS_COL[r["ActiveStage"]]) in AT_RISK_STATUSES,
        axis=1,
    )
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def get_cohort_options():
    return ["All Cohorts"] + get_available_cohorts()


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------
def cohort_sort_key(cohort):
    """'2025 - Fall' -> (2025, 3). Used to put cohorts in chronological order."""
    s = str(cohort).lower()
    year = re.search(r"(19|20)\d{2}", s)
    term = next((v for k, v in TERM_ORDER.items() if k in s), 0)
    return (int(year.group()) if year else 0, term, s)


def completion_rate(df: pd.DataFrame) -> float:
    return round(df["IsComplete"].mean() * 100, 1) if not df.empty else 0.0


def on_time_rate(df: pd.DataFrame) -> float:
    """Share of ALL students (in the current filter) with GraduateOnTime = yes."""
    if df.empty:
        return 0.0
    flags = df["GraduateOnTime"].astype(str).str.strip().str.lower().isin(ON_TIME_TRUE)
    return round(flags.mean() * 100, 1)


def lifecycle_counts(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["ActiveStage"].value_counts().reindex(STAGE_ORDER, fill_value=0)
    return counts.rename_axis("Stage").reset_index(name="Count")


def cohort_history(df: pd.DataFrame) -> pd.DataFrame:
    """Completion % and on-time % per cohort, oldest -> newest."""
    rows = [
        {"Cohort": c, "Completion": completion_rate(g), "OnTime": on_time_rate(g)}
        for c, g in df.groupby("Cohort")
    ]
    hist = pd.DataFrame(rows, columns=["Cohort", "Completion", "OnTime"])
    if hist.empty:
        return hist
    hist = hist.iloc[sorted(range(len(hist)), key=lambda i: cohort_sort_key(hist.loc[i, "Cohort"]))]
    return hist.reset_index(drop=True)


def cohort_delta(hist: pd.DataFrame, metric: str, cohort: str):
    """Change vs the previous cohort. Only meaningful when one cohort is selected."""
    if cohort == "All Cohorts" or hist.empty:
        return None
    cohorts = list(hist["Cohort"])
    if cohort not in cohorts:
        return None
    idx = cohorts.index(cohort)
    if idx == 0:
        return None
    return round(hist.loc[idx, metric] - hist.loc[idx - 1, metric], 1)

    total_students = len(df)
    if total_students == 0:
        return 0.0

    completed_mask = (
        (df["CourseworkStatus"] == COURSEWORK_DONE) &
        (df["CompExamStatus"] == COMPEXAM_DONE) &
        (df["CapstoneStatus"] == CAPSTONE_DONE)
    )

    completed_count = completed_mask.sum()
    return round((completed_count / total_students) * 100, 1)


# ---------------------------------------------------------------------------
# UI PIECES
# ---------------------------------------------------------------------------
def delta_html(delta):
    if delta is None:
        return "&nbsp;"
    cls, arrow = ("eo-up", "▲") if delta >= 0 else ("eo-down", "▼")
    return f'<span class="{cls}">{arrow} {abs(delta):.1f} pts vs previous cohort</span>'


def kpi_card(label, value, sub_html="&nbsp;"):
    return (
        f'<div class="eo-kpi"><div class="eo-kpi-label">{label}</div>'
        f'<div class="eo-kpi-value">{value}</div>'
        f'<div class="eo-kpi-sub">{sub_html}</div></div>'
    )


def render_kpi_row(cards):
    st.markdown(f'<div class="eo-kpi-row">{"".join(cards)}</div>', unsafe_allow_html=True)
def render_kpi_card(header: str, value: str, subtext: str = "", border_color: str = "#1F3864"):
    if not subtext:
        subtext_block = '<div style="font-size:12px; opacity:0; margin-top:6px;">placeholder</div>'
    else:
        subtext_block = f'<div style="font-size:12px; color:#6b7280; margin-top:6px;">{subtext}</div>'


def card_header(title, subtitle):
    st.markdown(
        f'<div class="eo-card-title">{title}</div><div class="eo-card-sub">{subtitle}</div>',
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
    for _, r in df.iterrows():
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
# ---------------------------------------------------------------------------
# PAGE ASSEMBLY
# ---------------------------------------------------------------------------
def render_executive_overview():
    # ---- Filters ----
    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])

    with filter_col1:
        status_options = ["All Students", "Enrolled", "Conditionally Enrolled"]
        selected_status = st.selectbox("Enrollment Status:", status_options)

    with filter_col2:
        cohorts = get_cohort_dropdown_options(active_program_id)
        selected_cohort = st.selectbox("Cohort Status:", options=cohorts, index=0)

    # Pull filtered data at once
    df = get_executive_lifecycle_data(program_id=active_program_id, cohort_filter=selected_cohort)

    # Filter enrollment status
    if selected_status != "All Students":
        df = df[df["EnrollmentStatus"].str.lower() == selected_status.lower()]

    total_enrolled = compute_total_enrolled(df)
    on_time_rate = compute_on_time_graduation_rate(df)
    overall_completion = compute_overall_completion(df)
    lifecycle_counts = compute_lifecycle_counts(df)

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- KPI row ----
    st.markdown("""
    <style>
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        flex: 1 1 0% !important;
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    card_header = f"TOTAL {selected_status.upper()}" if selected_status != "All Students" else "TOTAL ENROLLED"

    with col1:
        render_kpi_card(
            header=card_header,
            value=str(get_enrollment_count(selected_status, cohort=selected_cohort, program_id=active_program_id)),
            subtext=f"{active_code} • {selected_cohort}",
            border_color="#b91b21",
        )

    with col2:
        render_kpi_card(
            header="ON-TIME GRADUATION RATE",
            value=f"{on_time_rate}%",
            border_color="#ffca06"
        )

    with col3:
        render_kpi_card(
            header="OVERALL COMPLETION",
            value=f"{overall_completion}%",
            border_color="#1F3864"
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Lifecycle chart ----
    def classify_lifecycle_stage(row):
        cw = str(row.get("CourseworkStatus", "")).lower().strip()
        ce = str(row.get("CompExamStatus", "")).lower().strip()
        cs = str(row.get("CapstoneStatus", "")).lower().strip()

        if cs in ["defended for completion", "completed", "passed"]:
            return "Completed"

        if cw in ["pending", "in-progress", "in progress", "enrolled", "active"]:
            return "Coursework"

        if ce in ["in-progress", "in progress", "incomplete"]:
            return "Comprehensive Exam"

        if cs in ["in-progress", "in progress"]:
            return "Capstone"

        return "Coursework"

    df["ActiveStage"] = df.apply(classify_lifecycle_stage, axis=1)

    df_stage = df.groupby("ActiveStage").size().reset_index(name="Count")

    all_stages = pd.DataFrame({"ActiveStage": ["Coursework", "Comprehensive Exam", "Capstone", "Completed"]})
    df_stage = pd.merge(all_stages, df_stage, on="ActiveStage", how="left").fillna({"Count": 0})

    colors = ["#b91b21", '#ffca06', '#1F3864', "#18A061"]

    fig = px.bar(
        df_stage,
        x="ActiveStage",
        y="Count",
        color="ActiveStage",
        color_discrete_sequence=colors
    )
    # Built as one line: blank lines / indentation would break Streamlit's HTML rendering
    st.markdown(
        f'<div class="eo-table-wrap"><table class="eo-table"><thead>{header}</thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# PAGE ASSEMBLY
# ---------------------------------------------------------------------------
def render_executive_overview():
    st.markdown(PAGE_CSS, unsafe_allow_html=True)   # ← must be here
    st.title("Executive Overview")
    
    # ---- Data (loaded first so the cohort list can follow the program) ----
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
        f1, f2, f3 = st.columns(3, gap="small")

        with f1:
            selected_status = st.selectbox("Enrollment Status", ENROLLMENT_OPTIONS)

        # Program is chosen before Cohort in code (it still displays third)
        with f3:
            selected_program = st.selectbox(
                "Program", get_program_options(), format_func=lambda p: p["ProgramName"]
            )

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

    # ---- KPI row ----
    total_label = "Total Enrolled" if selected_status == "All" else f"Total {selected_status}"
    at_risk = int(df["IsAtRisk"].sum())
    render_kpi_row([
        kpi_card(total_label, f"{len(df):,}", f"MBA · {html.escape(selected_cohort)}"),
        kpi_card("On-Time Graduation Rate", f"{on_time_rate(df):.1f}%",
                 delta_html(cohort_delta(hist, "OnTime", selected_cohort))),
        kpi_card("Overall Completion", f"{completion_rate(df):.1f}%",
                 delta_html(cohort_delta(hist, "Completion", selected_cohort))),
        kpi_card("Remaining Students", f"{int((~df['IsComplete']).sum()):,}",
                 "across all active stages"),
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
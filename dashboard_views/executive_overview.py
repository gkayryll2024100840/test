import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from db_connect import (
    get_db_connection,
    LIFECYCLE_STATUS_MAP,
    format_mysql_error,
    get_enrollment_count,
    get_user_program,
)
from dashboard_views.components import DARK_MODE_CSS
import mysql.connector

st.set_page_config(page_title="Executive Overview", layout="wide")

# Inject unified dark mode styling
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

# ----------------- Constants & Styling -----------------
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


# ---------------------------------------------------------------------------
# DATA ACCESS LAYER
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_cohort_dropdown_options(program_id: int):
    """Populates the cohort filter dropdown for a given program."""
    from db_connect import get_available_cohorts
    cohorts = get_available_cohorts(program_id=program_id)
    return ["All Cohorts"] + cohorts


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
# BUSINESS LOGIC / METRIC CALCULATIONS
# ---------------------------------------------------------------------------
def determine_active_stage(row) -> str:
    if row.get("CourseworkStatus") != COURSEWORK_DONE:
        return "Coursework"
    if row.get("CompExamStatus") != COMPEXAM_DONE:
        return "Comprehensive Exam"
    if row.get("CapstoneStatus") != CAPSTONE_DONE:
        return "Capstone"
    return "Completed"


def compute_lifecycle_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame({"Stage": STAGE_ORDER, "Count": [0] * len(STAGE_ORDER)})

    df = df.copy()
    df["ActiveStage"] = df.apply(determine_active_stage, axis=1)

    counts = (
        df["ActiveStage"]
        .value_counts()
        .reindex(STAGE_ORDER, fill_value=0)
        .reset_index()
    )
    counts.columns = ["Stage", "Count"]
    return counts


def compute_total_enrolled(df: pd.DataFrame) -> int:
    return int(df["StudentNumber"].nunique()) if not df.empty else 0


def compute_on_time_graduation_rate(df: pd.DataFrame) -> float:
    if df.empty or "GraduateOnTime" not in df.columns:
        return 0.0

    total_rows = len(df)
    if total_rows == 0:
        return 0.0

    df_clean = df["GraduateOnTime"].astype(str).str.strip().str.lower()
    on_time_count = (df_clean == "yes").sum()

    return round((on_time_count / total_rows) * 100, 1)


def compute_overall_completion(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0

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
# UI RENDERING
# ---------------------------------------------------------------------------
def render_kpi_card(header: str, value: str, subtext: str = "", border_color: str = "#1F3864"):
    if not subtext:
        subtext_block = '<div style="font-size:12px; opacity:0; margin-top:6px;">placeholder</div>'
    else:
        subtext_block = f'<div style="font-size:12px; color:#6b7280; margin-top:6px;">{subtext}</div>'

    st.markdown(
        f"""
        <div style="
            border-top: 4px solid {border_color};
            border-radius: 8px;
            padding: 16px 18px;
            background-color: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            width: 100%;
            min-width: 280px; 
            box-sizing: border-box;
            height: 145px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        ">
            <div>
                <div style="font-size:12px; letter-spacing:0.05em; color:#6b7280; font-weight:600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    {header}
                </div>
                <div style="font-size:30px; font-weight:700; color:#111827; margin-top:4px;">
                    {value}
                </div>
            </div>
            <div>
                {subtext_block}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_lifecycle_chart(counts_df: pd.DataFrame):
    fig = go.Figure()
    for _, row in counts_df.iterrows():
        stage = row["Stage"]
        fig.add_trace(
            go.Bar(
                x=[stage],
                y=[row["Count"]],
                marker_color=STAGE_COLORS.get(stage, "#999999"),
                text=[row["Count"]],
                textposition="outside",
                showlegend=False,
                width=0.55,
            )
        )

    fig.update_layout(
        title=None,
        height=380,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(showgrid=True, gridcolor="#eee", title=None),
        xaxis=dict(title=None),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)


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

    fig.update_traces(texttemplate='%{y}', textposition='outside')

    fig.update_xaxes(showgrid=False, zeroline=False, title="")
    fig.update_yaxes(showgrid=False, zeroline=False, title="", showticklabels=False)

    fig.update_layout(
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=30, b=10, l=10, r=10)
    )

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("### Cohort by Lifecycle Stage")
            st.markdown(
                f'<p style="color: #6b7280; font-size: 14px; margin-top: -10px;">Students currently active per stage | {selected_cohort} • {selected_status}</p>',
                unsafe_allow_html=True
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        pass


if __name__ == "__main__":
    render_executive_overview()

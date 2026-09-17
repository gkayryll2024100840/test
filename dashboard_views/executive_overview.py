import streamlit as st
import pandas as pd
from db_connect import get_enrollment_count, get_student_roster_data

st.set_page_config(page_title="Executive Overview", layout="wide")

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view executive reporting.")
    st.stop()

st.title("Executive Overview — MBA Program")

# ----------------- US-05: Enrolled Headcount -----------------
st.markdown("### Headcount Summary")
status_options = ["All", "Enrolled", "Conditionally Enrolled"]
selected_status = st.selectbox("FILTER BY ENROLLMENT STATUS:", status_options)

total_headcount = get_enrollment_count(selected_status)
st.metric(label=f"Total MBA Headcount ({selected_status} Status)", value=total_headcount)
st.caption("Count updates automatically from the live database.")

st.markdown("---")

# ----------------- US-14: Lifecycle Stage Health Indicators -----------------
st.markdown("### Student Lifecycle Health")
st.caption("Ethical, colorblind-safe monitoring across core lifecycle stages.")

# Configurable Thresholds (Criteria: Configurable, not hardcoded)
with st.expander("⚙️ Configure Health Thresholds", expanded=False):
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        green_threshold = st.slider("Satisfactory Threshold (% on track)", min_value=50, max_value=100, value=75)
    with col_t2:
        yellow_threshold = st.slider("Attention Threshold (% on track)", min_value=20, max_value=75, value=50)

# Colorblind-Safe Color Palette & Symbols (CIS310 Principles)
# Okabe-Ito / Color Universal Design (CUD) compatible
PALETTE = {
    "GREEN": {"color": "#009E73", "symbol": "🟢", "label": "On Track"},
    "YELLOW": {"color": "#E69F00", "symbol": "🟡", "label": "Needs Attention"},
    "RED": {"color": "#D55E00", "symbol": "🔴", "label": "Critical Alert"}
}

def evaluate_stage_health(pct_on_track):
    """Calculates status badge based on configurable thresholds."""
    if pct_on_track >= green_threshold:
        return PALETTE["GREEN"]
    elif pct_on_track >= yellow_threshold:
        return PALETTE["YELLOW"]
    return PALETTE["RED"]

# Load student data
df = get_student_roster_data()

if not df.empty:
    total_students = len(df)

    # 1. Coursework Pillar (US-07 data source)
    cw_completed = len(df[df["CourseworkStatus"] == "Completed"])
    cw_pct = round((cw_completed / total_students) * 100, 1) if total_students > 0 else 0
    cw_eval = evaluate_stage_health(cw_pct)

    # 2. Comprehensive Exam Pillar (US-08 data source)
    comp_passed = len(df[df["CompExamStatus"] == "Passed"])
    comp_pct = round((comp_passed / total_students) * 100, 1) if total_students > 0 else 0
    comp_eval = evaluate_stage_health(comp_pct)

    # 3. Capstone Pillar (US-09 data source)
    capstone_defended = len(df[df["CapstoneStatus"] == "Defended for Completion"])
    capstone_pct = round((capstone_defended / total_students) * 100, 1) if total_students > 0 else 0
    capstone_eval = evaluate_stage_health(capstone_pct)

    # Render 3 Pillar Metric Cards Side-by-Side
    col_cw, col_comp, col_cap = st.columns(3)

    with col_cw:
        st.markdown(f"#### {cw_eval['symbol']} Coursework Stage")
        st.metric(
            label=f"Completed Rate: {cw_eval['label']}",
            value=f"{cw_pct}%",
            delta=f"{cw_completed}/{total_students} Students"
        )
        st.caption(f"Status: **{cw_eval['label']}** (Threshold: {green_threshold}%)")

    with col_comp:
        st.markdown(f"#### {comp_eval['symbol']} Comprehensive Exam")
        st.metric(
            label=f"Passing Rate: {comp_eval['label']}",
            value=f"{comp_pct}%",
            delta=f"{comp_passed}/{total_students} Students"
        )
        st.caption(f"Status: **{comp_eval['label']}** (Threshold: {green_threshold}%)")

    with col_cap:
        st.markdown(f"#### {capstone_eval['symbol']} Capstone Stage")
        st.metric(
            label=f"Defense Rate: {capstone_eval['label']}",
            value=f"{capstone_pct}%",
            delta=f"{capstone_defended}/{total_students} Students"
        )
        st.caption(f"Status: **{capstone_eval['label']}** (Threshold: {green_threshold}%)")

else:
    st.info("No student lifecycle data found to compute indicators.")
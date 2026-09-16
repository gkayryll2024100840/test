import os
import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime

# Set page to broad view
st.set_page_config(page_title="Success Advisor Dashboard - MBA Program", layout="wide")

# Dictionary mapping environment variables. Reused when connecting to MySQL database.
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306))
}

# --- Database Helpers ---
def get_db_connection():
    return mysql.connector.connect(**db_config)

def record_timestamp_log(student_id, pillar, status):
    """
    Append-only: Inserts current time without using UPDATE or ALTER.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        INSERT INTO student_pillar_audit (student_id, pillar, status, recorded_at)
        VALUES (%s, %s, %s, NOW())
    """
    cursor.execute(query, (student_id, pillar, status))
    conn.commit()
    cursor.close()
    conn.close()

def get_latest_pillar_data(student_id):
    """
    Retrieves the most recent timestamp record for each pillar.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT pillar, status, recorded_at
        FROM student_pillar_audit
        WHERE student_id = %s
        ORDER BY recorded_at DESC
    """
    cursor.execute(query, (student_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    pillars = {
        "Coursework": {"status": "Completed", "last_updated": "MM/DD/YYYY"},
        "Comprehensive Exam": {"status": "In-Progress", "last_updated": "MM/DD/YYYY"},
        "Capstone Paper": {"status": "In-Progress","last_updated": "MM/DD/YYYY"},
        
    }

    found = set()
    for r in rows:
        p_name = r["pillar"]
        if p_name in pillars and p_name not in found:
            pillars[p_name] = {
                "status": r["status"],
                "last_updated": r["recorded_at"].strftime("%b %d, %Y %H:%M")
            }
            found.add(p_name)
    return pillars

# --- Seed Sample Roster Data ---
ROSTER_DATA = [
    {"Name": "Nico Kimson A. Chan", "ID#": "2023130130", "Year": "2", "Age": "19"},
    {"Name": "Sammuel King H. Paloma", "ID#": "2023135763", "Year": "2", "Age": "19"},
    {"Name": "Jhon Kevin T. Dimabasa", "ID#": "2023130558", "Year": "2", "Age": "20"},
    {"Name": "Richard Lance C. Rodrigo", "ID#": "2025180203", "Year": "2", "Age": "20"},
    {"Name": "Kian Carl L. Canapi", "ID#": "2025109353", "Year": "2", "Age": "19"},
    {"Name": "Janina Erika S. Alday", "ID#": "2024180062", "Year": "3", "Age": "23"},
    {"Name": "Jose Elias R. Encarnado", "ID#": "2022106627", "Year": "3", "Age": "22"},
    {"Name": "Emmanuel Deus C. Abad", "ID#": "2024109219", "Year": "3", "Age": "20"},
    {"Name": "Rhanz Reicko P. Pilpa", "ID#": "2024109071", "Year": "3", "Age": "21"},
    {"Name": "Kayryll A. Guinto", "ID#": "2024100840", "Year": "3", "Age": "21"},
    {"Name": "Julienne Marie D. Flores", "ID#": "2024180189", "Year": "3", "Age": "21"}
]

# --- State Management ---
if "active_page" not in st.session_state:
    st.session_state.active_page = "Roster"

if "selected_student_id" not in st.session_state:
    st.session_state.selected_student_id = "2023130130"

# Navigation Bar Tabs
nav_col1, nav_col2, nav_col3, nav_col4 = st.columns(4)
with nav_col1:
    if st.button("Overview", use_container_width=True, type="secondary"):
        st.session_state.active_page = "Overview"
        st.rerun()
with nav_col2:
    if st.button("Roster", use_container_width=True, type="primary" if st.session_state_page == "Roster" else "secondary"):
        st.session_state.active_page = "Roster"
        st.rerun()
with nav_col3:
    if st.button("Student Profile", use_container_width=True, type="primary" if st.session_state.active_page == "Student Profile" else "Secondary"):
        st.session_state.active_page = "Student Profile"
        st.rerun()
with nav_col4:
    if st.button("Admin Config", use_container_width=True, type="secondary"):
        st.session_state.active_page = "Admin Config"
        st.rerun()

st.markdown("---")

# =========================================================
# PAGE 1: STUDENT ROSTER (One-Click Routing to Profile)
# =========================================================
if st.session_state.active_page == "Roster":
    st.markdown("### MBA Student Roster (12 students)")
    st.caption("Click any student name to navigate directly to their individual profile:")

    # Header row
    h_student, h_cohort, h_pillars = st.columns([3, 1.5, 2])
    h_student.markdown("**STUDENT**")
    h_cohort.markdown("**COHORT**")
    h_pillars.markdown("**RISK STATUS**")
    st.markdown("---")

    # Interactive Student Rows
    for s in ROSTER_DATA:
        r_student, r_cohort, r_pillars = st.columns([3, 1.5, 2])

        with r_student:
            # Accessible one-click route button
            btn_label = f"{s['name']} ({s['student_id']})"
            if st.button(btn_label, key=f"nav_{s['student_id']}", use_container_width=True):
                st.session_state.selected_student_id = s["student_id"]
                st.session_state.active_page = "Student Profile"
                st.rerun()

        with r_cohort:
            st.write(s["cohort"])

        with r_pillars:
            st.markdown('<span class="status-completed">CW: Done</span> <span class="status-inprogress">CE: Prog</span> <span class="status-inprogress">CP: Prog</span>', unsafe_allow_html=True)

  
# =========================================================
# PAGE 2: INDIVIDUAL STUDENT PROFILE (All 3 Pillars in 1 View)
# =========================================================
elif st.session_state.active_page == "Student Profile":
    student = next((s for s in ROSTER_DATA if s["student_id"] == st.session_state.selected_student_id), ROSTER_DATA[0])

    # Header Card
    p_header, p_back = st.columns([5, 1])
    with p_header:
        st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 12px;">
                <div class="avatar-circle">{student['initials']}</div>
                <div>
                    <h2 style="margin: 0;">{student['name']} <small style="color: gray; font-size: 14px;">{student['student_id']}</small></h2>
                    <small>Cohort: <b>{student['cohort']}</b> | Assigned Advisor: <b>{student['advisor']}</b> &nbsp; {f'<span class="risk-badge">{student["risk"]}</span>' if student['risk'] else ''}</small>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with p_back:
        if st.button("Back to Roster", use_container_width=True):
            st.session_state.active_page = "Roster"
            st.rerun()

    st.markdown("### Program Lifecycle Status")

    # Query timestamps without altering/updating schemas
    pillar_info = get_latest_pillar_data(student["student_id"])

    # Three-Pillar Consolidated View
    c_cw, c_ce, c_cp = st.columns(3)

    # 1. Coursework
    with c_cw:
        with st.container(border=True):
            st.markdown("**CW &nbsp; Coursework**")
            cw_data = pillar_info["Coursework"]
            st.markdown(f'<span class="status-completed">{cw_data["status"]}</span>', unsafe_allow_html=True)
            st.caption(f"Last updated: {cw_data['last_updated']}")

            new_status = st.selectbox("Update Status", ["Completed", "In-Progress", "Cancelled", "Pending"], key="cw_sel")
            if st.button("Record CW Stamp", key="btn_cw"):
                record_timestamp_log(student["student_id"], "Coursework", new_status)
                st.rerun()

    # 2. Comprehensive Exam
    with c_ce:
        with st.container(border=True):
            st.markdown("**CE &nbsp; Comprehensive Exam**")
            ce_data = pillar_info["Comprehensive Exam"]
            st.markdown(f'<span class="status-inprogress"')
            st.caption(f"Last updated: {ce_data['last_updated}']}")

            new_status_ce = st.selectbox("Update Status", ["In-Progress", "Passed", "Incomplete", "Pending"], key="ce_sel")
            if st.button("Record CE Stamp", key="btn_ce"):
                record_timestamp_log(student["student_id"], "Comprehensive Exam", new_status_ce)
                st.rerun()

    # 3. Capstone Paper
    with c_cp:
        with st.container(border=True):
            st.markdown("**CP &nbsp; Capstone Paper**")
            cp_data = pillar_info["Capstone Paper"]
            st.markdown(f'<span class="status-inprogress">{cp_data["status"]}</span>', unsafe_allow_html=True)
            st.caption(f"Last updated: {cp_data['last_updated']}")

            new_status_cp = st.selectbox("Update Status", ["In-Progress", "Defended for Completion", "Pending"], key="cp_sel")
            if st.button("Record CP Stamp", key="btn_cp"):
                record_timestamp_log(student["student_id"], "Capstone Paper", new_status_cp)
                st.rerun()
import streamlit as st
import pandas as pd
from db_connect import get_student_roster_data
from dashboard_views.components import (
    DARK_MODE_CSS, 
    render_status_pill, 
    calculate_risk_status
)

st.set_page_config(page_title="Student Profile", layout="wide")

# Inject unified dark mode styling
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

# Defensive session check
if not st.session_state.get("logged_in") and not st.session_state.get("user"):
    st.warning("Please log in to view student profile.")
    st.stop()

st.title("Student Profile")
st.markdown("---")

df = get_student_roster_data()

if not df.empty:
    student_options = {
        f"{row['StudentNumber']} - {row['Student']}": str(row['StudentNumber'])
        for _, row in df.iterrows()
    }

    student_ids = list(student_options.values())
    default_index = 0

    # 1. Check query parameter navigation from Student Roster (student_profile?student_id=...)
    target_student_id = st.query_params.get("student_id") or st.session_state.get("selected_student_override")
    if target_student_id:
        target_str = str(target_student_id).strip()
        if target_str in student_ids:
            default_index = student_ids.index(target_str)
        if "selected_student_override" in st.session_state:
            del st.session_state["selected_student_override"]

    # Student Selector Dropdown
    selected_label = st.selectbox(
        "SELECT STUDENT:",
        list(student_options.keys()),
        index=default_index
    )

    if selected_label:
        selected_id = student_options[selected_label]
        student = df[df["StudentNumber"].astype(str) == selected_id].iloc[0]

        student_name = student.get("Student", "Unknown")
        student_num = student.get("StudentNumber", selected_id)
        cohort = student.get("Cohort", "N/A")
        enrollment_status = student.get("EnrollmentStatus", "N/A")
        advisor = student.get("Advisor", "None Assigned")

        current_cw = student.get("CourseworkStatus", "Pending")
        current_ce = student.get("CompExamStatus", "In-Progress")
        current_cp = student.get("CapstoneStatus", "In-Progress")

        overall_risk = calculate_risk_status(current_cw, current_ce, current_cp)

        enrollment_pill = render_status_pill(enrollment_status)
        risk_pill = render_status_pill(overall_risk)

        # ----------------- Student Metadata Header Card -----------------
        header_markup = (
            '<div class="profile-meta-card">'
            '<div style="display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;">'
            f'<h2 class="profile-name">{student_name}</h2>'
            f'<span class="profile-id-badge">{student_num}</span>'
            '</div>'
            '<div class="profile-meta-row">'
            '<div class="meta-field">'
            '<span>Cohort:</span>'
            f'<strong>{cohort}</strong>'
            '</div>'
            '<div class="meta-field">'
            '<span>Enrollment Status:</span>'
            f'{enrollment_pill}'
            '</div>'
            '<div class="meta-field">'
            '<span>Assigned Advisor:</span>'
            f'<strong>{advisor}</strong>'
            '</div>'
            '<div class="meta-field">'
            '<span>Overall Risk:</span>'
            f'{risk_pill}'
            '</div>'
            '</div>'
            '</div>'
        )
        st.markdown(header_markup, unsafe_allow_html=True)

        # ----------------- Lifecycle Status Cards -----------------
        st.markdown("<h3 class='section-title'>Program Lifecycle Status</h3>", unsafe_allow_html=True)

        cw_pill = render_status_pill(current_cw)
        ce_pill = render_status_pill(current_ce)
        cp_pill = render_status_pill(current_cp)

        lifecycle_markup = (
            '<div class="lifecycle-cards-container">'
            '<div class="lifecycle-card">'
            '<div class="lifecycle-card-title">Coursework</div>'
            f'{cw_pill}'
            '</div>'
            '<div class="lifecycle-card">'
            '<div class="lifecycle-card-title">Comprehensive Exam</div>'
            f'{ce_pill}'
            '</div>'
            '<div class="lifecycle-card">'
            '<div class="lifecycle-card-title">Capstone Paper</div>'
            f'{cp_pill}'
            '</div>'
            '</div>'
        )
        st.markdown(lifecycle_markup, unsafe_allow_html=True)

else:
    st.info("No student records available. Please ensure database connection is established.")

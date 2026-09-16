import streamlit as st
from db_connect import get_student_roster_data

st.set_page_config(page_title="Student Profile", layout="wide")

st.title("Student Profile")
st.markdown("---")

current_user = st.session_state.get("user", {})
user_role = current_user.get("role", "")
df = get_student_roster_data()

if not df.empty:
    student_options = {
        f"{row['StudentNumber']} - {row['Student']}": row['StudentNumber']
        for _, row in df.iterrows()
    }

    student_ids = list(student_options.values())
    default_index = 0

    if "selected_student_override" in st.session_state:
        target_id = st.session_state["selected_student_override"]
        if target_id in student_ids:
            default_index = student_ids.index(target_id)
        # Clear the override so manual selections work normally afterwards
        del st.session_state["selected_student_override"]

    selected_label = st.selectbox("Select Student:", list(student_options.keys()), index=default_index)

    if selected_label:
        selected_id = student_options[selected_label]
        student = df[df["StudentNumber"] == selected_id].iloc[0]

        # Student Details Banner
        st.subheader(f"{student['Student']} (`{student['StudentNumber']}`)")
        st.write(
            f"**Cohort:** {student.get('Cohort', 'N/A')} | "
            f"**Enrollment Status:** {student.get('EnrollmentStatus', 'N/A')} | "
            f"**Assigned Advisor:** {student.get('Advisor', 'None Assigned')}"
        )

        st.markdown("### Program Lifecycle Status")
        col_cw, col_ce, col_cp = st.columns(3)

        current_cw = student.get("CourseworkStatus", "Pending")
        current_ce = student.get("CompExamStatus", "In-Progress")
        current_cp = student.get("CapstoneStatus", "In-Progress")

        with col_cw:
            st.info(f"**Coursework**\n\n### {current_cw}")

        with col_ce:
            st.info(f"**Comprehensive Exam**\n\n### {current_ce}")

        with col_cp:
            st.info(f"**Capstone Paper**\n\n### {current_cp}")

else:
    st.info("No student records available. Please ensure database connection is established.")
import streamlit as st
from db_connect import get_student_roster_data

st.set_page_config(page_title="Student Profile", layout="wide")

st.title("Student Profile")
st.markdown("---")

df = get_student_roster_data()

if not df.empty:
    student_options = {
        f"{row['StudentNumber']} - {row['Student']}": row['StudentNumber']
        for _, row in df.iterrows()
    }

    selected_label = st.selectbox("Select Student:", list(student_options.keys()))

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

        with col_cw:
            cw_status = student.get("CourseworkStatus", "Pending")
            st.info(f"**Coursework**\n\n### {cw_status}")

        with col_ce:
            # US-08: Comprehensive Exam Pillar
            ce_status = student.get("CompExamStatus", "In-Progress")
            st.info(f"**Comprehensive Exam**\n\n### {ce_status}")

        with col_cp:
            cp_status = student.get("CapstoneStatus", "In-Progress")
            st.info(f"**Capstone Paper**\n\n### {cp_status}")

else:
    st.info("No student records available. Please ensure database connection is established.")
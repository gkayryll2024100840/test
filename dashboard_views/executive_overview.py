import streamlit as st
from db_connect import get_enrollment_count

st.write("DEBUG — executive_overview is running") #DEBUGGING ONLY WILL DELETE
st.write("DEBUG — user:", st.session_state.get('user')) #DEBUGGING ONLY WILL DELETE

st.set_page_config(page_title="Executive Overview", layout="wide")

st.title("Executive Overview — MBA Program")
st.markdown("### Headcount Summary")

#Filter dropdown for enrollment status
status_options = ["All", "Enrolled", "Conditionally Enrolled"]
selected_status = st.selectbox("FILTER BY ENROLLMENT STATUS:", status_options)

#Fetch live count automatically from database based on selection
total_headcount = get_enrollment_count(selected_status)

#Display Metric Card
st.metric(
    label=f"Total MBA Headcount ({selected_status} Status)",
    value=total_headcount
)

st.caption("Count updates automatically from the live database. Visible on landing view.")
import streamlit as st
from db_connect import get_enrollment_count
from dashboard_views.components import DARK_MODE_CSS

st.set_page_config(page_title="Executive Overview", layout="wide")

# Inject unified dark mode styling
st.markdown(DARK_MODE_CSS, unsafe_allow_html=True)

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
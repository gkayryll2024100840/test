import json
import os
import streamlit as st
from db_connect import get_system_logs, trigger_data_sync, check_column_exists
from system_log import get_system_logs_local
from field_mapping import load_mappings, save_mappings

# get_system_logs(): pull history from local_logs.db
# trigger_data_sync: to test the connection to MySQL

# st: customize browser's tabs title and layout
st.title("Admin Configuration")
st.markdown("---")

# ============================================================
# FIELD MAPPING CONFIGURATION SECTION 
# ============================================================
CONFIG_FILE = "field_mappings.json"

st.subheader("Field Mapping (US-10)")
st.markdown("Maps dashboard fields to IFT200's normalized schema — no code changes required to repoint for a new program.")

# Load current configuration into session state if not already present
if "current_mappings" not in st.session_state:
    st.session_state["current_mappings"] = load_mappings()

updated_mappings = {}
validation_errors = []

# Render editable mapping rows
for field_label, db_column in st.session_state["current_mappings"].items():
    col1, col2, col3 = st.columns([3, 5, 2])

    with col1:
        st.write(f"**{field_label}**")

    with col2:
        new_column = st.text_input(
            f"Column for {field_label}",
            value=db_column,
            label_visibility="collapsed",
            key=f"input_{field_label}",
        )
        updated_mappings[field_label] = new_column.strip()

    with col3:
        typed_path = new_column.strip()
        column_exists = check_column_exists(typed_path) if typed_path else False

        toggle_key = f"toggle_{field_label}"

        st.session_state[toggle_key] = column_exists

        is_active = st.toggle(
            "Mapped",
            key=toggle_key,
            disabled=True
        )

        if not is_active or not column_exists:
            validation_errors.append(field_label)

st.markdown("---")

# Action Buttons
col_save, col_status = st.columns([1, 3])

with col_save:
    if st.button("Save Mappings", type="primary"):
        if validation_errors:
            st.error(
                f"Cannot save. Missing mapping for: {', '.join(validation_errors)}"
            )
        else:
            save_mappings(updated_mappings)
            st.session_state["current_mappings"] = updated_mappings
            st.success("Configurations successfully saved!")
            st.rerun()

with col_status:
    if validation_errors:
        st.warning(
            "Configuration has errors and cannot go live until resolved.",
        )
    else:
        st.success("All mappings valid and ready for production deployment.")

# ============================================================
# SYSTEM SYNC LOGS SECTION 
# ============================================================
st.markdown("---")
st.subheader("System Sync Logs")

active_login_id = st.session_state.get("session_id", "default_admin")
st.info(f"Active Session ID for this browser: **{active_login_id}**")

if st.button("Run Sync Attempt"):
    # tries connecting to local_log.db
    success = trigger_data_sync(login_id=active_login_id)
    if success:
        st.success("Sync executed successfully!")
        st.rerun()
    else:
        st.error("Sync failed! Error logged to SQL Local_Logs table.")
        st.rerun()

logs = get_system_logs_local()

# displays your logs on the admin screen using Streamlit
if logs:
    st.dataframe(logs, use_container_width=True)
else:
    st.info("No system logs found in the local_logs.db")

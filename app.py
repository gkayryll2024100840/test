import os
import pymysql
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Load secret credentials from local .env
load_dotenv()

st.title("Project PULSE Dashboard")
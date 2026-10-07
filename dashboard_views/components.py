# COMPONENTS.PY (speed-optimized: header repaints in place instead of rerunning the page)
# Added mobile view
"""
Unified reusable UI components and styles for Student Roster and Student Profile.
Responsive dual-theme (Light & Dark mode) enterprise styling with accessible contrast steps
and no AI/SaaS anti-patterns.
"""
import base64
import html
import os
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from db_connect import (
    get_all_programs,
    get_available_cohorts,
    get_db_connection,
    get_last_updated_time,
    get_user_permission,
    get_user_program,
    get_refresh_schedule,
    trigger_data_sync,
)


def get_current_theme() -> str:
    """Returns 'light' or 'dark' based on Streamlit's context, defaulting to 'auto'."""
    try:
        if hasattr(st, "context") and hasattr(st.context, "theme"):
            theme_type = getattr(st.context.theme, "type", None)
            if theme_type in ["light", "dark"]:
                return theme_type
    except Exception:
        pass
    return "auto"


def get_theme_css() -> str:
    """Generates dynamic, responsive CSS supporting both Light Mode and Dark Mode."""
    # The theme is detected IN THE BROWSER (see THEME_DETECTOR_JS). Reading it here with
    # st.context.theme only updated on the next page load, which caused the stale-colour bug.
    current_theme = None

    explicit_override = ""
    if current_theme == "dark":
        explicit_override = """
/* Explicit Streamlit Dark Mode Override */
.stApp {
    --app-bg: #0B0F17 !important;
    --app-text: #F1F5F9 !important;
    --card-bg: #161D2B !important;
    --card-border: #263044 !important;
    --card-shadow: none !important;
    --text-primary: #F1F5F9 !important;
    --text-secondary: #94A3B8 !important;
    --text-body: #CBD5E1 !important;
    --text-muted: #64748B !important;
    --id-badge-bg: #0F172A !important;
    --id-badge-border: #263044 !important;
    --id-badge-text: #94A3B8 !important;
    --metric-val-color: #F1F5F9 !important;
    --metric-lbl-color: #94A3B8 !important;
    --input-bg: #0F172A !important;
    --input-border: #263044 !important;
    --input-text: #F1F5F9 !important;
    --input-focus-border: #3B82F6 !important;
    --btn-bg: #161D2B !important;
    --btn-border: #263044 !important;
    --btn-text: #F1F5F9 !important;
    --btn-hover-bg: #1E293B !important;
    --btn-hover-border: #3B82F6 !important;
    --btn-hover-text: #FFFFFF !important;
    --roster-th-color: #94A3B8 !important;
    --roster-th-border: #263044 !important;
    --roster-row-border: #1E293B !important;
    --roster-cell-id: #94A3B8 !important;
    --roster-cell-text: #CBD5E1 !important;
    --roster-link-color: #60A5FA !important;
    --roster-link-hover: #93C5FD !important;
    --pill-success-bg: rgba(16, 185, 129, 0.15) !important;
    --pill-success-border: rgba(16, 185, 129, 0.3) !important;
    --pill-success-text: #34D399 !important;
    --pill-danger-bg: rgba(239, 68, 68, 0.14) !important;
    --pill-danger-border: rgba(239, 68, 68, 0.3) !important;
    --pill-danger-text: #FCA5A5 !important;
    --pill-active-bg: rgba(245, 158, 11, 0.14) !important;
    --pill-active-border: rgba(245, 158, 11, 0.3) !important;
    --pill-active-text: #FCD34D !important;
    --pill-warning-bg: rgba(245, 158, 11, 0.14) !important;
    --pill-warning-border: rgba(245, 158, 11, 0.3) !important;
    --pill-warning-text: #FCD34D !important;
    --pill-neutral-bg: rgba(148, 163, 184, 0.12) !important;
    --pill-neutral-border: rgba(148, 163, 184, 0.24) !important;
    --pill-neutral-text: #CBD5E1 !important;
    
    /* Lifecycle Status Cards (Matched to Profile Card) */
    --lifecycle-card-bg: #161D2B !important;
    --lifecycle-card-border: #263044 !important;
    --lifecycle-card-title: #F1F5F9 !important;
    --lifecycle-pill-success-bg: #16433C !important;
    --lifecycle-pill-success-border: rgba(52, 211, 153, 0.35) !important;
    --lifecycle-pill-success-text: #34D399 !important;
    --lifecycle-pill-danger-bg: #451D24 !important;
    --lifecycle-pill-danger-border: rgba(248, 113, 113, 0.35) !important;
    --lifecycle-pill-danger-text: #FCA5A5 !important;
    --lifecycle-pill-active-bg: #422E15 !important;
    --lifecycle-pill-active-border: rgba(251, 191, 36, 0.35) !important;
    --lifecycle-pill-active-text: #FCD34D !important;
    --lifecycle-pill-warning-bg: #422E15 !important;
    --lifecycle-pill-warning-border: rgba(251, 191, 36, 0.35) !important;
    --lifecycle-pill-warning-text: #FCD34D !important;
    --lifecycle-pill-neutral-bg: #1E293B !important;
    --lifecycle-pill-neutral-border: rgba(148, 163, 184, 0.3) !important;
    --lifecycle-pill-neutral-text: #CBD5E1 !important;
    background-color: #0B0F17 !important;
    color: #F1F5F9 !important;
}
"""
    elif current_theme == "light":
        explicit_override = """
/* Explicit Streamlit Light Mode Override */
.stApp {
    --app-bg: #FFFFFF !important;
    --app-text: #0F172A !important;
    --card-bg: #FFFFFF !important;
    --card-border: #E2E8F0 !important;
    --card-shadow: 0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.03) !important;
    --text-primary: #0F172A !important;
    --text-secondary: #64748B !important;
    --text-body: #334155 !important;
    --text-muted: #94A3B8 !important;
    --id-badge-bg: #F1F5F9 !important;
    --id-badge-border: #E2E8F0 !important;
    --id-badge-text: #475569 !important;
    --metric-val-color: #0F172A !important;
    --metric-lbl-color: #64748B !important;
    --input-bg: #FFFFFF !important;
    --input-border: #CBD5E1 !important;
    --input-text: #0F172A !important;
    --input-focus-border: #2563EB !important;
    --btn-bg: #FFFFFF !important;
    --btn-border: #CBD5E1 !important;
    --btn-text: #0F172A !important;
    --btn-hover-bg: #F8FAFC !important;
    --btn-hover-border: #2563EB !important;
    --btn-hover-text: #0F172A !important;
    --roster-th-color: #64748B !important;
    --roster-th-border: #E2E8F0 !important;
    --roster-row-border: #F1F5F9 !important;
    --roster-cell-id: #64748B !important;
    --roster-cell-text: #334155 !important;
    --roster-link-color: #2563EB !important;
    --roster-link-hover: #1D4ED8 !important;
    --pill-success-bg: #D4F8D3 !important;
    --pill-success-border: #B8F3B7 !important;
    --pill-success-text: #0E6251 !important;
    --pill-danger-bg: #FDE8E8 !important;
    --pill-danger-border: #FCD4D4 !important;
    --pill-danger-text: #9C0006 !important;
    --pill-active-bg: #FEF3C7 !important;
    --pill-active-border: #FDE68A !important;
    --pill-active-text: #92400E !important;
    --pill-warning-bg: #FEF3C7 !important;
    --pill-warning-border: #FDE68A !important;
    --pill-warning-text: #92400E !important;
    --pill-neutral-bg: #F1F5F9 !important;
    --pill-neutral-border: #E2E8F0 !important;
    --pill-neutral-text: #475569 !important;
    
    /* Lifecycle Status Cards (Light Mode) */
    --lifecycle-card-bg: #F8FAFC !important;
    --lifecycle-card-border: #E2E8F0 !important;
    --lifecycle-card-title: #0F172A !important;
    --lifecycle-pill-success-bg: #D4F8D3 !important;
    --lifecycle-pill-success-border: #B8F3B7 !important;
    --lifecycle-pill-success-text: #0E6251 !important;
    --lifecycle-pill-danger-bg: #FDE8E8 !important;
    --lifecycle-pill-danger-border: #FCD4D4 !important;
    --lifecycle-pill-danger-text: #9C0006 !important;
    --lifecycle-pill-active-bg: #FEF3C7 !important;
    --lifecycle-pill-active-border: #FDE68A !important;
    --lifecycle-pill-active-text: #92400E !important;
    --lifecycle-pill-warning-bg: #FEF3C7 !important;
    --lifecycle-pill-warning-border: #FDE68A !important;
    --lifecycle-pill-warning-text: #92400E !important;
    --lifecycle-pill-neutral-bg: #F1F5F9 !important;
    --lifecycle-pill-neutral-border: #E2E8F0 !important;
    --lifecycle-pill-neutral-text: #475569 !important;
    background-color: #FFFFFF !important;
    color: #0F172A !important;
}
"""

    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

/* ============================================================
   DUAL-THEME ENTERPRISE STYLING (LIGHT & DARK MODE)
   ============================================================ */

/* Base Variables: Clean, high-contrast Light Mode default */
:root, .stApp {{
    --app-bg: #FFFFFF;
    --app-text: #0F172A;
    --card-bg: #FFFFFF;
    --card-border: #E2E8F0;
    --card-radius: 14px;
    --card-shadow: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
    --card-shadow-hover: 0 10px 25px -4px rgba(15, 23, 42, 0.08), 0 4px 10px -2px rgba(15, 23, 42, 0.04);
    
    --text-primary: #0F172A;
    --text-secondary: #64748B;
    --text-body: #334155;
    --text-muted: #94A3B8;
    
    --id-badge-bg: #F1F5F9;
    --id-badge-border: #E2E8F0;
    --id-badge-text: #475569;
    
    --metric-val-color: #0F172A;
    --metric-lbl-color: #64748B;
    
    --input-bg: #FFFFFF;
    --input-border: #CBD5E1;
    --input-text: #0F172A;
    --input-focus-border: #2563EB;
    
    --btn-bg: #FFFFFF;
    --btn-border: #CBD5E1;
    --btn-text: #0F172A;
    --btn-hover-bg: #F8FAFC;
    --btn-hover-border: #2563EB;
    --btn-hover-text: #0F172A;
    
    --roster-th-color: #64748B;
    --roster-th-border: #E2E8F0;
    --roster-row-border: #F1F5F9;
    --roster-cell-id: #64748B;
    --roster-cell-text: #334155;
    --roster-link-color: #2563EB;
    --roster-link-hover: #1D4ED8;
    
    /* Light Mode Status Pills - Reference Spec */
    --pill-success-bg: #D4F8D3;
    --pill-success-border: #B8F3B7;
    --pill-success-text: #0E6251;
    
    --pill-danger-bg: #FDE8E8;
    --pill-danger-border: #FCD4D4;
    --pill-danger-text: #9C0006;
    
    --pill-active-bg: #FEF3C7;
    --pill-active-border: #FDE68A;
    --pill-active-text: #92400E;
    
    --pill-warning-bg: #FEF3C7;
    --pill-warning-border: #FDE68A;
    --pill-warning-text: #92400E;
    
    --pill-neutral-bg: #F1F5F9;
    --pill-neutral-border: #E2E8F0;
    --pill-neutral-text: #475569;
    
    /* Lifecycle Status Cards (Light Mode) */
    --lifecycle-card-bg: #F8FAFC;
    --lifecycle-card-border: #E2E8F0;
    --lifecycle-card-title: #0F172A;
    --lifecycle-pill-success-bg: #D4F8D3;
    --lifecycle-pill-success-border: #B8F3B7;
    --lifecycle-pill-success-text: #0E6251;
    --lifecycle-pill-danger-bg: #FDE8E8;
    --lifecycle-pill-danger-border: #FCD4D4;
    --lifecycle-pill-danger-text: #9C0006;
    --lifecycle-pill-active-bg: #FEF3C7;
    --lifecycle-pill-active-border: #FDE68A;
    --lifecycle-pill-active-text: #92400E;
    --lifecycle-pill-warning-bg: #FEF3C7;
    --lifecycle-pill-warning-border: #FDE68A;
    --lifecycle-pill-warning-text: #92400E;
    --lifecycle-pill-neutral-bg: #F1F5F9;
    --lifecycle-pill-neutral-border: #E2E8F0;
    --lifecycle-pill-neutral-text: #475569;
}}

/* Dark mode: set by the theme detector when Streamlit's theme is dark */
html[data-eo-theme="dark"],
html[data-eo-theme="dark"] .stApp {{
    --app-bg: #0B0F17;
    --app-text: #F1F5F9;
    --card-bg: #161D2B;
    --card-border: #263044;
    --card-radius: 14px;
    --card-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.4), 0 2px 6px -1px rgba(0, 0, 0, 0.25);
    --card-shadow-hover: 0 8px 24px -2px rgba(0, 0, 0, 0.6), 0 4px 12px -2px rgba(0, 0, 0, 0.35);
    
    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
    --text-body: #CBD5E1;
    --text-muted: #64748B;
    
    --id-badge-bg: #0F172A;
    --id-badge-border: #263044;
    --id-badge-text: #94A3B8;
    
    --metric-val-color: #F1F5F9;
    --metric-lbl-color: #94A3B8;
    
    --input-bg: #0F172A;
    --input-border: #263044;
    --input-text: #F1F5F9;
    --input-focus-border: #3B82F6;
    
    --btn-bg: #161D2B;
    --btn-border: #263044;
    --btn-text: #F1F5F9;
    --btn-hover-bg: #1E293B;
    --btn-hover-border: #3B82F6;
    --btn-hover-text: #FFFFFF;
    
    --roster-th-color: #94A3B8;
    --roster-th-border: #263044;
    --roster-row-border: #1E293B;
    --roster-cell-id: #94A3B8;
    --roster-cell-text: #CBD5E1;
    --roster-link-color: #60A5FA;
    --roster-link-hover: #93C5FD;
    
    /* Dark Mode Status Pills */
    --pill-success-bg: rgba(16, 185, 129, 0.15);
    --pill-success-border: rgba(16, 185, 129, 0.3);
    --pill-success-text: #34D399;
    
    --pill-danger-bg: rgba(239, 68, 68, 0.14);
    --pill-danger-border: rgba(239, 68, 68, 0.3);
    --pill-danger-text: #FCA5A5;
    
    --pill-active-bg: rgba(245, 158, 11, 0.14);
    --pill-active-border: rgba(245, 158, 11, 0.3);
    --pill-active-text: #FCD34D;
    
    --pill-warning-bg: rgba(245, 158, 11, 0.14);
    --pill-warning-border: rgba(245, 158, 11, 0.3);
    --pill-warning-text: #FCD34D;
    
    --pill-neutral-bg: rgba(148, 163, 184, 0.12);
    --pill-neutral-border: rgba(148, 163, 184, 0.24);
    --pill-neutral-text: #CBD5E1;
    
    /* Lifecycle Status Cards (Matched to Profile Card) */
    --lifecycle-card-bg: #161D2B;
    --lifecycle-card-border: #263044;
    --lifecycle-card-title: #F1F5F9;
    --lifecycle-pill-success-bg: #16433C;
    --lifecycle-pill-success-border: rgba(52, 211, 153, 0.35);
    --lifecycle-pill-success-text: #34D399;
    --lifecycle-pill-danger-bg: #451D24;
    --lifecycle-pill-danger-border: rgba(248, 113, 113, 0.35);
    --lifecycle-pill-danger-text: #FCA5A5;
    --lifecycle-pill-active-bg: #422E15;
    --lifecycle-pill-active-border: rgba(251, 191, 36, 0.35);
    --lifecycle-pill-active-text: #FCD34D;
    --lifecycle-pill-warning-bg: #422E15;
    --lifecycle-pill-warning-border: rgba(251, 191, 36, 0.35);
    --lifecycle-pill-warning-text: #FCD34D;
    --lifecycle-pill-neutral-bg: #1E293B;
    --lifecycle-pill-neutral-border: rgba(148, 163, 184, 0.3);
    --lifecycle-pill-neutral-text: #CBD5E1;
}}

{explicit_override}

/* Surface base and text contrast */
.stApp {{
    color: var(--app-text);
}}

/* the invisible theme-detector iframe shouldn't take up space */
[data-testid="stElementContainer"]:has(iframe[height="0"]),
.element-container:has(iframe[height="0"]) {{
    display: none !important;
}}

/* Base typography for content elements without overriding icon fonts */
.stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp label,
.lifecycle-card, .profile-meta-card {{
    font-family: 'Plus Jakarta Sans', 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

/* Explicitly preserve Streamlit's Material Symbols Icon fonts */
[data-testid="stIconMaterial"], 
[data-testid*="Icon"], 
[class*="material-symbols"], 
[class*="material-icons"],
i.material-icons,
span[data-testid="stIconMaterial"],
div[data-testid="stSidebarCollapseButton"] span,
button[data-testid="stSidebarCollapseButton"] span {{
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons" !important;
}}

/* Metric / Card overrides */
div[data-testid="stMetricValue"] {{
    color: var(--metric-val-color) !important;
    font-size: 26px !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
    font-variant-numeric: tabular-nums !important;
}}

div[data-testid="stMetricLabel"] {{
    color: var(--metric-lbl-color) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}}

/* Form Inputs & Selectboxes */
.stSelectbox > div[data-baseweb="select"] > div,
.stTextInput > div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {{
    background-color: var(--input-bg) !important;
    border: 1px solid var(--input-border) !important;
    border-radius: 10px !important;
    min-height: 40px !important;
    color: var(--input-text) !important;
    transition: border-color 150ms ease, box-shadow 150ms ease !important;
}}

.stSelectbox > div[data-baseweb="select"] > div:focus-within,
.stTextInput > div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="input"] > div:focus-within {{
    border-color: var(--input-focus-border) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14) !important;
}}

/* Button overrides - modern enterprise styling with click feedback */
.stButton > button {{
    background-color: var(--btn-bg) !important;
    color: var(--btn-text) !important;
    border: 1px solid var(--btn-border) !important;
    border-radius: 10px !important;
    font-size: 12.5px !important;
    font-weight: 600 !important;
    padding: 7px 16px !important;
    transition: transform 120ms ease, box-shadow 150ms ease, background-color 150ms ease, border-color 150ms ease, color 150ms ease !important;
}}

.stButton > button:hover {{
    background-color: var(--btn-hover-bg) !important;
    border-color: var(--btn-hover-border) !important;
    color: var(--btn-hover-text) !important;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08) !important;
}}

.stButton > button:active {{
    transform: scale(0.98) !important;
}}

@media (hover: none) {{
    .stButton > button:hover {{
        box-shadow: none !important;
    }}
}}

/* Roster Table Grid Styling & Vertical Alignment (strictly scoped to the roster table) */
.st-key-roster_table div[data-testid="stHorizontalBlock"] {{
    align-items: center !important;
}}

.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}}

.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stElementContainer"],
.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stElementContainer"] {{
    margin-top: 0 !important;
    margin-bottom: 0 !important;
    display: flex !important;
    align-items: center !important;
    min-height: 32px !important;
}}

.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stMarkdownContainer"] {{
    display: flex !important;
    align-items: center !important;
    min-height: 32px !important;
    width: 100% !important;
}}

.st-key-roster_table div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stMarkdownContainer"] > p {{
    margin: 0 !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    min-height: 32px !important;
    line-height: 1 !important;
    width: 100% !important;
}}

.roster-th {{
    font-size: 11px;
    font-weight: 600;
    color: var(--roster-th-color);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0;
    margin: 0;
    line-height: 1;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    min-height: 24px;
}}

.roster-th-divider {{
    border-bottom: 2px solid var(--roster-th-border);
    margin-top: 6px;
    margin-bottom: 8px;
}}

.roster-row-divider {{
    border-bottom: 1px solid var(--roster-row-border);
    margin: 6px 0;
}}

div[data-testid="stMarkdownContainer"]:has(.roster-row-divider) > p,
div[data-testid="stMarkdownContainer"]:has(.roster-th-divider) > p {{
    margin: 0 !important;
    padding: 0 !important;
}}

.roster-cell-id {{
    font-family: monospace;
    color: var(--roster-cell-id);
    font-size: 12px;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    white-space: nowrap;
    min-height: 32px;
}}

.roster-cell-text {{
    color: var(--roster-cell-text);
    font-size: 13px;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    white-space: nowrap;
    min-height: 32px;
}}

/* Make st.page_link render as a crisp, clickable blue student name link perfectly vertically centered */
div[data-testid="stPageLink"] {{
    width: 100% !important;
    min-height: 32px !important;
    height: 32px !important;
    display: flex !important;
    align-items: center !important;
    margin: 0 !important;
    padding: 0 !important;
}}

div[data-testid="stPageLink"] a {{
    color: var(--roster-link-color) !important;
    text-decoration: none !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    line-height: 1 !important;
    min-height: 32px !important;
    display: inline-flex !important;
    align-items: center !important;
    transition: color 120ms ease !important;
}}

div[data-testid="stPageLink"] a span {{
    line-height: 1 !important;
    display: inline-flex !important;
    align-items: center !important;
}}

div[data-testid="stPageLink"] a:hover {{
    color: var(--roster-link-hover) !important;
    text-decoration: underline !important;
    background: transparent !important;
}}

div[data-testid="stPageLink"] a:focus {{
    box-shadow: none !important;
    outline: none !important;
}}

/* Student Profile Cards - Lifecycle Row & Cards */
.lifecycle-row,
.lifecycle-cards-container {{
    display: flex !important;
    flex-direction: row !important;
    gap: 16px !important;
    align-items: stretch !important;
    justify-content: flex-start !important;
    margin-top: 8px !important;
    margin-bottom: 24px !important;
    flex-wrap: wrap !important;
    width: 100% !important;
}}

.lifecycle-card {{
    min-width: 220px !important;
    width: auto !important;
    flex: 1 1 220px !important;
    box-sizing: border-box !important;
    background-color: var(--card-bg) !important;
    border: 1px solid var(--card-border) !important;
    box-shadow: var(--card-shadow) !important;
    border-radius: 14px !important;
    padding: 20px 24px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-start !important;
    justify-content: center !important;
    gap: 10px !important;
    transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1) !important;
}}

.lifecycle-card:hover {{
    transform: translateY(-2px);
    box-shadow: var(--card-shadow-hover) !important;
}}

@media (hover: none) {{
    .lifecycle-card:hover {{
        transform: none !important;
    }}
}}

.lifecycle-card-title {{
    font-size: 13px !important;
    font-weight: 500 !important;
    color: var(--text-secondary) !important;
    letter-spacing: 0.02em !important;
    white-space: nowrap !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.2 !important;
}}

.lifecycle-card .status-pill {{
    height: 26px !important;
    min-height: 26px !important;
    padding: 0 12px !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    border-radius: 9999px !important;
    line-height: 1 !important;
    letter-spacing: 0.015em !important;
    width: fit-content !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
}}

.lifecycle-card .status-pill.pill-success {{
    background-color: var(--lifecycle-pill-success-bg, #16433C) !important;
    border: 1px solid var(--lifecycle-pill-success-border, rgba(52, 211, 153, 0.35)) !important;
    color: var(--lifecycle-pill-success-text, #34D399) !important;
}}

.lifecycle-card .status-pill.pill-danger {{
    background-color: var(--lifecycle-pill-danger-bg, #451D24) !important;
    border: 1px solid var(--lifecycle-pill-danger-border, rgba(248, 113, 113, 0.35)) !important;
    color: var(--lifecycle-pill-danger-text, #FCA5A5) !important;
}}

.lifecycle-card .status-pill.pill-active {{
    background-color: var(--lifecycle-pill-active-bg, #422E15) !important;
    border: 1px solid var(--lifecycle-pill-active-border, rgba(251, 191, 36, 0.35)) !important;
    color: var(--lifecycle-pill-active-text, #FCD34D) !important;
}}

.lifecycle-card .status-pill.pill-warning {{
    background-color: var(--lifecycle-pill-warning-bg, #422E15) !important;
    border: 1px solid var(--lifecycle-pill-warning-border, rgba(251, 191, 36, 0.35)) !important;
    color: var(--lifecycle-pill-warning-text, #FCD34D) !important;
}}

.lifecycle-card .status-pill.pill-neutral {{
    background-color: var(--lifecycle-pill-neutral-bg, #1E293B) !important;
    border: 1px solid var(--lifecycle-pill-neutral-border, rgba(148, 163, 184, 0.3)) !important;
    color: var(--lifecycle-pill-neutral-text, #CBD5E1) !important;
}}

.profile-meta-card {{
    background-color: var(--card-bg);
    border: 1px solid var(--card-border);
    box-shadow: var(--card-shadow);
    border-radius: 14px;
    padding: 20px 24px;
    margin-bottom: 24px;
    transition: box-shadow 200ms ease;
}}

.profile-name {{
    margin: 0;
    color: var(--text-primary);
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.015em;
}}

.profile-id-badge {{
    font-family: monospace;
    font-size: 13px;
    color: var(--id-badge-text);
    background: var(--id-badge-bg);
    border: 1px solid var(--id-badge-border);
    padding: 2px 8px;
    border-radius: 6px;
}}

.profile-meta-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 24px;
    margin-top: 12px;
}}

.meta-field {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
}}

.meta-field strong {{
    color: var(--text-primary);
    font-weight: 500;
}}

.section-title,
h3.section-title,
div[data-testid="stMarkdownContainer"] h3.section-title {{
    font-size: 20px !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.015em !important;
    margin-top: 24px !important;
    margin-bottom: 14px !important;
    line-height: 1.3 !important;
}}

/* Unified Status Pill Styles */
.status-pill {{
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    height: 26px !important;
    min-height: 26px !important;
    padding: 0 12px !important;
    border-radius: 9999px !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    letter-spacing: 0.015em !important;
    line-height: 1 !important;
    white-space: nowrap !important;
    word-break: keep-all !important;
    flex-wrap: nowrap !important;
    width: fit-content !important;
    box-sizing: border-box !important;
    transition: transform 150ms cubic-bezier(0.16, 1, 0.3, 1), filter 150ms ease !important;
}}
.status-pill * {{
    white-space: nowrap !important;
    word-break: keep-all !important;
}}
.status-pill:hover {{
    filter: brightness(1.06) !important;
}}
@media (hover: none) {{
    .status-pill:hover {{
        filter: none !important;
    }}
}}

.pill-success {{
    background-color: var(--pill-success-bg);
    border: 1px solid var(--pill-success-border);
    color: var(--pill-success-text);
}}

.pill-danger {{
    background-color: var(--pill-danger-bg);
    border: 1px solid var(--pill-danger-border);
    color: var(--pill-danger-text);
}}

.pill-active {{
    background-color: var(--pill-active-bg);
    border: 1px solid var(--pill-active-border);
    color: var(--pill-active-text);
}}

.pill-warning {{
    background-color: var(--pill-warning-bg);
    border: 1px solid var(--pill-warning-border);
    color: var(--pill-warning-text);
}}

.pill-neutral {{
    background-color: var(--pill-neutral-bg);
    border: 1px solid var(--pill-neutral-border);
    color: var(--pill-neutral-text);
}}
</style>"""


THEME_DETECTOR_JS = """
<script>
(function () {
  var d = window.parent.document;
  if (d.getElementById("eo-theme-detector")) return;          // already running in this tab
  var s = d.createElement("script");
  s.id = "eo-theme-detector";
  s.textContent = "(" + function () {
    function rgb(c) {
      var m = (c || "").match(/[\\d.]+/g);
      if (!m || m.length < 3) return null;
      if (m.length > 3 && parseFloat(m[3]) === 0) return null; // transparent
      return [+m[0], +m[1], +m[2]];
    }
    function detect() {
      var els = [document.querySelector('[data-testid="stApp"]'), document.querySelector(".stApp"),
                 document.querySelector('[data-testid="stAppViewContainer"]'), document.body];
      for (var i = 0; i < els.length; i++) {
        if (!els[i]) continue;
        var c = rgb(getComputedStyle(els[i]).backgroundColor);
        if (c) return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255 < 0.5 ? "dark" : "light";
      }
      return "light";
    }
    function apply() {
      var t = detect(), h = document.documentElement;
      if (h.getAttribute("data-eo-theme") !== t) h.setAttribute("data-eo-theme", t);
      // phones: the red header scrolls away there, so tag the page while it is out of view
      // (CSS then hides Deploy / the menu instead of leaving them floating over the content)
      var red = document.querySelector(".ps-red");
      var gone = red && red.getBoundingClientRect().bottom <= 0 ? "1" : "0";
      if (h.getAttribute("data-ps-header-gone") !== gone) h.setAttribute("data-ps-header-gone", gone);
      // Student Roster: the rows scroll inside their own box, whose scrollbar makes them a bit narrower than
      // the header row. Share that scrollbar's width (it differs per OS) so the header can match the rows.
      var rows = document.querySelector(".st-key-roster_scroll");
      if (rows) {
        var sb = (rows.offsetWidth - rows.clientWidth) + "px";
        if (h.style.getPropertyValue("--sr-scrollbar") !== sb) h.style.setProperty("--sr-scrollbar", sb);
      }
      // Executive Overview, Students At Risk table: same idea (its rows scroll in their own box too)
      var eoRows = document.querySelector(".st-key-eo_table_rows");
      if (eoRows) {
        var esb = (eoRows.offsetWidth - eoRows.clientWidth) + "px";
        if (h.style.getPropertyValue("--eo-scrollbar") !== esb) h.style.setProperty("--eo-scrollbar", esb);
      }
    }
    apply();
    setInterval(apply, 250);                                   // follows theme switches instantly
  } + ")();";
  d.head.appendChild(s);
})();
</script>
"""


# Light mode by default, while keeping Light/Dark in the ⋮ menu > Settings.
# (Setting [theme] base="light" in config.toml would remove that menu choice.)
# Streamlit saves the menu choice in the browser as stActiveTheme-<page path>-v2 = "Light"/"Dark"/"System";
# with nothing saved it follows the computer's setting (and it remembers a menu choice forever).
#   - Every NEW TAB starts in "Light" (marker kept in sessionStorage, which is per tab), even if Dark
#     was picked in an earlier visit.
#   - Inside that tab, a choice the user makes in the menu is kept, also across reloads.
#   - Streamlit only reads the saved theme when the page first loads, so applying it needs a reload.
#     A reload starts a NEW Streamlit session (= logged out), so it is only allowed on the login page;
#     on dashboard pages the script just saves the value and never reloads.
LIGHT_DEFAULT_JS_TEMPLATE = """
<script>
(function () {
  try {
    var ALLOW_RELOAD = __ALLOW_RELOAD__;
    var w = window.parent, ls = w.localStorage, ss = w.sessionStorage;
    var key = "stActiveTheme-" + w.location.pathname + "-v2";
    var MARKER = "pp-light-default-applied";
    var LIGHT = '"Light"';
    var saved = [];
    for (var i = 0; i < ls.length; i++) {
      var k = ls.key(i);
      if (/^stActiveTheme-.*-v2$/.test(k)) saved.push(k);
    }
    var current = ls.getItem(key);
    ls.removeItem(MARKER);                                       // left over from the previous version

    if (ss.getItem(MARKER) === null) {                           // new tab: start in Light everywhere
      ss.setItem(MARKER, "1");
      saved.forEach(function (k) { ls.setItem(k, LIGHT); });
      ls.setItem(key, LIGHT);
      if (ALLOW_RELOAD && current !== LIGHT) w.location.reload();
      return;
    }
    if (current !== null) return;                                // the user's own choice for this page
    // a page address not seen yet in this tab: store the tab's current choice for it (no reload needed -
    // Streamlit keeps using the theme it loaded with while you move between pages)
    ls.setItem(key, saved.length ? ls.getItem(saved[0]) : LIGHT);
  } catch (e) {}                                                 // storage blocked: keep Streamlit's default
})();
</script>
"""
LIGHT_DEFAULT_JS = LIGHT_DEFAULT_JS_TEMPLATE.replace("__ALLOW_RELOAD__", "false")         # dashboard pages
LIGHT_DEFAULT_LOGIN_JS = LIGHT_DEFAULT_JS_TEMPLATE.replace("__ALLOW_RELOAD__", "true")    # login page only


def inject_light_default():
    """Login page: makes Light the starting theme of each new tab (Dark stays available in the ⋮ menu)."""
    try:
        import streamlit.components.v1 as components
        components.html(LIGHT_DEFAULT_LOGIN_JS, height=0)
    except Exception:
        pass


def inject_theme_detector():
    """Adds the (invisible) script that tags <html data-eo-theme="light|dark"> from Streamlit's theme."""
    try:
        import streamlit.components.v1 as components
        # the light-mode default rides in the same hidden iframe (a separate one added a gap above the header)
        components.html(THEME_DETECTOR_JS + LIGHT_DEFAULT_JS, height=0)
    except Exception:
        pass


class DynamicThemeCSS:
    """Dynamic theme string that evaluates to the appropriate CSS on demand,
    supporting both Light and Dark mode seamlessly."""

    def __str__(self) -> str:
        # st.markdown(DARK_MODE_CSS) calls this, so every page that loads the shared
        # styling also gets the theme detector, without editing each page.
        inject_theme_detector()
        return get_theme_css()

    def __repr__(self) -> str:
        return get_theme_css()


# Backward-compatible alias for existing imports
DARK_MODE_CSS = DynamicThemeCSS()
THEME_CSS = DARK_MODE_CSS


def render_status_pill(status) -> str:
    """Unified StatusPill component adhering to the dual-theme enterprise spec:
    - Standardized height: 26px (h-6.5)
    - display: inline-flex; align-items: center; justify-content: center;
    - Padding: 0 11px, border-radius: 9999px (rounded-full)
    - Single-line typography: 12px font-medium, leading-none, whitespace-nowrap
    - Semantic palette:
      * Success: Completed, Passed, Defended for Completion, On Track, Enrolled
      * Danger: Cancelled, Incomplete, At Risk, Failed
      * Active: In-Progress
      * Warning: Conditionally Enrolled, Pending
      * Neutral: default fallback
    """
    if status is None or (isinstance(status, float) and pd.isna(status)) or str(status).strip().lower() in ["nan", "none", ""]:
        status_str = "Pending"
    else:
        status_str = str(status).strip()

    status_lower = status_str.lower()

    # Success: soft green (light mode) / emerald neon (dark mode)
    if status_lower in ["completed", "passed", "defended for completion", "defended", "on track", "enrolled"]:
        pill_class = "pill-success"

    # Danger / At Risk / Incomplete / Cancelled: soft pink-red (light) / coral neon (dark)
    elif status_lower in ["cancelled", "canceled", "incomplete", "at risk", "high risk", "critical", "failed", "abs/failed"]:
        pill_class = "pill-danger"

    # Warning / Pending / In-Progress: soft amber (light) / warm amber neon (dark)
    elif status_lower in ["conditionally enrolled", "pending", "in-progress", "in progress"]:
        pill_class = "pill-warning"

    else:
        pill_class = "pill-neutral"

    return f'<span class="status-pill {pill_class}">{status_str}</span>'


def calculate_risk_status(coursework, comp_exam, capstone) -> str:
    """Calculates an overall risk indicator for a student based on their lifecycle pillars."""
    cw = str(coursework).strip().lower() if coursework and not pd.isna(coursework) else ""
    ce = str(comp_exam).strip().lower() if comp_exam and not pd.isna(comp_exam) else ""
    cp = str(capstone).strip().lower() if capstone and not pd.isna(capstone) else ""

    # Any pillar cancelled or incomplete marks the student as At Risk
    if cw in ["cancelled", "canceled", "failed"] or ce in ["incomplete", "failed"] or "fail" in cp:
        return "At Risk"

    # All pillars completed / passed / defended
    if (
        cw in ["completed"]
        and ce in ["passed"]
        and cp in ["defended for completion", "defended"]
    ):
        return "On Track"

    return "In-Progress"


# ===========================================================================
# APP HEADER + SIDEBAR (shown on every page; called from login.py before pg.run())
# ===========================================================================
SCHOOL_NAME = "E.T. Yuchengco School of Business"
UNIVERSITY_LINE = "Mapúa University · ASU Pathways"
APP_TITLE = "ETYSB Dashboard"
LOGO_FILES = ["assets/etysb_logo.png", "assets/etysb_logo.jpg", "assets/etysb_logo.jpeg",
              "assets/etysb_logo.webp", "assets/etysb_logo.svg"]   # put your logo in assets/ with one of these names
CURRENT_TERM_OVERRIDE = None          # e.g. "1Q2425" to pin the TERM shown in the yellow bar

ROLE_LABELS = {
    "Dean": "Dean",
    "IT/Admin": "IT/Admin",
    "Program_Chair": "Program Chair",
    "Faculty_Advisor": "Faculty Advisor",
    "Success_Advisor": "Success Advisor",
}


# ---------------------------------------------------------------------------
# DATA FOR THE HEADER / USER CARD (cached so page switches stay fast)
# ---------------------------------------------------------------------------
def _cohort_key(c):
    m = re.fullmatch(r"(\d)Q(\d{2})(\d{2})", str(c).strip().upper())
    return (2000 + int(m.group(2)), int(m.group(1))) if m else (0, 0)


@st.cache_data(ttl=300, show_spinner=False)
def _program_for_user(user_id):
    return get_user_program(user_id)


@st.cache_data(ttl=300, show_spinner=False)
def _current_term(program_id):
    if CURRENT_TERM_OVERRIDE:
        return CURRENT_TERM_OVERRIDE
    if program_id is not None:
        cohorts = get_available_cohorts(program_id)
    else:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT Cohort FROM Students WHERE Cohort IS NOT NULL")
            cohorts = [r[0] for r in cur.fetchall()]
            cur.close()
            conn.close()
        except Exception:
            cohorts = []
    return max(cohorts, key=_cohort_key) if cohorts else "—"


@st.cache_data(ttl=300, show_spinner=False)
def _all_programs():
    return get_all_programs(active_only=False)


@st.cache_data(ttl=60, show_spinner=False)
def _permission_for_user(user_id):
    return get_user_permission(user_id)


@st.cache_data(ttl=30, show_spinner=False)
def _last_sync_time():
    """Last successful sync (cached 30 s; Refresh Now / Run Sync Attempt clear it right away)."""
    return get_last_updated_time()


def _sync_label():
    raw = _last_sync_time()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{dt:%b %d, %Y} · {dt.hour % 12 or 12}:{dt:%M %p}"
        except (TypeError, ValueError):
            continue
    return raw or "—"


@st.cache_data(ttl=60, show_spinner=False)
def _refresh_time():
    """Nightly refresh time 'HH:MM' from Admin Configuration (cached 1 min)."""
    try:
        return get_refresh_schedule()["time"]
    except Exception:
        return "02:00"


def _next_refresh_label():
    """'Today · 2:00 AM' / 'Tomorrow · 2:00 AM' (Asia/Manila)."""
    now = datetime.now(timezone(timedelta(hours=8)))
    try:
        hh, mm = (int(x) for x in _refresh_time().split(":"))
    except Exception:
        hh, mm = 2, 0
    day = "Today" if (now.hour, now.minute) < (hh, mm) else "Tomorrow"
    return f"{day} · {hh % 12 or 12}:{mm:02d} {'AM' if hh < 12 else 'PM'}"


def _manual_refresh():
    """Sidebar "Refresh Now": runs a sync, then clears cached data so every page reloads fresh numbers.
    A failed sync is logged by trigger_data_sync() (US-16), same as the nightly one."""
    ok = trigger_data_sync(login_id=st.session_state.get("session_id"))
    st.cache_data.clear()
    st.session_state["_ps_refresh_msg"] = (ok, "Data refreshed." if ok else "Refresh failed. Check Admin logs.")


@st.cache_data(show_spinner=False)
def _logo_data_uri(path, mtime):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    mime = {"jpg": "jpeg", "svg": "svg+xml"}.get(ext, ext)
    with open(path, "rb") as f:
        return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode()}"


def _logo_html():
    for path in LOGO_FILES:
        if os.path.exists(path):
            return f'<img src="{_logo_data_uri(path, os.path.getmtime(path))}" alt="ETYSB logo">'
    return '<span class="ps-logo-text">ETYSB<br>logo</span>'


def _initials(user, role_label):
    first = str(user.get("firstname") or "").strip()
    last = str(user.get("lastname") or "").strip()
    if first or last:
        return ((first[:1] + last[:1]) or first[:2]).upper()
    words = [w for w in re.split(r"[\s_/]+", role_label) if w]
    return "".join(w[0] for w in words[:2]).upper() or "U"


# ---------------------------------------------------------------------------
# STYLES
# ---------------------------------------------------------------------------
SHELL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

/* Typography for App Shell, Sidebar, Navigation, and Headers */
.stApp,
[data-testid="stSidebar"],
[data-testid="stSidebar"] *,
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] *,
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p,
[data-testid="stSidebarHeader"],
[data-testid="stSidebarHeader"]::before,
[data-testid="stSidebarHeader"]::after,
.ps-header,
.ps-header * {
  font-family: 'Plus Jakarta Sans', 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Explicitly preserve Streamlit's Material Symbols and Icon fonts */
[data-testid="stSidebar"] [data-testid*="Icon"],
[data-testid="stSidebar"] [data-testid="stIconMaterial"],
[data-testid="stSidebar"] [class*="material-symbols"],
[data-testid="stSidebar"] [class*="material-icons"],
[data-testid="stSidebar"] i.material-icons,
[data-testid="stSidebarCollapseButton"] span,
button[data-testid="stSidebarCollapseButton"] span,
[data-testid*="Icon"],
[data-testid="stIconMaterial"],
span[data-testid="stIconMaterial"],
[class*="material-symbols"],
[class*="material-icons"],
i.material-icons {
  font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons" !important;
}

/* ---- colours (light, and dark when the theme detector marks the page dark) ---- */
.stApp{
  --ps-red:#B31B21; --ps-yellow:#F2E230; --ps-yellow-text:#1F2937;
  --ps-side-bg:#F3F4F6; --ps-side-border:#E5E7EB; --ps-card:#FFFFFF; --ps-card-border:#E5E7EB;
  --ps-text:#111827; --ps-muted:#6B7280; --ps-nav:#374151; --ps-btn-border:#D1D5DB;
  --ps-shadow:0 1px 2px rgba(16,24,40,.06);
}
html[data-eo-theme="dark"] .stApp{
  --ps-side-bg:#111827; --ps-side-border:#1F2937; --ps-card:#161D2B; --ps-card-border:#263044;
  --ps-text:#F1F5F9; --ps-muted:#94A3B8; --ps-nav:#CBD5E1; --ps-btn-border:#334155; --ps-shadow:none;
}

/* ---- Streamlit's own top bar: invisible, but keep the ⋮ menu and the sidebar-open button ---- */
[data-testid="stHeader"]{background:transparent !important;height:90px !important;
    display:block !important;z-index:999990 !important;pointer-events:none;}
[data-testid="stHeader"] button, [data-testid="stHeader"] a{pointer-events:auto;}
[data-testid="stToolbar"]{position:fixed !important;top:25px !important;right:22px !important;
    height:32px !important;display:flex !important;align-items:center !important;}
[data-testid="stToolbar"] button, [data-testid="stToolbar"] a, [data-testid="stToolbar"] span,
[data-testid="stToolbar"] p, [data-testid="stToolbar"] svg{color:#FFFFFF !important;fill:#FFFFFF;}
[data-testid="stDecoration"]{display:none !important;}

/* blocks that only hold <style> tags still take up space (the gaps above/below the header) */
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child),
.element-container:has([data-testid="stMarkdownContainer"] > style:only-child){display:none !important;}

/* ---- page area: header runs edge to edge ---- */
[data-testid="stMainBlockContainer"], .block-container{
    padding-top:0 !important;padding-left:2.25rem !important;padding-right:2.25rem !important;max-width:100% !important;}
.ps-header{margin:0 -2.25rem 26px -2.25rem;}
/* keep the red + yellow bars pinned at the top while scrolling, so Deploy / ⋮ always sit on the red bar */
[data-testid="stElementContainer"]:has(.ps-header),
.element-container:has(.ps-header){position:sticky;top:0;z-index:999980;}
.ps-red{background:var(--ps-red);display:flex;align-items:center;gap:14px;padding:16px 28px;}
.ps-logo{width:46px;height:46px;border-radius:8px;flex-shrink:0;overflow:hidden;
    border:1px solid rgba(255,255,255,.35);display:flex;align-items:center;justify-content:center;
    background:repeating-linear-gradient(135deg,rgba(255,255,255,.18) 0 6px,rgba(255,255,255,.06) 6px 12px);}
.ps-logo img{width:100%;height:100%;object-fit:contain;}
.ps-logo:has(img){background:#FFFFFF;padding:4px;}
.ps-logo-text{color:#FFFFFF;font-size:9px;font-weight:700;line-height:1.1;text-align:center;}
.ps-kicker{color:#FFFFFF;font-size:12px;font-weight:600;opacity:.95;}
.ps-title{color:#FFFFFF;font-size:26px;font-weight:800;letter-spacing:-.02em;line-height:1.15;}
.ps-yellow{background:var(--ps-yellow);display:flex;justify-content:space-between;align-items:center;
    padding:8px 28px;font-size:12px;color:var(--ps-yellow-text);}
.ps-meta{display:flex;align-items:center;gap:10px;}
.ps-meta-label{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;opacity:.8;}
.ps-meta-sep{width:1px;height:16px;background:rgba(31,41,55,.35);}
.ps-meta-value{font-weight:700;}

/* ---- sidebar ---- */
[data-testid="stSidebar"]{background:var(--ps-side-bg) !important;border-right:1px solid var(--ps-side-border);}
[data-testid="stSidebarContent"]{display:flex !important;flex-direction:column;background:transparent !important;}
[data-testid="stSidebarHeader"]{position:relative;min-height:64px;padding:18px 14px 10px 20px !important;
    border-bottom:1px solid var(--ps-side-border);margin:0 0 10px 0;}
[data-testid="stSidebarHeader"]::before{content:"DASHBOARD";position:absolute;left:20px;top:16px;
    font-size:10px;font-weight:700;letter-spacing:.14em;color:var(--ps-muted);
    font-family:'Plus Jakarta Sans', 'Inter', system-ui, sans-serif !important;}
[data-testid="stSidebarHeader"]::after{content:"Navigation";position:absolute;left:20px;top:31px;
    font-size:16px;font-weight:700;color:var(--ps-text);
    font-family:'Plus Jakarta Sans', 'Inter', system-ui, sans-serif !important;}
[data-testid="stSidebarCollapseButton"]{display:flex !important;visibility:visible !important;opacity:1 !important;
    position:static !important;transform:none !important;margin-left:auto;}
[data-testid="stSidebarCollapseButton"] button{background:var(--ps-card) !important;border:1px solid var(--ps-btn-border) !important;
    border-radius:8px !important;width:32px;height:32px;display:flex !important;align-items:center;justify-content:center;}
[data-testid="stSidebarCollapseButton"] *{visibility:visible !important;opacity:1 !important;color:var(--ps-nav) !important;}
[data-testid="stSidebarNavSeparator"]{display:none;}
[data-testid="stSidebarNav"]{padding:0 10px;}
[data-testid="stSidebarNavLink"]{border-radius:8px;padding:9px 14px !important;margin:2px 0;border-left:3px solid transparent;transition:all 150ms ease !important;
    font-family:'Plus Jakarta Sans', 'Inter', system-ui, sans-serif !important;}
[data-testid="stSidebarNavLink"] span{color:var(--ps-nav) !important;font-size:14px;
    font-family:'Plus Jakarta Sans', 'Inter', system-ui, sans-serif !important;}
[data-testid="stSidebarNavLink"]:hover{background:rgba(148,163,184,.12) !important;}
[data-testid="stSidebarNavLink"]:active{background:rgba(148,163,184,.18) !important;}
[data-testid="stSidebarNavLink"]:focus, [data-testid="stSidebarNavLink"]:focus-visible{outline:none !important;box-shadow:none !important;}
[data-testid="stSidebarNavLink"][aria-current="page"]{background:var(--ps-card) !important;border-left-color:var(--ps-red);
    box-shadow:0 1px 3px rgba(16,24,40,.08);}
[data-testid="stSidebarNavLink"][aria-current="page"] span{color:var(--ps-red) !important;font-weight:600;
    font-family:'Plus Jakarta Sans', 'Inter', system-ui, sans-serif !important;}

/* sidebar content fills the height: "Data" block right under the nav links,
   user card (Log Out) pinned to the bottom */
[data-testid="stSidebarUserContent"]{flex:1 1 auto;display:flex !important;flex-direction:column;
    padding:0 12px 14px 12px !important;}
[data-testid="stSidebarUserContent"] > div,
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]{flex:1 1 auto;display:flex !important;
    flex-direction:column;}
[data-testid="stSidebarUserContent"] *:has(> .st-key-ps_user_card),
.st-key-ps_user_card{margin-top:auto !important;}

/* ---- "Data" block (manual refresh) under the nav links ---- */
.st-key-ps_data_card{border-top:1px solid var(--ps-side-border);padding:14px 8px 0 8px;gap:8px;}
.ps-data-label{font-size:10px;font-weight:700;letter-spacing:.14em;color:var(--ps-muted);text-transform:uppercase;}
.ps-data-line{font-size:12px;color:var(--ps-muted);line-height:1.45;text-align:center;width:100%;}
.ps-data-line b{color:var(--ps-text);font-weight:600;}
.st-key-ps_data_card [data-testid="stMarkdownContainer"]:has(.ps-data-line){justify-content:center !important;}
.st-key-ps_data_card [data-testid="stMarkdown"],
.st-key-ps_data_card [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
.st-key-ps_data_card button{border-radius:10px !important;}
.ps-refresh-note{font-size:12px;font-weight:600;text-align:center;width:100%;line-height:1.4;}
.ps-refresh-note.ok{color:#15803D;}
.ps-refresh-note.err{color:#B91C1C;}
html[data-eo-theme="dark"] .ps-refresh-note.ok{color:#34D399;}
html[data-eo-theme="dark"] .ps-refresh-note.err{color:#FCA5A5;}
.st-key-ps_user_card{background:var(--ps-card);border:1px solid var(--ps-card-border);border-radius:14px;
    padding:14px 14px 12px 14px;box-shadow:0 2px 8px rgba(16,24,40,.06);gap:10px;}
html[data-eo-theme="dark"] .st-key-ps_user_card{box-shadow:0 4px 12px rgba(0,0,0,0.3);}
.ps-user{display:flex;align-items:center;gap:10px;}
.ps-avatar{width:34px;height:34px;border-radius:50%;background:#1F2937;color:#FFFFFF;font-size:12px;font-weight:700;
    display:flex;align-items:center;justify-content:center;flex-shrink:0;position:relative;}
.ps-user-name{font-size:14px;font-weight:700;color:var(--ps-text);line-height:1.2;}
.ps-user-mode{font-size:12px;color:var(--ps-muted);}
.ps-user-mode b{color:var(--ps-text);}
.ps-sync{display:flex;align-items:flex-start;gap:8px;margin:12px 0 4px 0;font-size:12px;
    color:var(--ps-muted);line-height:1.45;}
@keyframes ps-pulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.92);}}
.ps-dot{width:8px;height:8px;border-radius:50%;background:#10B981;flex-shrink:0;margin-top:5px;
    animation:ps-pulse 2.5s infinite ease-in-out;}
/* Streamlit pulls the element after a markdown block up by 1rem; undo that inside the card
   so the sync text never sits on top of the Log Out button */
.st-key-ps_user_card [data-testid="stMarkdown"],
.st-key-ps_user_card [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
.st-key-ps_user_card button{border-radius:10px !important;}
.st-key-ps_legacy_badge{display:none !important;}

/* ---- collapsed sidebar: slim rail with the open button (top) and avatar (bottom) ---- */
.ps-rail{display:none;position:fixed;left:0;top:0;bottom:0;width:58px;z-index:100;
    background:var(--ps-side-bg);border-right:1px solid var(--ps-side-border);
    flex-direction:column;align-items:center;justify-content:flex-end;padding-bottom:16px;}
.ps-rail .ps-avatar::after{content:"";position:absolute;right:-1px;bottom:-1px;width:10px;height:10px;border-radius:50%;
    background:#10B981;border:2px solid var(--ps-side-bg);}
.stApp:has([data-testid="stSidebar"][aria-expanded="false"]) .ps-rail{display:flex;}
/* make room for the rail by shrinking the page area (a plain margin pushed the right side off-screen) */
.stApp:has([data-testid="stSidebar"][aria-expanded="false"]) [data-testid="stMain"]{
    margin-left:58px !important;width:calc(100% - 58px) !important;max-width:calc(100% - 58px) !important;
    flex:1 1 auto;min-width:0;}
/* ---- open-sidebar button (shown while the sidebar is collapsed) ----
   Streamlit's own icon is a font ligature that turned invisible here (the white toolbar rule above makes it
   white-on-white), so it is hidden and a chevron is drawn with CSS instead. The click area stays the same. */
[data-testid="stExpandSidebarButton"]{position:fixed !important;top:14px !important;left:13px !important;z-index:999991 !important;
    background:var(--ps-card, #FFFFFF) !important;border:1px solid var(--ps-btn-border, #D1D5DB) !important;border-radius:8px !important;
    width:32px;height:32px;display:flex !important;align-items:center;justify-content:center;
    visibility:visible !important;opacity:1 !important;cursor:pointer;pointer-events:auto !important;}
[data-testid="stExpandSidebarButton"] *{font-size:0 !important;color:transparent !important;fill:transparent !important;}
[data-testid="stExpandSidebarButton"] button{position:absolute !important;inset:0;width:100% !important;height:100% !important;
    background:transparent !important;border:0 !important;padding:0 !important;cursor:pointer;}
[data-testid="stExpandSidebarButton"]::after{content:"";position:absolute;left:50%;top:50%;width:8px;height:8px;
    border-top:2px solid var(--ps-nav, #1F2937);border-right:2px solid var(--ps-nav, #1F2937);
    transform:translate(-65%, -50%) rotate(45deg);pointer-events:none;}
html[data-eo-theme="dark"] [data-testid="stExpandSidebarButton"]::after{border-color:#E5E7EB;}
/* ============================================================
   MOBILE (<= 640px): phone portrait layout
   ============================================================ */
@media (max-width: 640px) {
  /* Header red bar: compact single line, title with ellipsis if constrained */
  .ps-red {
    padding: 10px 14px !important;
    gap: 8px !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    overflow: hidden !important;
    min-height: 52px !important;
  }
  .ps-logo { width: 34px !important; height: 34px !important; min-width: 34px !important; }
  .ps-kicker { font-size: 9.5px !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }
  .ps-title  { font-size: 16px !important; line-height: 1.2 !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }

  /* Toolbar buttons positioned cleanly in header without collision */
  [data-testid="stToolbar"] { top: 10px !important; right: 10px !important; height: 28px !important; }
  [data-testid="stHeader"] { height: 52px !important; }

  /* Yellow bar: stack the two meta blocks vertically */
  .ps-yellow {
    flex-direction: column !important;
    align-items: flex-start !important;
    gap: 4px !important;
    padding: 6px 14px !important;
  }
  .ps-meta { flex-wrap: wrap !important; gap: 4px 8px !important; }
  .ps-meta-sep { display: none !important; }
  .ps-meta-label { font-size: 9px !important; }
  .ps-meta-value { font-size: 11px !important; }

  /* No sticky header on mobile — saves vertical scrolling space */
  [data-testid="stElementContainer"]:has(.ps-header),
  .element-container:has(.ps-header) {
    position: static !important;
  }

  /* Page content padding tighter */
  [data-testid="stMainBlockContainer"],
  .block-container {
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
  }
  .ps-header { margin: 0 -0.85rem 14px -0.85rem !important; }

  /* Sidebar drawer on mobile */
  [data-testid="stSidebar"] {
    min-width: 270px !important;
    max-width: 85vw !important;
  }
}

/* ============================================================
   MOBILE LANDSCAPE: compact height, preserve screen real estate
   ============================================================ */
@media (max-height: 520px) and (orientation: landscape), (max-width: 950px) and (orientation: landscape) {
  [data-testid="stElementContainer"]:has(.ps-header),
  .element-container:has(.ps-header) {
    position: static !important;
  }
  .ps-header { margin: 0 -1.25rem 10px -1.25rem !important; }
  .ps-red { padding: 6px 16px !important; min-height: 42px !important; gap: 8px !important; }
  .ps-logo { width: 30px !important; height: 30px !important; min-width: 30px !important; }
  .ps-title { font-size: 15px !important; }
  .ps-kicker { font-size: 8.5px !important; }
  .ps-yellow { padding: 4px 16px !important; font-size: 10.5px !important; gap: 6px !important; }
  .ps-meta-label { font-size: 8.5px !important; }
  .ps-meta-value { font-size: 10.5px !important; }
  [data-testid="stToolbar"] { top: 6px !important; right: 12px !important; height: 28px !important; }
  [data-testid="stHeader"] { height: 42px !important; }
  [data-testid="stMainBlockContainer"], .block-container {
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
  }
}

/* ============================================================
   TABLET (<= 1024px): tighten the header so it doesn't wrap awkwardly
   ============================================================ */
@media (max-width: 1024px) and (min-width: 641px) and (min-height: 521px) {
  .ps-red { padding: 14px 22px !important; gap: 12px !important; }
  .ps-title { font-size: 22px !important; }
  .ps-yellow { padding: 8px 22px !important; gap: 12px !important; flex-wrap: wrap !important; }
  .ps-meta-value { font-size: 11px !important; }
}

/* Phones (portrait + landscape): the red header scrolls away there (see above), but Streamlit's Deploy / ⋮
   toolbar is pinned and would float over the page. Hide it while the red header is out of view
   (data-ps-header-gone is set by THEME_DETECTOR_JS); it comes back when you scroll up to the header. */
@media (max-width: 640px), (max-height: 520px) and (orientation: landscape), (max-width: 950px) and (orientation: landscape) {
  [data-testid="stToolbar"] { transition: opacity .15s ease; }
  html[data-ps-header-gone="1"] [data-testid="stToolbar"] { opacity: 0 !important; pointer-events: none !important; }
}
</style>
"""


# ---------------------------------------------------------------------------
# RENDER (header + sidebar)
# ---------------------------------------------------------------------------
_UNSET = "__not_set__"


def set_header_context(program=_UNSET, cohort=_UNSET):
    """Call from ANY page, after its filters, to make the yellow bar match what's selected.

        program: ProgramID (int), ProgramCode ("BIA"), or None for "All Programs"
        cohort:  "1Q2425", or "All Cohorts" / None

    The header is drawn before the page runs, so when the selection changes this
    reruns once to redraw it (quick, the page data is cached).
    """
    ctx = {"page": st.session_state.get("_hdr_page"), "program": program, "cohort": cohort}
    st.session_state["_hdr_ctx"] = ctx
    if st.session_state.get("_hdr_drawn") != ctx:
        # SPEED: repaint the header in place instead of st.rerun(). The old rerun made EVERY page run
        # twice each time it was opened or a cohort/program filter changed.
        slot = st.session_state.get("_hdr_slot")
        if slot is not None:
            _paint_header(slot, ctx, st.session_state.get("_hdr_initials", ""))
            st.session_state["_hdr_drawn"] = ctx
        else:
            st.rerun()   # old behaviour, only if the header slot doesn't exist for some reason


def _resolve_program(value, user_id):
    if value == _UNSET:            # page hasn't picked anything -> "All Programs"
        return None
    if value is None or str(value).strip().lower() in ("", "all", "all programs"):
        return None
    for p in _all_programs():
        if p["ProgramID"] == value or str(p["ProgramCode"]).strip().upper() == str(value).strip().upper():
            return p
    return None


def _paint_header(slot, ctx, initials):
    """Draws the red + yellow header bars into `slot` for the given context (None = All Programs / All Cohorts)."""
    program = _resolve_program(ctx["program"] if ctx else _UNSET, None)
    if program:
        program_text = f'{program["ProgramCode"]} ({SCHOOL_NAME})'
    else:
        program_text = f"All Programs ({SCHOOL_NAME})"

    cohort = ctx["cohort"] if ctx else _UNSET
    # page hasn't picked a cohort -> "All Cohorts"
    term = "All Cohorts" if cohort in (_UNSET, None, "", "All Cohorts") else cohort

    slot.markdown(
        f"""
<div class="ps-header">
  <div class="ps-red">
    <div class="ps-logo">{_logo_html()}</div>
    <div><div class="ps-kicker">{html.escape(UNIVERSITY_LINE)}</div><div class="ps-title">{html.escape(APP_TITLE)}</div></div>
  </div>
  <div class="ps-yellow">
    <div class="ps-meta"><span class="ps-meta-label">Program Instance</span><span class="ps-meta-sep"></span>
      <span class="ps-meta-value">{html.escape(program_text)}</span></div>
    <div class="ps-meta"><span class="ps-meta-label">Cohort</span><span class="ps-meta-sep"></span>
      <span class="ps-meta-value">{html.escape(str(term))}</span></div>
  </div>
</div>
<div class="ps-rail"><div class="ps-avatar">{initials}</div></div>
""",
        unsafe_allow_html=True,
    )


def render_app_shell(user: dict, on_logout=None, page_key=None):
    """Header (red + yellow bars), styled sidebar nav, user card and collapsed rail.

    page_key: which page is open (login.py passes pg.title), so a page's filter
    selection only shows in the header while that page is open.
    """
    user = user or {}
    user_id = user.get("userid")
    role_label = ROLE_LABELS.get(user.get("role"), str(user.get("role") or "User").replace("_", " "))
    initials = html.escape(_initials(user, role_label))

    # What the open page last reported through set_header_context(). Opening another page
    # resets the bar to "All Programs" / "All Cohorts" until that page reports a selection.
    st.session_state["_hdr_page"] = page_key
    ctx = st.session_state.get("_hdr_ctx")
    if not ctx or ctx.get("page") != page_key:
        ctx = None
    st.session_state["_hdr_drawn"] = ctx

    access = _permission_for_user(user_id) if user_id is not None else "View Only"

    st.markdown(SHELL_CSS, unsafe_allow_html=True)

    # header + rail in ONE markdown element (no extra gaps), inside a slot the page can repaint later
    header_slot = st.empty()
    st.session_state["_hdr_slot"] = header_slot
    st.session_state["_hdr_initials"] = initials
    _paint_header(header_slot, ctx, initials)

    # "Data" block: manual refresh for urgent updates (right under the page links, away from Log Out)
    with st.sidebar.container(key="ps_data_card"):
        st.markdown(
            f'<div class="ps-data-line">Next auto-refresh: <b>{html.escape(_next_refresh_label())}</b></div>',
            unsafe_allow_html=True,
        )
        st.button("⟳ Refresh Now", key="ps_refresh", width="stretch", on_click=_manual_refresh,
                  help="Pull the latest data now instead of waiting for the nightly refresh.")
        msg = st.session_state.pop("_ps_refresh_msg", None)
        if msg:   # small one-line note under the button (instead of a big alert box)
            ok, text = msg
            st.markdown(
                f'<div class="ps-refresh-note {"ok" if ok else "err"}">{"✓" if ok else "✕"} {html.escape(text)}</div>',
                unsafe_allow_html=True,
            )

    # sidebar user card (pinned to the bottom by CSS)
    with st.sidebar.container(key="ps_user_card"):
        st.markdown(
            f"""
<div class="ps-user"><div class="ps-avatar">{initials}</div>
  <div><div class="ps-user-name">{html.escape(role_label)} View</div>
  <div class="ps-user-mode">Access mode · <b>{html.escape(str(access))}</b></div></div></div>
<div class="ps-sync"><span class="ps-dot"></span><span>Live Sync Status: {html.escape(_sync_label())}</span></div>
""",
            unsafe_allow_html=True,
        )
        if st.button("Log Out", key="ps_logout", width="stretch"):
            if on_logout:
                on_logout()
            st.session_state.clear()
            st.rerun()

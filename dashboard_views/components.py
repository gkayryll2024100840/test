"""
Unified reusable UI components and styles for Student Roster and Student Profile.
Responsive dual-theme (Light & Dark mode) enterprise styling with accessible contrast steps
and no AI/SaaS anti-patterns.
"""
import pandas as pd
import streamlit as st


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
    current_theme = get_current_theme()

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
/* ============================================================
   DUAL-THEME ENTERPRISE STYLING (LIGHT & DARK MODE)
   ============================================================ */

/* Base Variables: Clean, high-contrast Light Mode default */
:root, .stApp {{
    --app-bg: #FFFFFF;
    --app-text: #0F172A;
    --card-bg: #FFFFFF;
    --card-border: #E2E8F0;
    --card-shadow: 0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.03);
    
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

/* System / Browser Dark Mode */
@media (prefers-color-scheme: dark) {{
    :root, .stApp {{
        --app-bg: #0B0F17;
        --app-text: #F1F5F9;
        --card-bg: #161D2B;
        --card-border: #263044;
        --card-shadow: none;
        
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
}}

{explicit_override}

/* Surface base and text contrast */
.stApp {{
    background-color: var(--app-bg);
    color: var(--app-text);
}}

/* Base typography for content elements without overriding icon fonts */
.stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp label,
.lifecycle-card, .profile-meta-card {{
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Geist", sans-serif;
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
    font-size: 24px !important;
    font-weight: 600 !important;
}}

div[data-testid="stMetricLabel"] {{
    color: var(--metric-lbl-color) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}}

/* Form Inputs & Selectboxes */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {{
    background-color: var(--input-bg) !important;
    border: 1px solid var(--input-border) !important;
    border-radius: 6px !important;
    color: var(--input-text) !important;
}}

div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="input"] > div:focus-within {{
    border-color: var(--input-focus-border) !important;
}}

/* Button overrides - clean enterprise outline */
.stButton > button {{
    background-color: var(--btn-bg) !important;
    color: var(--btn-text) !important;
    border: 1px solid var(--btn-border) !important;
    border-radius: 6px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    transition: all 150ms ease !important;
}}

.stButton > button:hover {{
    background-color: var(--btn-hover-bg) !important;
    border-color: var(--btn-hover-border) !important;
    color: var(--btn-hover-text) !important;
}}

/* Roster Table Grid Styling & Vertical Alignment */
div[data-testid="stHorizontalBlock"] {{
    align-items: center !important;
}}

div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}}

div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stElementContainer"],
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stElementContainer"] {{
    margin-top: 0 !important;
    margin-bottom: 0 !important;
    display: flex !important;
    align-items: center !important;
    min-height: 32px !important;
}}

div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stMarkdownContainer"] {{
    display: flex !important;
    align-items: center !important;
    min-height: 32px !important;
    width: 100% !important;
}}

div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] div[data-testid="stMarkdownContainer"] > p {{
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
    border-radius: 8px !important;
    padding: 20px 24px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-start !important;
    justify-content: center !important;
    gap: 10px !important;
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
    padding: 0 11px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    border-radius: 9999px !important;
    line-height: 1 !important;
    letter-spacing: 0.01em !important;
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
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 24px;
}}

.profile-name {{
    margin: 0;
    color: var(--text-primary);
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.01em;
}}

.profile-id-badge {{
    font-family: monospace;
    font-size: 13px;
    color: var(--id-badge-text);
    background: var(--id-badge-bg);
    border: 1px solid var(--id-badge-border);
    padding: 2px 8px;
    border-radius: 4px;
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
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    margin-top: 24px !important;
    margin-bottom: 14px !important;
    line-height: 1.3 !important;
}}

/* Unified Status Pill Styles */
.status-pill {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 26px;
    padding: 0 11px;
    border-radius: 9999px;
    font-size: 12px;
    font-weight: 500;
    line-height: 1;
    white-space: nowrap;
    width: fit-content;
    box-sizing: border-box;
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


class DynamicThemeCSS:
    """Dynamic theme string that evaluates to the appropriate CSS on demand,
    supporting both Light and Dark mode seamlessly."""

    def __str__(self) -> str:
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

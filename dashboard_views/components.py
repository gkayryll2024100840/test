"""
Unified reusable UI components and styles for Student Roster and Student Profile.
Strict dark-mode enterprise styling with accessible contrast steps and no AI/SaaS anti-patterns.
"""
import pandas as pd

DARK_MODE_CSS = """
<style>
/* Surface base and text contrast */
.stApp {
    background-color: #0B0F17;
    color: #F1F5F9;
}

/* Base typography for content elements without overriding icon fonts */
.stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp label,
.lifecycle-card, .profile-meta-card {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Geist", sans-serif;
}

/* Explicitly preserve Streamlit's Material Symbols Icon fonts */
[data-testid="stIconMaterial"], 
[data-testid*="Icon"], 
[class*="material-symbols"], 
[class*="material-icons"],
i.material-icons,
span[data-testid="stIconMaterial"],
div[data-testid="stSidebarCollapseButton"] span,
button[data-testid="stSidebarCollapseButton"] span {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons" !important;
}

/* Metric / Card overrides */
div[data-testid="stMetricValue"] {
    color: #F1F5F9 !important;
    font-size: 24px !important;
    font-weight: 600 !important;
}

div[data-testid="stMetricLabel"] {
    color: #94A3B8 !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

/* Form Inputs & Selectboxes */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    background-color: #0F172A !important;
    border: 1px solid #263044 !important;
    border-radius: 6px !important;
    color: #F1F5F9 !important;
}

div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="input"] > div:focus-within {
    border-color: #3B82F6 !important;
}

/* Button overrides - clean enterprise outline */
.stButton > button {
    background-color: #161D2B !important;
    color: #F1F5F9 !important;
    border: 1px solid #263044 !important;
    border-radius: 6px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    transition: all 150ms ease !important;
}

.stButton > button:hover {
    background-color: #1E293B !important;
    border-color: #3B82F6 !important;
    color: #FFFFFF !important;
}

/* Roster Table Grid Styling */
.roster-th {
    font-size: 11px;
    font-weight: 600;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 6px 0;
    white-space: nowrap;
}

.roster-th-divider {
    border-bottom: 2px solid #263044;
    margin-top: 4px;
    margin-bottom: 8px;
}

.roster-row-divider {
    border-bottom: 1px solid #1E293B;
    margin: 4px 0 6px 0;
}

.roster-cell-id {
    font-family: monospace;
    color: #94A3B8;
    font-size: 12px;
    line-height: 28px;
    white-space: nowrap;
}

.roster-cell-text {
    color: #CBD5E1;
    font-size: 13px;
    line-height: 28px;
    white-space: nowrap;
}

/* Make st.page_link render as a crisp, clickable blue student name link */
div[data-testid="stPageLink"] {
    width: 100% !important;
    min-height: 28px !important;
    display: flex !important;
    align-items: center !important;
}

div[data-testid="stPageLink"] a {
    color: #60A5FA !important;
    text-decoration: none !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    line-height: 28px !important;
    display: inline-flex !important;
    align-items: center !important;
    transition: color 120ms ease !important;
}

div[data-testid="stPageLink"] a:hover {
    color: #93C5FD !important;
    text-decoration: underline !important;
    background: transparent !important;
}

div[data-testid="stPageLink"] a:focus {
    box-shadow: none !important;
    outline: none !important;
}

/* Student Profile Cards */
.lifecycle-card {
    background-color: #161D2B;
    border: 1px solid #263044;
    border-radius: 8px;
    padding: 18px 20px;
    min-height: 100px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.lifecycle-card-title {
    font-size: 11px;
    font-weight: 600;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 12px;
}

.profile-meta-card {
    background-color: #161D2B;
    border: 1px solid #263044;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 24px;
}

.profile-meta-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 24px;
    margin-top: 12px;
}

.meta-field {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: #94A3B8;
}

.meta-field strong {
    color: #F1F5F9;
    font-weight: 500;
}
</style>
"""


def render_status_pill(status) -> str:
    """Unified StatusPill component adhering strictly to the dark-mode enterprise spec:
    - Standardized height: 24px (h-6)
    - display: inline-flex; align-items: center; justify-content: center;
    - Padding: 0 10px (px-2.5), border-radius: 9999px (rounded-full)
    - Single-line typography: 11px font-medium, leading-none, whitespace-nowrap
    - Semantic palette:
      * Success: Completed, Passed, Defended for Completion, On Track
      * Active: In-Progress, Pending
      * Warning/At Risk: Cancelled, Incomplete, At Risk
    """
    if status is None or (isinstance(status, float) and pd.isna(status)) or str(status).strip().lower() in ["nan", "none", ""]:
        status_str = "Pending"
    else:
        status_str = str(status).strip()

    status_lower = status_str.lower()

    # Success: subtle dark-emerald tint with crisp light text
    if status_lower in ["completed", "passed", "defended for completion", "defended", "on track", "enrolled"]:
        bg = "rgba(16, 185, 129, 0.15)"
        border = "rgba(16, 185, 129, 0.3)"
        text = "#34D399"

    # Warning / At Risk / Incomplete / Cancelled: muted brick red/coral
    elif status_lower in ["cancelled", "canceled", "incomplete", "at risk", "high risk", "critical", "failed", "abs/failed"]:
        bg = "rgba(239, 68, 68, 0.14)"
        border = "rgba(239, 68, 68, 0.3)"
        text = "#FCA5A5"

    # Active / In-Progress / Pending: crisp neutral or cool slate blue
    elif status_lower in ["in-progress", "in progress"]:
        bg = "rgba(59, 130, 246, 0.14)"
        border = "rgba(59, 130, 246, 0.28)"
        text = "#93C5FD"

    # Conditionally Enrolled / Pending / Neutral
    elif status_lower in ["conditionally enrolled"]:
        bg = "rgba(245, 158, 11, 0.14)"
        border = "rgba(245, 158, 11, 0.3)"
        text = "#FCD34D"

    else:
        bg = "rgba(148, 163, 184, 0.12)"
        border = "rgba(148, 163, 184, 0.24)"
        text = "#CBD5E1"

    return (
        f'<span style="display: inline-flex; align-items: center; justify-content: center; '
        f'height: 24px; padding: 0 10px; border-radius: 9999px; '
        f'font-size: 11px; font-weight: 500; line-height: 1; white-space: nowrap; width: fit-content; '
        f'background: {bg}; border: 1px solid {border}; color: {text}; '
        f'box-sizing: border-box;">{status_str}</span>'
    )


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

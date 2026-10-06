from datetime import date

def build_student_onepager_html(data, stage_labels):
    """Builds a print-ready one-page HTML summary. stage_labels: output of get_program_stage_labels()."""
    name = f"{data['FirstName']} {data['LastName']}"
    threshold = data.get("AtRiskThresholdDays")


    stage_map = [
        ("coursework", data["CourseworkStatus"], data["CourseworkUpdateAt"]),
        ("compexam", data["CompExamStatus"], data["CompExamUpdateAt"]),
        ("capstone", data["CapstoneStatus"], data["CapstoneUpdateAt"]),
    ]
    current = next((s for s in stage_map if str(s[1]).strip().lower() == "in-progress"), None)

    at_risk_html = '<p class="ok">No active at-risk flag.</p>'
    if current and current[2] and threshold:
        days = (date.today()  - current[2].date()).days
        if days > threshold:
            at_risk_html = (
                f'<p class="risk">AT RISK - {days} days in '
                f'{stage_labels.get(current[0], current[0])} '
                f'(expected {threshold} days)</p>'
            )


    rows = "".join(
        f"<tr><td>{stage_labels.get(key, key.title())}</td><td>{status or '-'}</td></tr>"
        for key, status, _ in stage_map
    )

    notes_html = "<p>No notes on file.</p>"
    if data.get("Notes"):
        items = "".join(
            f"<li><b>{n['AuthorName']}</b> ({n['CreatedAt']:%Y-%m-%d}): {n['NoteText']}</li>"
            for n in data["Notes"]
        )
        notes_html = f"<ul>{items}</ul>"


     return f"""
    <html><head><style>
        @page {{ size: letter; margin: 0.6in; }}
        body {{ font-family: Arial, sans-serif; color: #1A1F36; }}
        h1 {{ font-size: 20px; margin-bottom: 2px; }}
        .meta {{ color: #6B7280; font-size: 13px; margin-bottom: 16px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
        td {{ border: 1px solid #E5E7EB; padding: 6px 10px; font-size: 13px; }}
        .risk {{ color: #B91C1C; font-weight: 700; }}
        .ok {{ color: #15803D; font-weight: 600; }}
        h2 {{ font-size: 14px; border-bottom: 1px solid #E5E7EB; padding-bottom: 4px; }}
        ul {{ font-size: 13px; padding-left: 18px; }}
    </style></head><body>
        <h1>{name}</h1>
        <div class="meta">
            {data['ProgramName']} · Cohort {data['Cohort']} · Student No. {data['StudentNumber']}
            · Adviser: {data.get('Adviser') or '—'}
        </div>

        <h2>Lifecycle Status</h2>
        <table>{rows}</table>

        <h2>At-Risk Status</h2>
        {at_risk_html}

        <h2>Adviser Notes</h2>
        {notes_html}

        <div class="meta" style="margin-top:20px;">Generated {date.today():%Y-%m-%d}</div>
    </body></html>
    """
# kpi_alerts.py
# ---------------------------------------------------------------------------
# US-36: email the Dean when a core KPI crosses its critical threshold.
#
#   1. Thresholds come from kpi_thresholds.json (configurable, not hardcoded). The Executive Overview
#      colours its KPI numbers with the same file, so the dashboard and the emails always agree.
#   2. check_kpi_alerts() runs right after the nightly data refresh (db_connect), and from the
#      "Check KPI Status" button in Admin Config. Every KPI that newly dropped goes into ONE email.
#   3. For every active program (all cohorts, all statuses) it works out Overall Completion and
#      On-Time Graduation Rate with the same rules as the Executive Overview KPI tiles.
#   4. A KPI below its red line emails the Dean ONCE - the first time it goes red. It stays quiet on the
#      next checks while it is still red, and only emails again after it has recovered and dropped again.
#   5. Every alert is saved in Alert_Logs (UserID = the Dean, StudentNumber = NULL, SentAt = when the
#      email went out, NULL if sending failed - a failed email is retried on the next check).
#
# Email account: the emails are sent FROM the Dean's own address (Users.Email), to that same address.
# Only its password goes in .env (or the hosted app's secrets) - never in the code or the database:
#   ALERT_SMTP_PASSWORD  the Gmail APP password of that address (Google Account > Security >
#                        2-Step Verification > App passwords - the normal Gmail password won't work)
# Optional:
#   ALERT_SMTP_USER      send from a different account instead of the Dean's address
#   ALERT_SMTP_HOST      default: smtp.gmail.com for Gmail addresses, otherwise smtp.office365.com
#   ALERT_SMTP_PORT      default 587
#   DASHBOARD_URL        adds an "Open the dashboard" link to the email
# ---------------------------------------------------------------------------
import json
import os
import re
import smtplib
import ssl
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from html import escape

from db_connect import get_db_connection, LIFECYCLE_STATUS_MAP, _now_local

THRESHOLDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kpi_thresholds.json")
DEFAULT_THRESHOLDS = {   # only used if kpi_thresholds.json is missing or broken
    "overall_completion": {"green_at": 50, "red_below": 40},
    "on_time_rate": {"green_at": 40, "red_below": 30},
}
ALERT_TABLE = "Alert_Logs"

# KPI key -> (name in the email, what the top of the formula counts)
ALERT_KPIS = {
    "overall_completion": ("Overall Completion", "Completed"),
    "on_time_rate": ("On-Time Graduation Rate", "Graduated on time"),
}

# Same rules as the Executive Overview (dashboard_views/executive_overview.py)
COURSEWORK_DONE, COMPEXAM_DONE, CAPSTONE_DONE = "Completed", "Passed", "Defended for Completion"
ON_TIME_TRUE = {"yes", "y", "true", "1", "on time", "on-time"}

# Who gets the emails.
# For now ONLY Mary Grace Bautista (UserID 0987654321) - the only Dean inbox the group can test.
ALERT_RECIPIENT_USER_IDS = ("0987654321",)


def get_alert_recipients(cur):
    """[{UserID, Name, Email}, ...] of the Deans who get KPI alert emails."""
    placeholders = ", ".join(["%s"] * len(ALERT_RECIPIENT_USER_IDS))
    cur.execute(
        "SELECT UserID, FirstName, LastName, Email FROM Users "
        "WHERE Role = 'Dean' AND isActive = 1 AND Email IS NOT NULL AND Email <> '' "
        f"AND UserID IN ({placeholders})",
        ALERT_RECIPIENT_USER_IDS,
    )
    # To email EVERY active Dean instead, replace the cur.execute(...) above with:
    #
    #   cur.execute(
    #       "SELECT UserID, FirstName, LastName, Email FROM Users "
    #       "WHERE Role = 'Dean' AND isActive = 1 AND Email IS NOT NULL AND Email <> ''"
    #   )
    #
    # (ALERT_RECIPIENT_USER_IDS is then no longer used and can be deleted.)
    return [{"UserID": str(r["UserID"]), "Name": f"{r['FirstName']} {r['LastName']}".strip(), "Email": r["Email"]}
            for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Thresholds (kpi_thresholds.json)
# ---------------------------------------------------------------------------
_thresholds_cache = {"mtime": None, "data": None}


def load_thresholds():
    """The whole kpi_thresholds.json (re-read only when the file changes)."""
    try:
        mtime = os.path.getmtime(THRESHOLDS_FILE)
        if _thresholds_cache["mtime"] != mtime:
            with open(THRESHOLDS_FILE, encoding="utf-8") as f:
                _thresholds_cache["data"] = json.load(f)
            _thresholds_cache["mtime"] = mtime
        return _thresholds_cache["data"]
    except Exception as e:
        print(f"Could not read kpi_thresholds.json, using the built-in defaults: {e}")
        return {"default": DEFAULT_THRESHOLDS, "programs": {}}


def thresholds_for(program_code=None):
    """{kpi_key: (green_at, red_below)} for one program (its own values if it has any, else the default).
    "completion_rate" is the old name of Overall Completion, so it gets the same values."""
    data = load_thresholds()
    merged = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    for source in (data.get("default") or {}, (data.get("programs") or {}).get(program_code or "", {}) or {}):
        for key, limits in source.items():
            merged.setdefault(key, {}).update(limits or {})
    out = {k: (float(v["green_at"]), float(v["red_below"])) for k, v in merged.items()}
    out["completion_rate"] = out["overall_completion"]
    return out


# ---------------------------------------------------------------------------
# KPI values per program
# ---------------------------------------------------------------------------
def _pct_1dp(part, whole):
    """Same rounding as the dashboard (half up, 1 decimal)."""
    if not whole:
        return 0.0
    return float((Decimal(int(part)) * 100 / Decimal(int(whole))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _status(value):
    return LIFECYCLE_STATUS_MAP.get(str(value).strip().lower(), value)


def program_kpis(cur):
    """[{ProgramID, ProgramCode, ProgramName, total, overall_completion: (part, pct), on_time_rate: (part, pct)}]
    for every active program - all cohorts, all enrollment statuses (the program's main view)."""
    cur.execute("SELECT ProgramID, ProgramCode, ProgramName FROM Program WHERE IsActive = 1 ORDER BY ProgramCode")
    programs = cur.fetchall()
    cur.execute(
        "SELECT s.StudentNumber, s.ProgramID, sl.CourseworkStatus, sl.CompExamStatus, sl.CapstoneStatus, "
        "sl.GraduateOnTime FROM Students s "
        "LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber"
    )
    students = {}
    for r in cur.fetchall():
        students.setdefault(r["StudentNumber"], r)   # one row per student, like the dashboard

    counts = {}   # ProgramID -> [total, completed, on time]
    for r in students.values():
        c = counts.setdefault(r["ProgramID"], [0, 0, 0])
        c[0] += 1
        if (_status(r["CourseworkStatus"]), _status(r["CompExamStatus"]), _status(r["CapstoneStatus"])) == \
                (COURSEWORK_DONE, COMPEXAM_DONE, CAPSTONE_DONE):
            c[1] += 1
        if str(r["GraduateOnTime"]).strip().lower() in ON_TIME_TRUE:
            c[2] += 1

    result = []
    for p in programs:
        total, done, on_time = counts.get(p["ProgramID"], [0, 0, 0])
        result.append({
            **p,
            "total": total,
            "overall_completion": (done, _pct_1dp(done, total)),
            "on_time_rate": (on_time, _pct_1dp(on_time, total)),
        })
    return result


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def smtp_settings(sender=None):
    """sender = the address to send from when ALERT_SMTP_USER isn't set (the Dean's Users.Email)."""
    user = (os.getenv("ALERT_SMTP_USER") or sender or "").strip()
    is_gmail = user.lower().endswith(("@gmail.com", "@googlemail.com"))
    default_host = "smtp.gmail.com" if is_gmail else "smtp.office365.com"
    return {
        "host": (os.getenv("ALERT_SMTP_HOST") or default_host).strip(),
        "port": int(os.getenv("ALERT_SMTP_PORT") or 587),
        "user": user,
        "password": (os.getenv("ALERT_SMTP_PASSWORD") or "").replace(" ", ""),   # app passwords are shown with spaces
    }


def email_is_configured():
    return bool(os.getenv("ALERT_SMTP_PASSWORD"))


def send_email(to_address, subject, text_body, html_body=None, sender=None):
    """(True, None) if the mail server accepted it, else (False, reason). Sends from `sender` unless
    ALERT_SMTP_USER is set."""
    s = smtp_settings(sender or to_address)
    if not (s["user"] and s["password"]):
        return False, "Email isn't set up: add ALERT_SMTP_PASSWORD (the Gmail app password) to .env"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s["user"]
    msg["To"] = to_address
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    def _send(port):
        if port == 465:   # SSL from the start
            server = smtplib.SMTP_SSL(s["host"], port, timeout=20, context=ssl.create_default_context())
        else:             # 587: plain, then upgraded with STARTTLS
            server = smtplib.SMTP(s["host"], port, timeout=20)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(s["user"], s["password"])
            server.send_message(msg)

    try:
        try:
            _send(s["port"])
        except (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError):
            _send(465 if s["port"] != 465 else 587)   # the server hung up -> try once on its other port
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        return False, (f"The mail server rejected the sign-in for {s['user']} ({e.smtp_code}). Gmail needs an "
                       "APP password (turn on 2-Step Verification, then create one under App passwords), "
                       "not the normal Gmail password.")
    except smtplib.SMTPServerDisconnected:
        return False, (f"The mail server hung up while signing in as {s['user']} (on both ports). Check that "
                       "ALERT_SMTP_USER is the Gmail the app password was made for, and that ALERT_SMTP_PASSWORD "
                       "is that 16-letter app password.")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _alert_email(items, checked_at):
    """ONE email listing every KPI that just dropped below its threshold.
    items = [{program, kpi_key, pct, part, total, red_below}, ...]"""
    when = checked_at.strftime("%b %d, %Y %I:%M %p")
    url = (os.getenv("DASHBOARD_URL") or "").strip()
    n = len(items)
    if n == 1:
        i = items[0]
        subject = (f"KPI alert: {i['program']['ProgramCode']} {ALERT_KPIS[i['kpi_key']][0]} is {i['pct']:.1f}% "
                   f"(below {i['red_below']:g}%)")
    else:
        codes = ", ".join(dict.fromkeys(i["program"]["ProgramCode"] for i in items))
        subject = f"KPI alert: {n} KPIs dropped below their threshold ({codes})"
    intro = ("This KPI has dropped below its threshold:" if n == 1 else
             f"These {n} KPIs have dropped below their threshold:")
    footer = ("You get one email when a KPI first goes below its threshold. You'll be emailed about it again only "
              "if it recovers and then drops again.")

    text_parts = []
    for i in items:
        kpi_name, part_label = ALERT_KPIS[i["kpi_key"]]
        prog = i["program"]
        text_parts.append(
            f"- {prog['ProgramCode']} {kpi_name}: {i['pct']:.1f}% (threshold: below {i['red_below']:g}% needs attention)\n"
            f"  {part_label} ({i['part']:,}) / Total Enrolled ({i['total']:,}) x 100 = {i['pct']:.1f}%, "
            f"{prog['ProgramName']}, all cohorts, all statuses"
        )
    text = (f"{intro}\n\n" + "\n\n".join(text_parts) + f"\n\nChecked: {when}\n\n{footer}\n"
            + (f"\nOpen the dashboard: {url}\n" if url else ""))

    cell = "padding:8px 14px 8px 0;border-bottom:1px solid #E5E7EB;vertical-align:top;"
    head = "padding:6px 14px 6px 0;border-bottom:1px solid #E5E7EB;text-align:left;font-size:12px;color:#6B7280;"
    html_rows = ""
    for i in items:
        kpi_name, part_label = ALERT_KPIS[i["kpi_key"]]
        html_rows += (
            f'<tr><td style="{cell}"><b>{escape(str(i["program"]["ProgramCode"]))}</b></td>'
            f'<td style="{cell}">{escape(kpi_name)}<div style="font-size:12px;color:#6B7280;">'
            f'{escape(part_label)} ({i["part"]:,}) &divide; Total Enrolled ({i["total"]:,}) &times; 100</div></td>'
            f'<td style="{cell}"><b style="color:#B91B21;">{i["pct"]:.1f}%</b></td>'
            f'<td style="{cell}">below {i["red_below"]:g}%</td></tr>'
        )
    html = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#111827;max-width:620px;">'
        f'<p style="font-size:16px;">{escape(intro)}</p>'
        f'<table style="border-collapse:collapse;width:100%;"><tr><th style="{head}">Program</th>'
        f'<th style="{head}">KPI</th><th style="{head}">Value</th><th style="{head}">Threshold</th></tr>'
        f'{html_rows}</table>'
        f'<p style="color:#6B7280;font-size:13px;">Checked {escape(when)} &middot; all cohorts, all statuses.</p>'
        f'<p style="color:#6B7280;font-size:13px;">{escape(footer)}</p>'
        + (f'<p><a href="{escape(url)}">Open the dashboard</a></p>' if url else "")
        + "</div>"
    )
    return subject, text, html


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------
# Alert_Logs.Message starts with a tag so the check can tell which program + KPI a row is about:
#   "[KPI ALERT P3 on_time_rate] ..."  the KPI went red (an email was / will be sent)
#   "[KPI OK P3 on_time_rate] ..."     it recovered (no email) - so the next drop alerts again
_TAG = re.compile(r"^\[KPI (ALERT|OK) P(\d+) ([a-z_]+)\]")


def _latest_kpi_rows(cur):
    """{(UserID, ProgramID, kpi_key): {kind, AlertID, SentAt}} - the newest KPI row of each."""
    cur.execute(
        f"SELECT AlertID, UserID, Message, SentAt FROM {ALERT_TABLE} "
        "WHERE StudentNumber IS NULL AND Message LIKE %s ORDER BY AlertID", ("[KPI %",)
    )
    latest = {}
    for r in cur.fetchall():
        m = _TAG.match(r["Message"] or "")
        if m:
            latest[(str(r["UserID"]), int(m.group(2)), m.group(3))] = {
                "kind": m.group(1), "AlertID": r["AlertID"], "SentAt": r["SentAt"]}
    return latest


def check_kpi_alerts():
    """Runs the US-36 check once ("Check KPI Status" button / nightly). Every KPI that newly dropped goes into ONE email.
    Returns {emails, sent, failed, recovered, red, checked, recipients, errors: [..]}
    (sent / failed = how many KPIs were / couldn't be emailed, emails = how many emails went out)."""
    summary = {"emails": 0, "sent": 0, "failed": 0, "recovered": 0, "red": 0, "checked": 0,
               "recipients": [], "errors": []}
    now = _now_local()
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        recipients = get_alert_recipients(cur)
        summary["recipients"] = [r["Email"] for r in recipients]
        if not recipients:
            summary["errors"].append("No Dean to email (check ALERT_RECIPIENT_USER_IDS in kpi_alerts.py).")
            return summary
        programs = program_kpis(cur)
        latest = _latest_kpi_rows(cur)
        to_email = {r["UserID"]: [] for r in recipients}   # UserID -> the KPIs to put in their email

        for program in programs:
            if not program["total"]:
                continue   # no students yet -> 0% would be a false alarm
            limits = thresholds_for(program["ProgramCode"])
            for kpi_key, (kpi_name, part_label) in ALERT_KPIS.items():
                summary["checked"] += 1
                part, pct = program[kpi_key]
                red_below = limits[kpi_key][1]
                is_red = pct < red_below
                summary["red"] += is_red
                tag_end = f"P{program['ProgramID']} {kpi_key}]"

                for person in recipients:
                    prev = latest.get((person["UserID"], program["ProgramID"], kpi_key))
                    if not is_red:
                        if prev and prev["kind"] == "ALERT":   # recovered -> note it (no email)
                            cur.execute(
                                f"INSERT INTO {ALERT_TABLE} (UserID, StudentNumber, Message, CreatedAt) "
                                "VALUES (%s, NULL, %s, %s)",
                                (person["UserID"],
                                 f"[KPI OK {tag_end} {program['ProgramCode']} {kpi_name} is back to {pct:.1f}% "
                                 f"(threshold {red_below:g}%). No email sent.", now))
                            conn.commit()
                            summary["recovered"] += 1
                        continue

                    if prev and prev["kind"] == "ALERT" and prev["SentAt"] is not None:
                        continue   # already told about this drop -> stay quiet until it recovers
                    if prev and prev["kind"] == "ALERT":
                        alert_id = prev["AlertID"]   # last email failed -> include it again
                    else:
                        cur.execute(
                            f"INSERT INTO {ALERT_TABLE} (UserID, StudentNumber, Message, CreatedAt) "
                            "VALUES (%s, NULL, %s, %s)",
                            (person["UserID"],
                             f"[KPI ALERT {tag_end} {program['ProgramCode']} {kpi_name} is {pct:.1f}%, below the "
                             f"{red_below:g}% threshold ({part_label} {part:,} of {program['total']:,} students). "
                             f"Recipient: {person['Email']}.", now))
                        conn.commit()
                        alert_id = cur.lastrowid
                    to_email[person["UserID"]].append({
                        "alert_id": alert_id, "program": program, "kpi_key": kpi_key, "pct": pct,
                        "part": part, "total": program["total"], "red_below": red_below})

        for person in recipients:   # ONE email per Dean with everything that dropped
            items = to_email[person["UserID"]]
            if not items:
                continue
            subject, text, html = _alert_email(items, now)
            ok, err = send_email(person["Email"], subject, text, html)
            if ok:
                ids = [i["alert_id"] for i in items]
                cur.execute(f"UPDATE {ALERT_TABLE} SET SentAt = %s WHERE AlertID IN ({', '.join(['%s'] * len(ids))})",
                            [_now_local(), *ids])
                conn.commit()
                summary["emails"] += 1
                summary["sent"] += len(items)
            else:
                summary["failed"] += len(items)
                if err not in summary["errors"]:
                    summary["errors"].append(err)
        cur.close()
    finally:
        conn.close()
    return summary


def kpi_status():
    """Read-only, for the Admin Config card: (recipients, rows) where each row is one program's KPI now:
    {ProgramCode, kpi, value, green_at, red_below, is_red, email: None | "sent" | "failed", sent_at}.
    email = what happened to the Dean's alert for the CURRENT drop (None when it isn't red / not checked yet)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        recipients = get_alert_recipients(cur)
        programs = program_kpis(cur)
        latest = _latest_kpi_rows(cur)
        cur.close()
    finally:
        conn.close()

    rows = []
    for p in programs:
        if not p["total"]:
            continue
        limits = thresholds_for(p["ProgramCode"])
        for kpi_key, (kpi_name, _) in ALERT_KPIS.items():
            pct = p[kpi_key][1]
            green_at, red_below = limits[kpi_key]
            alerts = [a for a in (latest.get((r["UserID"], p["ProgramID"], kpi_key)) for r in recipients)
                      if a and a["kind"] == "ALERT"]
            sent = [a["SentAt"] for a in alerts if a["SentAt"] is not None]
            rows.append({
                "ProgramCode": p["ProgramCode"], "kpi": kpi_name, "value": pct,
                "green_at": green_at, "red_below": red_below, "is_red": pct < red_below,
                "email": None if not alerts else ("sent" if sent else "failed"),
                "sent_at": max(sent) if sent else None,
            })
    return recipients, rows

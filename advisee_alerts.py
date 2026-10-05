# advisee_alerts.py
# ---------------------------------------------------------------------------
# US-37: alert a Faculty Advisor when one of THEIR advisees moves to a bad status.
#
#   1. Every status saved in Student Profile adds a row to a history table
#      (Coursework / Comprehensive Exam / Capstone / Enrollment).
#   2. scan_status_changes() looks at the history rows of the last LOOKBACK_DAYS days. A row is an alert when
#      the student moved INTO a bad status (Cancelled, Incomplete, Conditionally Enrolled) from something else.
#      Students who were already in that status don't trigger anything (no new history row = nothing changed).
#   3. The alert goes to the student's adviser(s) only (per US-23): Student_Adviser.AdviserID = the adviser's
#      login, because an adviser's Users.UserID is the same as their AdviserID (e.g. ADV0000001).
#   4. Each alert is one row in Alert_Logs (UserID = adviser, StudentNumber = student). The Message starts with
#      a tag naming the history row, so the same change is never alerted twice.
#   5. The adviser sees the alerts on the Student Roster ("My Alerts") and clicks Acknowledge, which fills
#      Alert_Logs.AcknowledgedAt.
#
# The scan runs right after a status is saved (db_connect), when an adviser opens the Student Roster, and
# every night after the data refresh. Delivered in the dashboard only (no email).
# ---------------------------------------------------------------------------
import re
from datetime import timedelta

from db_connect import get_db_connection, _now_local

ALERT_TABLE = "Alert_Logs"
LOOKBACK_DAYS = 7   # history older than this is never turned into an alert (no flood of old changes)

# tag code -> (history table, stage name shown to the adviser)
HISTORY_SOURCES = {
    "CW": ("Student_Course_Status_History", "Coursework"),
    "CE": ("CompExam_Status_History", "Comprehensive Exam"),
    "CP": ("Capstone_Status_History", "Capstone"),
    "EN": ("Enrollment_Status_History", "Enrollment"),
}
BAD_STATUSES = ("Cancelled", "Incomplete", "Conditionally Enrolled")

# "[STATUS CE H12] Maria Santos (2024100840): Comprehensive Exam changed from In-Progress to Incomplete."
_TAG = re.compile(r"^\[STATUS ([A-Z]{2}) H(\d+)\]\s*")


def _norm(status):
    return str(status or "").strip().lower().replace("-", "").replace(" ", "")


def scan_status_changes(student_number=None):
    """Creates the Alert_Logs rows for new bad status changes. student_number = only check that student
    (used right after a save). Returns how many alerts were created."""
    since = _now_local() - timedelta(days=LOOKBACK_DAYS)
    bad = {_norm(s) for s in BAD_STATUSES}
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)

        # 1. history rows where the student moved INTO a bad status
        changes = []
        for code, (table, stage) in HISTORY_SOURCES.items():
            sql = (
                f"SELECT h.HistoryID, h.StudentNumber, h.Status, h.UpdatedAt, "
                f"(SELECT p.Status FROM `{table}` p WHERE p.StudentNumber = h.StudentNumber "
                f" AND p.HistoryID < h.HistoryID ORDER BY p.HistoryID DESC LIMIT 1) AS PrevStatus "
                f"FROM `{table}` h WHERE h.UpdatedAt >= %s AND h.Status IN ({', '.join(['%s'] * len(BAD_STATUSES))})"
            )
            params = [since, *BAD_STATUSES]
            if student_number is not None:
                sql += " AND h.StudentNumber = %s"
                params.append(str(student_number))
            try:
                cur.execute(sql, params)
            except Exception as e:   # e.g. a history table that doesn't exist on this database
                print(f"US-37: skipped {table}: {e}")
                continue
            for r in cur.fetchall():
                if _norm(r["Status"]) in bad and _norm(r["PrevStatus"]) != _norm(r["Status"]):
                    changes.append({**r, "code": code, "stage": stage, "StudentNumber": str(r["StudentNumber"])})
        if not changes:
            return 0

        students = sorted({c["StudentNumber"] for c in changes})
        marks = ", ".join(["%s"] * len(students))

        # 2. who advises them (only advisers that have a login: Users.UserID = AdviserID)
        cur.execute(
            f"SELECT sa.StudentNumber, u.UserID FROM Student_Adviser sa "
            f"JOIN Users u ON u.UserID = sa.AdviserID WHERE sa.StudentNumber IN ({marks})", students)
        advisers = {}
        for r in cur.fetchall():
            advisers.setdefault(str(r["StudentNumber"]), set()).add(str(r["UserID"]))

        cur.execute(f"SELECT StudentNumber, FirstName, LastName FROM Students WHERE StudentNumber IN ({marks})",
                    students)
        names = {str(r["StudentNumber"]): f"{r['FirstName']} {r['LastName']}".strip() for r in cur.fetchall()}

        # 3. alerts that already exist (never alert the same change twice)
        cur.execute(f"SELECT UserID, Message FROM {ALERT_TABLE} WHERE Message LIKE %s", ("[STATUS %",))
        existing = set()
        for r in cur.fetchall():
            m = _TAG.match(r["Message"] or "")
            if m:
                existing.add((str(r["UserID"]), m.group(1), int(m.group(2))))

        # 4. one Alert_Logs row per adviser per change
        now = _now_local()
        created = 0
        for c in changes:
            sn = c["StudentNumber"]
            for user_id in sorted(advisers.get(sn, ())):
                if (user_id, c["code"], int(c["HistoryID"])) in existing:
                    continue
                before = f"from {c['PrevStatus']} " if c["PrevStatus"] else ""
                when = c["UpdatedAt"].strftime("%b %d, %Y %I:%M %p") if c["UpdatedAt"] else "recently"
                message = (f"[STATUS {c['code']} H{c['HistoryID']}] {names.get(sn, 'Student')} ({sn}): "
                           f"{c['stage']} changed {before}to {c['Status']} on {when}.")
                cur.execute(
                    f"INSERT INTO {ALERT_TABLE} (UserID, StudentNumber, Message, CreatedAt) VALUES (%s, %s, %s, %s)",
                    (user_id, int(sn), message, now))
                created += 1
        conn.commit()
        cur.close()
        return created
    finally:
        conn.close()


def my_alerts(user_id, acknowledged=False, limit=50):
    """The adviser's status alerts, newest first: unacknowledged ones, or (acknowledged=True) the ones they
    already acknowledged."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT AlertID, StudentNumber, Message, CreatedAt, AcknowledgedAt FROM {ALERT_TABLE} "
            f"WHERE UserID = %s AND Message LIKE %s AND AcknowledgedAt IS {'NOT ' if acknowledged else ''}NULL "
            "ORDER BY AlertID DESC LIMIT %s",
            (str(user_id), "[STATUS %", int(limit)))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    for r in rows:
        m = _TAG.match(r["Message"] or "")
        text = _TAG.sub("", r["Message"] or "")
        student, _, change = text.partition("): ")
        r["Stage"] = HISTORY_SOURCES.get(m.group(1), ("", ""))[1] if m else ""
        r["Student"] = (student + ")") if change else ""
        r["Change"] = change.rstrip(".") if change else text
    return rows


def acknowledge(alert_id, user_id):
    """Marks one of the adviser's OWN alerts as acknowledged. Returns True if it changed."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {ALERT_TABLE} SET AcknowledgedAt = %s "
            "WHERE AlertID = %s AND UserID = %s AND AcknowledgedAt IS NULL AND Message LIKE %s",
            (_now_local(), int(alert_id), str(user_id), "[STATUS %"))
        conn.commit()
        changed = cur.rowcount == 1
        cur.close()
        return changed
    finally:
        conn.close()

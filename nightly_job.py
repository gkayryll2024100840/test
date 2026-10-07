# nightly_job.py
# ---------------------------------------------------------------------------
# Runs the dashboard's nightly work from GitHub Actions (.github/workflows/nightly.yml), so it happens even
# when nobody has the dashboard open (a hosted Streamlit app goes to sleep when no one visits it).
#
# The nightly work (same as db_connect.run_scheduled_refresh_if_due):
#   1. data refresh                       -> App_Settings.last_sync / last_scheduled_run
#   2. configuration backup (US-48)       -> Config_Backups row with Reason = 'scheduled'
#   3. KPI email alerts to the Dean (US-36)
#   4. advisee status alerts (US-37)
#
# Safe to run several times a night: each step checks whether today's work is already done. If a copy of the
# dashboard (e.g. one running older code) already ran the refresh tonight, this script still adds whatever
# that copy skipped (the backup, the alerts).
#
# Exit code 1 = something failed -> GitHub marks the run red and emails the repo owner.
# ---------------------------------------------------------------------------
import os
import sys

os.environ.setdefault("DISABLE_REFRESH_SCHEDULER", "1")   # this script does the job itself; no background thread

from db_connect import (   # noqa: E402  (the line above must run first)
    DEFAULT_REFRESH_TIME,
    _now_local,
    _parse_hhmm,
    get_db_connection,
    get_setting,
    run_scheduled_refresh_if_due,
)


def _scheduled_backup_exists(today):
    """True when tonight's 'scheduled' backup is already in Config_Backups."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Config_Backups WHERE Reason = 'scheduled' AND DATE(CreatedAt) = %s",
                    (today,))
        found = cur.fetchone()[0] > 0
        cur.close()
        return found
    except Exception:
        return False   # table not created yet -> create_backup() makes it
    finally:
        conn.close()


def main():
    now = _now_local()   # Philippine time, same clock as the dashboard
    today = now.date().isoformat()
    refresh_time = get_setting("refresh_time", DEFAULT_REFRESH_TIME) or DEFAULT_REFRESH_TIME
    hh, mm = _parse_hhmm(refresh_time)
    if (now.hour, now.minute) < (hh, mm):
        print(f"Not time yet: the refresh time in Admin Config is {hh:02d}:{mm:02d}, it is {now:%H:%M} now.")
        return 0

    problems = []

    # 1-4. the normal nightly job (does nothing if it already ran today)
    ran_here = run_scheduled_refresh_if_due(now)
    if get_setting("last_scheduled_date") != today:
        print("The nightly refresh could not start (database unreachable?).")
        return 1
    print("Nightly refresh: " + ("ran now." if ran_here else "already ran tonight."))
    if get_setting("last_scheduled_status") == "Failed":
        problems.append("the data refresh failed (see last_scheduled_status in App_Settings)")

    # 2. backup: add it if tonight's run didn't save one
    if _scheduled_backup_exists(today):
        print("Configuration backup: done.")
    else:
        from config_backup import create_backup
        ok, msg, _ = create_backup("SCHEDULER", "scheduled")
        print(f"Configuration backup: {msg}")
        if not ok:
            problems.append(msg)

    # 3-4. alerts: only needed when another copy of the dashboard ran tonight's job (it may run older code).
    # Both checks are safe to repeat: the Dean is emailed once per drop, an advisee change is alerted once.
    if not ran_here:
        from kpi_alerts import check_kpi_alerts
        alerts = check_kpi_alerts()
        print(f"KPI alerts: {alerts['emails']} email(s) sent, {alerts['red']} KPI(s) below threshold.")
        if alerts["failed"] or (alerts["errors"] and not alerts["sent"]):
            problems.append(f"KPI alert email: {alerts['errors'][0] if alerts['errors'] else 'not sent'}")

        from advisee_alerts import scan_status_changes
        print(f"Advisee alerts: {scan_status_changes()} new alert(s).")

    if problems:
        print("FAILED: " + "; ".join(problems))
        return 1
    print("Nightly job finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

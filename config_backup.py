# CONFIG_BACKUP.PY (US-48: back up and restore the dashboard's configuration)
#
# What a backup contains (one JSON document):
#   - field mappings          (field_mappings.json, via field_mapping.py)
#   - KPI tile config         (Program.KpiTiles)
#   - at-risk thresholds      (Program.AtRiskThresholdDays + Program_Stage.ExpectedDays)
#   - stage labels            (Program_Stage.StageLabel / StageOrder / IsRequired)
#   - refresh schedule        (App_Settings.refresh_time)
#   - connection settings     (DB host / port / database / user - NEVER the password)
#
# Where backups are kept:
#   - the Config_Backups table (created automatically, newest KEEP_BACKUPS are kept)
#   - a downloadable .json file (Admin Config) - keep a copy outside the database for outages
#
# When backups run:
#   - every night, right after the scheduled data refresh (db_connect.run_scheduled_refresh_if_due)
#   - "Back up now" in Admin Config (before any big change)
#   - automatically right before every restore, so a restore can always be undone
#
# Programs are matched by ProgramCode (not ProgramID), so a backup still restores onto a re-created database.
import json
import os

import mysql.connector

from db_connect import (
    get_db_connection,
    format_mysql_error,
    can_edit,
    log_permission_attempt,
    _now_local,
    SETTINGS_TABLE,
)
from field_mapping import load_mappings, save_mappings

BACKUP_TABLE = "Config_Backups"
BACKUP_FORMAT = "projectpulse-config-backup"
BACKUP_VERSION = 1
KEEP_BACKUPS = 60                    # older backups are deleted automatically
BACKED_UP_SETTINGS = ["refresh_time"]  # App_Settings keys that are configuration (not run history)

_table_ready = False


def _ensure_table(cur):
    global _table_ready
    if _table_ready:
        return
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
            BackupID  INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
            CreatedAt DATETIME     NOT NULL,
            CreatedBy VARCHAR(64)  NULL,
            Reason    VARCHAR(32)  NOT NULL,
            Payload   MEDIUMTEXT   NOT NULL
        )
        """
    )
    _table_ready = True


def _text(value):
    """JSON / text columns can come back as bytes depending on the connector version."""
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


# ---------------------------------------------------------------------------
# BACKUP
# ---------------------------------------------------------------------------
def collect_config(created_by=None, reason="manual"):
    """Reads the current configuration into one dict (the backup document)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT ProgramID, ProgramCode, ProgramName, IsActive, KpiTiles, AtRiskThresholdDays "
                    "FROM Program ORDER BY ProgramCode")
        programs = cur.fetchall()
        cur.execute("SELECT p.ProgramCode, ps.Pillar, ps.StageLabel, ps.StageOrder, ps.IsRequired, ps.ExpectedDays "
                    "FROM Program_Stage ps JOIN Program p ON p.ProgramID = ps.ProgramID "
                    "ORDER BY p.ProgramCode, ps.StageOrder")
        stages = cur.fetchall()
        cur.execute(f"SELECT SettingKey, SettingValue FROM {SETTINGS_TABLE} "
                    f"WHERE SettingKey IN ({', '.join(['%s'] * len(BACKED_UP_SETTINGS))})", BACKED_UP_SETTINGS)
        settings = {_text(r["SettingKey"]): _text(r["SettingValue"]) for r in cur.fetchall()}
        cur.close()
    finally:
        conn.close()

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "created_by": None if created_by is None else str(created_by),
        "reason": reason,
        "field_mappings": load_mappings(),
        "programs": [
            {
                "ProgramCode": _text(p["ProgramCode"]),
                "ProgramName": _text(p["ProgramName"]),
                "IsActive": p["IsActive"],
                "KpiTiles": _text(p["KpiTiles"]),          # JSON text (None = default tiles)
                "AtRiskThresholdDays": p["AtRiskThresholdDays"],
            }
            for p in programs
        ],
        "program_stages": [
            {
                "ProgramCode": _text(s["ProgramCode"]),
                "Pillar": _text(s["Pillar"]),
                "StageLabel": _text(s["StageLabel"]),
                "StageOrder": s["StageOrder"],
                "IsRequired": s["IsRequired"],
                "ExpectedDays": s["ExpectedDays"],
            }
            for s in stages
        ],
        "app_settings": settings,
        "connection": {
            "DB_HOST": os.getenv("DB_HOST"),
            "DB_PORT": os.getenv("DB_PORT", "3306"),
            "DB_NAME": os.getenv("DB_NAME"),
            "DB_USER": os.getenv("DB_USER"),
            "note": "The password is never stored in a backup. Keep it somewhere safe (e.g. a password manager).",
        },
    }


def create_backup(created_by=None, reason="manual"):
    """Saves a backup of the current configuration. Returns (True, message, backup_id) or (False, error, None)."""
    try:
        payload = collect_config(created_by, reason)
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            _ensure_table(cur)
            cur.execute(
                f"INSERT INTO {BACKUP_TABLE} (CreatedAt, CreatedBy, Reason, Payload) VALUES (%s, %s, %s, %s)",
                (payload["created_at"], payload["created_by"], reason, json.dumps(payload)),
            )
            backup_id = cur.lastrowid
            # keep only the newest KEEP_BACKUPS backups
            cur.execute(
                f"DELETE FROM {BACKUP_TABLE} WHERE BackupID NOT IN ("
                f"SELECT BackupID FROM (SELECT BackupID FROM {BACKUP_TABLE} "
                f"ORDER BY BackupID DESC LIMIT {int(KEEP_BACKUPS)}) newest)"
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return True, f"Backup #{backup_id} saved ({payload['created_at']}).", backup_id
    except mysql.connector.Error as e:
        return False, f"Backup failed: {format_mysql_error(e)}", None
    except Exception as e:
        return False, f"Backup failed: {e}", None


def list_backups(limit=20):
    """Newest backups first: [{"BackupID", "CreatedAt", "CreatedBy", "Reason"}, ...]."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        _ensure_table(cur)
        cur.execute(f"SELECT BackupID, CreatedAt, CreatedBy, Reason FROM {BACKUP_TABLE} "
                    f"ORDER BY BackupID DESC LIMIT {int(limit)}")
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return rows


def get_backup(backup_id):
    """The backup document (dict) for one BackupID, or None."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        _ensure_table(cur)
        cur.execute(f"SELECT Payload FROM {BACKUP_TABLE} WHERE BackupID = %s", (int(backup_id),))
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    return json.loads(_text(row[0])) if row else None


def backup_file_bytes(payload):
    """The backup as a nicely formatted .json file."""
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def backup_file_name(payload):
    stamp = str(payload.get("created_at", "")).replace(":", "").replace(" ", "_").replace("-", "")
    return f"dashboard_config_backup_{stamp or 'unknown'}.json"


# ---------------------------------------------------------------------------
# RESTORE
# ---------------------------------------------------------------------------
def parse_backup_file(raw_bytes):
    """Reads an uploaded backup file. Returns (payload, None) or (None, error message)."""
    try:
        payload = json.loads(raw_bytes.decode("utf-8-sig"))
    except Exception:
        return None, "This file isn't valid JSON."
    error = validate_backup(payload)
    return (None, error) if error else (payload, None)


def validate_backup(payload):
    """None if the backup document looks right, else a short error message."""
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        return "This isn't a dashboard configuration backup."
    if payload.get("version") != BACKUP_VERSION:
        return f"Unsupported backup version: {payload.get('version')!r}."
    if not isinstance(payload.get("field_mappings"), dict):
        return "The backup has no field mappings."
    if not isinstance(payload.get("programs"), list) or not isinstance(payload.get("program_stages"), list):
        return "The backup has no program settings."
    return None


def backup_summary(payload):
    """Short facts about a backup, for the preview before restoring."""
    return {
        "Created": f"{payload.get('created_at', '?')} by {payload.get('created_by') or 'unknown'} "
                   f"({payload.get('reason', '?')})",
        "Programs": ", ".join(p["ProgramCode"] for p in payload.get("programs", [])) or "none",
        "Field mappings": str(len(payload.get("field_mappings", {}))),
        "Stage rows (labels + thresholds)": str(len(payload.get("program_stages", []))),
        "Refresh time": (payload.get("app_settings") or {}).get("refresh_time", "not set"),
    }


def restore_backup(payload, user_id):
    """Puts a backup's configuration back. Edit permission only.

    1. Saves a backup of the CURRENT configuration first ("before restore"), so this can be undone.
    2. Restores KPI tiles, thresholds, stage labels and the refresh time in ONE database transaction.
    3. Writes the field mappings back.
    Connection settings are NOT changed by a restore (the app needs them to reach the database at all);
    they stay in the backup file as a record of which database the dashboard used.

    Returns (True, message) or (False, error message).
    """
    error = validate_backup(payload)
    if error:
        return False, error
    if not can_edit(user_id):
        log_permission_attempt(user_id)
        return False, "You have View Only access, so you can't restore a backup."

    ok, msg, safety_id = create_backup(user_id, "before restore")
    if not ok:
        return False, f"Nothing was restored: couldn't save the current settings first ({msg})"

    conn = get_db_connection()
    try:
        if conn.in_transaction:
            conn.rollback()
        conn.start_transaction()
        cur = conn.cursor()
        cur.execute("SELECT ProgramCode, ProgramID FROM Program")
        id_by_code = {_text(code): pid for code, pid in cur.fetchall()}

        restored, skipped = [], []
        for p in payload["programs"]:
            pid = id_by_code.get(p["ProgramCode"])
            if pid is None:
                skipped.append(p["ProgramCode"])
                continue
            cur.execute("UPDATE Program SET KpiTiles = %s, AtRiskThresholdDays = %s WHERE ProgramID = %s",
                        (p.get("KpiTiles"), p.get("AtRiskThresholdDays"), pid))
            restored.append(p["ProgramCode"])

        for s in payload["program_stages"]:
            pid = id_by_code.get(s["ProgramCode"])
            if pid is None:
                continue
            cur.execute(
                "INSERT INTO Program_Stage (ProgramID, Pillar, StageLabel, StageOrder, IsRequired, ExpectedDays) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE StageLabel = VALUES(StageLabel), StageOrder = VALUES(StageOrder), "
                "IsRequired = VALUES(IsRequired), ExpectedDays = VALUES(ExpectedDays)",
                (pid, s["Pillar"], s["StageLabel"], s["StageOrder"], s["IsRequired"], s["ExpectedDays"]),
            )

        for key, value in (payload.get("app_settings") or {}).items():
            if key in BACKED_UP_SETTINGS and value:
                cur.execute(
                    f"INSERT INTO {SETTINGS_TABLE} (SettingKey, SettingValue, UpdatedBy) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE SettingValue = VALUES(SettingValue), UpdatedBy = VALUES(UpdatedBy)",
                    (key, str(value), str(user_id)),
                )
        conn.commit()
        cur.close()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        detail = format_mysql_error(e) if isinstance(e, mysql.connector.Error) else str(e)
        return False, f"Nothing was restored: {detail}"
    finally:
        conn.close()

    try:
        save_mappings(payload["field_mappings"])
    except Exception as e:
        return False, (f"Program settings were restored, but the field mappings couldn't be saved: {e}. "
                       f"Backup #{safety_id} has the settings from before the restore.")

    msg = (f"Restored settings from {payload.get('created_at', 'the backup')} "
           f"({', '.join(restored) or 'no programs'}). The previous settings were saved as backup #{safety_id}.")
    if skipped:
        msg += f" Skipped programs that don't exist anymore: {', '.join(skipped)}."
    return True, msg

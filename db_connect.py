# DB_CONNECT.PY 
# (speed-optimized: connection pool, try/finally on hot reads, leaner roster query)
import os
import time
import threading
import mysql.connector
import queue
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv 
from system_log import log_sync_attempt_local, get_system_logs_local, get_max_retry_count_local
from field_mapping import load_mappings

# Load database credentials from .env file into memory 
load_dotenv(override=True)  

# Dictionary mapping for env details
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306))
}

# Standardized status mapping for US-07, US-08, and US-09
LIFECYCLE_STATUS_MAP = {
    # US-07: Pending, Cancelled, Completed
    "pending": "Pending",
    "cancelled": "Cancelled",
    "completed": "Completed",
    # US-08: In-Progress, Incomplete, Passed
    "in-progress": "In-Progress",
    "incomplete": "Incomplete",
    "passed": "Passed",
    # US-09: In-Progress, Defended for Completion
    "defended for completion": "Defended for Completion",
    "defended": "Defended for Completion"
}

# SPEED (with a hard cap): opening a brand-new MySQL connection costs far more than the queries themselves,
# so finished connections are kept and reused. Connections are opened ONLY when needed (never up front),
# the total is capped (DB_POOL_SIZE, default 3 - hosted MySQL plans often allow only ~5-10 connections in
# total), and idle ones are closed after DB_POOL_IDLE_SECONDS so they don't hog the limit.
# If every connection is busy, callers wait (up to 10 s) instead of opening more -> no "Too many connections".
# conn.close() still works as before: on a pooled connection it just hands it back.
_MAX_OPEN = max(1, int(os.getenv("DB_POOL_SIZE", 3)))
_IDLE_SECONDS = int(os.getenv("DB_POOL_IDLE_SECONDS", 60))
_WAIT_SECONDS = 10
_PING_AFTER_SECONDS = 10         # only connections idle longer than this are pinged before reuse
_idle = queue.LifoQueue()        # items: (raw_connection, time_it_was_returned)
_open_count = 0                  # raw connections currently alive (idle + in use)
_pool_lock = threading.Lock()


class _PooledConn:
    """Behaves like a normal MySQL connection, except close() returns it to the pool."""

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_released", False)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def close(self):
        if self._released:
            return
        object.__setattr__(self, "_released", True)
        _release(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _discard(raw):
    """Really close a raw connection and free its slot."""
    global _open_count
    try:
        raw.close()
    except Exception:
        pass
    with _pool_lock:
        _open_count = max(0, _open_count - 1)


def _release(raw):
    """Give a finished connection back (or drop it if it's broken)."""
    try:
        if raw.in_transaction:
            raw.rollback()               # end any open read snapshot so the next user sees fresh data
        _idle.put((raw, time.monotonic()))
    except Exception:
        _discard(raw)


def _alive(raw):
    try:
        return raw.is_connected()        # pings the server
    except Exception:
        return False


def reap_idle_connections():
    """Close pooled connections that have been idle too long (called by the background checker)."""
    keep = []
    while True:
        try:
            raw, ts = _idle.get_nowait()
        except queue.Empty:
            break
        if time.monotonic() - ts > _IDLE_SECONDS:
            _discard(raw)
        else:
            keep.append((raw, ts))
    for item in keep:
        _idle.put(item)


def get_db_connection():
    """Return a live MySQL connection. Callers must call .close() when done (hands it back to the pool)."""
    global _open_count
    deadline = time.monotonic() + _WAIT_SECONDS
    while True:
        try:
            raw, ts = _idle.get_nowait()
        except queue.Empty:
            with _pool_lock:
                can_open = _open_count < _MAX_OPEN
                if can_open:
                    _open_count += 1
            if can_open:
                try:
                    cfg = {**db_config, "connection_timeout": db_config.get("connection_timeout", 10)}
                    return _PooledConn(mysql.connector.connect(**cfg))
                except Exception:
                    with _pool_lock:
                        _open_count = max(0, _open_count - 1)
                    raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise mysql.connector.Error(
                    msg="Database is busy (all connections are in use). Please try again in a moment.",
                    errno=1040,
                )
            try:
                raw, ts = _idle.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
        # got an idle connection - make sure it's still good. The check pings the server (one full round
        # trip, ~150 ms on the hosted database), so it's skipped for connections handed back moments ago:
        # those are still open, and a page makes many quick queries in a row (US-49 speed).
        idle_for = time.monotonic() - ts
        if idle_for > _IDLE_SECONDS or (idle_for > _PING_AFTER_SECONDS and not _alive(raw)):
            _discard(raw)
            continue
        return _PooledConn(raw)

def format_mysql_error(err):
    """Translates MySQL error codes into clean error messages."""
    error_code = err.errno

    if error_code == 1045:
        return "Authentication failed: Check database username or password in .env"
    elif error_code == 1049:
        return "Database not found: Verify DB_NAME in your environment configuration"
    elif error_code == 1146:
        return "Schema error: Required database table is missing"
    elif error_code in (2003, 2026):
        return "Connection timeout to SQL Server host"
    elif error_code in (2013, 2006):
        return "Network socket closed unexpectedly during bulk data transfer"
    elif error_code == 2017:
        return "Cannot connect to database host (Named pipe error): Check if .env exists and DB_HOST is configured properly"
    else:
        return f"Database error ({error_code}): {err.msg}"

def trigger_data_sync(login_id=None):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Students LIMIT 1")
        cursor.fetchall()
        cursor.close()
        conn.close()

        # The sync time is saved in the database (App_Settings) so every app process / server restart
        # sees the same value. last_sync.txt is only a local fallback: on a hosted app the disk is reset
        # to the git version on every reboot, which is why the sidebar used to be stuck on an old date.
        synced_at = _now_local().strftime("%Y-%m-%d %H:%M:%S")
        set_setting("last_sync", synced_at, "SCHEDULER" if login_id == "SCHEDULED" else login_id)
        try:
            with open("last_sync.txt", "w") as f:
                f.write(synced_at)
        except Exception:
            pass
        return True

    except mysql.connector.Error as err:
        msg = format_mysql_error(err)
        log_sync_attempt_local("FAILED", error_message=msg, login_id=login_id)
        return False

    except Exception as e:
        log_sync_attempt_local("FAILED", error_message=str(e), login_id=login_id)
        return False

# Retrieve system_logs.py for admin view
def get_system_logs():
    """Wrapper to pull logs from local SQLite storage for admin view."""
    return get_system_logs_local()

def get_max_retry_count(login_id):
    """Wrapper to check retry count from local storage."""
    return get_max_retry_count_local(login_id)

# Connects to database > queries rows from Students table > converts results into a Pandas Dataframe  
def get_student_roster_data(program_id=None):
    """Fetches the roster.

    program_id=None returns students from every program (used by the "All Programs"
    option on the Student Roster). A specific program_id filters to that program.
    """
    try:
        # 1. Load the mappings from the JSON file
        mappings = load_mappings()

        # 2. Validate EVERY mapped field against the cached schema snapshot
        invalid = find_invalid_mappings(mappings)
        if invalid:
            schema_error = get_schema_load_error()
            if schema_error:
                raise ValueError(f"Could not verify field mappings: {schema_error}")
            details = "; ".join(f"'{label}': '{path}'" for label, path in invalid)
            raise ValueError(f"Invalid or unverified mapping(s) - {details}")

        # 3. Run the query (all programs when program_id is None)
        # SPEED: the adviser sub-query is limited to the target students (never a full-school scan).
        if program_id is None:
            query = """
                SELECT
                    s.StudentNumber,
                    CONCAT(s.FirstName, ' ', s.LastName) AS Student,
                    p.ProgramCode,
                    s.Cohort,
                    s.EnrollmentStatus,
                    a.AdviserName AS Adviser,
                    sl.CourseworkStatus,
                    sl.CompExamStatus,
                    sl.CapstoneStatus,
                    sl.LastUpdate
                FROM Students s
                LEFT JOIN Program p ON s.ProgramID = p.ProgramID
                LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
                LEFT JOIN (
                    SELECT sa.StudentNumber,
                           GROUP_CONCAT(ad.AdviserName ORDER BY ad.AdviserName SEPARATOR ', ') AS AdviserName
                    FROM Student_Adviser sa
                    JOIN Adviser ad ON sa.AdviserID = ad.AdviserID
                    GROUP BY sa.StudentNumber
                ) a ON a.StudentNumber = s.StudentNumber
            """
            params = None
        else:
            query = """
                SELECT
                    s.StudentNumber,
                    CONCAT(s.FirstName, ' ', s.LastName) AS Student,
                    p.ProgramCode,
                    s.Cohort,
                    s.EnrollmentStatus,
                    a.AdviserName AS Adviser,
                    sl.CourseworkStatus,
                    sl.CompExamStatus,
                    sl.CapstoneStatus,
                    sl.LastUpdate
                FROM Students s
                LEFT JOIN Program p ON s.ProgramID = p.ProgramID
                LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
                LEFT JOIN (
                    SELECT sa.StudentNumber,
                           GROUP_CONCAT(ad.AdviserName ORDER BY ad.AdviserName SEPARATOR ', ') AS AdviserName
                    FROM Student_Adviser sa
                    JOIN Adviser ad ON sa.AdviserID = ad.AdviserID
                    JOIN Students sp ON sp.StudentNumber = sa.StudentNumber AND sp.ProgramID = %s
                    GROUP BY sa.StudentNumber
                ) a ON a.StudentNumber = s.StudentNumber
                WHERE s.ProgramID = %s
            """
            params = (program_id, program_id)

        conn = get_db_connection()
        try:
            df = pd.read_sql(query, conn, params=params)
        finally:
            conn.close()
        return df

    except Exception as e:
        print(f"Mapping validation failed: {e}")
        raise e

def get_last_updated_time():
    """Last successful sync timestamp: App_Settings first (shared by every process), last_sync.txt as fallback.

    Uses the newest of the last manual/any sync (last_sync) and the last SUCCESSFUL nightly run
    (last_scheduled_run, the same value Admin Config > Data Refresh Schedule shows).
    """
    vals = get_settings(["last_sync", "last_scheduled_run", "last_scheduled_status"])
    candidates = [vals.get("last_sync")]
    if vals.get("last_scheduled_status") == "Success":
        candidates.append(vals.get("last_scheduled_run"))
    candidates = [c for c in candidates if c]
    if candidates:
        return max(candidates)   # same "YYYY-MM-DD HH:MM:SS" format, so text order = time order
    try:
        if os.path.exists("last_sync.txt"):
            with open("last_sync.txt", "r") as f:
                return f.read().strip()
        return "No sync recorded"
    except Exception:
        return "Unavailable"

def get_student_profile_data(student_number):
    """Fetches full student details for a specific student number."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # Adviser link lives on the Student_Adviser junction table.
            query = """
                SELECT
                    s.StudentNumber,
                    CONCAT(s.LastName, ', ', s.FirstName) AS Student,
                    s.Cohort,
                    s.EnrollmentStatus,
                    a.AdviserName,
                    sl.CourseworkStatus,
                    sl.CompExamStatus,
                    sl.CapstoneStatus
                FROM Students s
                LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
                LEFT JOIN Student_Adviser sa ON s.StudentNumber = sa.StudentNumber
                LEFT JOIN Adviser a ON sa.AdviserID = a.AdviserID
                WHERE s.StudentNumber = %s
            """

            cursor.execute(query, (str(student_number),))
            student_data = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()

        # Normalize single record values if present
        if student_data:
            for col in ['CourseworkStatus', 'CompExamStatus', 'CapstoneStatus']:
                val = str(student_data.get(col, "")).strip().lower()
                if val in LIFECYCLE_STATUS_MAP:
                    student_data[col] = LIFECYCLE_STATUS_MAP[val]

        return student_data

    except Exception as e:
        print(f"Failed to fetch student details: {e}")
        return None

def get_enrollment_count(status_filter="All", cohort=None, program_id=None):
    """Returns the count of students matching the filters.

    Requires program_id — returns 0 if it is not provided.
    """
    if program_id is None:
        return 0

    try:
        conditions = ["ProgramID = %s"]
        params = [program_id]

        if status_filter not in ("All", "All Students", None, ""):
            conditions.append("EnrollmentStatus = %s")
            params.append(status_filter)

        if cohort and cohort != "All Cohorts":
            conditions.append("Cohort = %s")
            params.append(cohort)

        query = "SELECT COUNT(*) FROM Students WHERE " + " AND ".join(conditions)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            count = cursor.fetchone()[0]
            cursor.close()
        finally:
            conn.close()
        return count

    except Exception as e:
        print(f"Failed to fetch enrollment count: {e}")
        return 0
def get_available_cohorts(program_id=None):
    """Fetches distinct cohort values for the given program."""
    if program_id is None:
        return []

    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = (
                "SELECT DISTINCT Cohort FROM Students "
                "WHERE Cohort IS NOT NULL AND ProgramID = %s "
                "ORDER BY Cohort DESC"
            )
            cursor.execute(query, (program_id,))
            cohorts = [row[0] for row in cursor.fetchall()]
            cursor.close()
        finally:
            conn.close()
        return cohorts
    except Exception as e:
        print(f"Failed to fetch cohorts: {e}")
        return []


# ------------------------------------------------------------------
# Program (added for student_roster feature)
# Schema: ProgramID (int PK, AUTO_INCREMENT), ProgramCode (varchar UNIQUE, NOT NULL),
#         ProgramName (varchar NOT NULL), IsActive (tinyint DEFAULT 1),
#         CreatedAt (datetime DEFAULT CURRENT_TIMESTAMP)
# ------------------------------------------------------------------

def get_all_programs(active_only=True):
    """Fetches programs for dropdown filters.

    Args:
        active_only: If True, only returns IsActive = 1 rows (default).

    Returns:
        List of dicts:
            [{"ProgramID": int, "ProgramCode": str, "ProgramName": str,
              "IsActive": int, "CreatedAt": datetime}, ...]
    """
    try:
        query = """
            SELECT ProgramID, ProgramCode, ProgramName, IsActive, CreatedAt
            FROM Program
        """
        if active_only:
            query += " WHERE IsActive = 1"
        query += " ORDER BY ProgramName ASC"

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query)
            programs = cursor.fetchall()
            cursor.close()
        finally:
            conn.close()
        return programs

    except Exception as e:
        print(f"Failed to fetch programs: {e}")
        return []

def get_user_program(user_id):
    """Fetches the current program assigned to a user.

    Args:
        user_id: The UserID to look up.

    Returns:
        dict: {"ProgramID": int, "ProgramCode": str, "ProgramName": str, "IsActive": int}
              when a program is assigned and found.
        None: when the user exists but has no CurrentProgramID,
              OR when the user doesn't exist,
              OR when the referenced program row is missing.
    """
    if user_id is None or str(user_id).strip() == "":
        return None

    user_id = str(user_id).strip()

    try:
        query = """
            SELECT p.ProgramID, p.ProgramCode, p.ProgramName, p.IsActive
            FROM Users u
            JOIN Program p ON u.CurrentProgramID = p.ProgramID
            WHERE u.UserID = %s
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()
        return row  # None if no match

    except mysql.connector.Error as e:
        print(f"Failed to fetch user program: {format_mysql_error(e)}")
        return None

    except Exception as e:
        print(f"Failed to fetch user program: {e}")
        return None
def get_users_assigned_to_program(program_id):
    """UserIDs of every user whose CurrentProgramID = program_id.

    Used by the Program Instances console to show which Program Chair is assigned.
    """
    if program_id is None:
        return []
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT UserID FROM Users WHERE CurrentProgramID = %s",
                (program_id,),
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        print(f"Failed to fetch users for program {program_id}: {e}")
        return []
def create_program(program_code, program_name, is_active=1):
    """Inserts a new program into the Program table.

    Args:
        program_code: Unique code, e.g. "MBA", "BIA" (required, UNIQUE).
        program_name: Full display name, e.g. "Master of Business Administration" (required).
        is_active:    1 = active (default), 0 = inactive.

    Returns:
        (True, new_program_id) on success
        (False, error_message) on failure
    """
    # --- Validate inputs ---
    if not program_code or not str(program_code).strip():
        return False, "Program code is required."
    if not program_name or not str(program_name).strip():
        return False, "Program name is required."

    program_code = str(program_code).strip()
    program_name = str(program_name).strip()
    is_active = 1 if is_active else 0

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ProgramID auto-increments; CreatedAt uses table default CURRENT_TIMESTAMP.
        query = """
            INSERT INTO Program (ProgramCode, ProgramName, IsActive)
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, (program_code, program_name, is_active))

        new_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return True, new_id

    except mysql.connector.IntegrityError as e:
        # 1062 = duplicate key (program_code already exists)
        if e.errno == 1062:
            return False, f"Program code '{program_code}' already exists."
        return False, f"Integrity error: {e.msg}"

    except mysql.connector.Error as e:
        return False, format_mysql_error(e)

    except Exception as e:
        return False, f"Unexpected error: {e}"


def set_user_program(user_id, program_id):
    """Updates Users.CurrentProgramID for a given user.

    Schema confirmed:
        Users.CurrentProgramID  int, NULLABLE, MUL (FK to Program.ProgramID)

    Args:
        user_id:    The UserID of the user to update (required).
        program_id: The ProgramID to assign. Pass None or "" to clear the
                    assignment (sets CurrentProgramID = NULL).

    Returns:
        (True, None) on success
        (False, error_message) on failure
    """
    if user_id is None or str(user_id).strip() == "":
        return False, "User ID is required."

    user_id = str(user_id).strip()

    # Allow clearing the program by passing None / empty string
    if program_id is None or str(program_id).strip() == "":
        program_id_value = None
    else:
        try:
            program_id_value = int(program_id)
        except (TypeError, ValueError):
            return False, f"Invalid program ID: {program_id!r}"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "UPDATE Users SET CurrentProgramID = %s WHERE UserID = %s"
        cursor.execute(query, (program_id_value, user_id))

        # rowcount may be 0 if the value is already what we're setting it to
        # AND the user exists — so verify existence separately.
        if cursor.rowcount == 0:
            cursor.execute("SELECT 1 FROM Users WHERE UserID = %s", (user_id,))
            if cursor.fetchone() is None:
                cursor.close()
                conn.close()
                return False, f"No user found with UserID '{user_id}'."

        conn.commit()
        cursor.close()
        conn.close()
        return True, None

    except mysql.connector.IntegrityError as e:
        # 1452 = FK violation: program_id doesn't exist in Program
        if e.errno == 1452:
            return False, f"Program ID {program_id_value} does not exist."
        return False, f"Integrity error: {e.msg}"

    except mysql.connector.Error as e:
        return False, format_mysql_error(e)

    except Exception as e:
        return False, f"Unexpected error: {e}"


# ------------------------------------------------------------------
# Field-mapping validation (schema snapshot cache)
# ------------------------------------------------------------------
# ONE query against INFORMATION_SCHEMA loads every (table, column) pair of the
# current database. Validating a mapping is then an in-memory lookup, instead of
# a new connection + query per column on every Streamlit rerun.
_SCHEMA_TTL_SECONDS = 300       # how long a successful snapshot is trusted (refresh_schema_cache() forces a reload)
_SCHEMA_RETRY_SECONDS = 10      # wait before retrying after a failed load
_SCHEMA_CONNECT_TIMEOUT = 5     # fail fast if the DB host is unreachable

_schema_lock = threading.Lock()
_schema_cache = {"columns": frozenset(), "loaded_at": None, "ttl": 0, "error": None}

# ------------------------------------------------------------------
# US-13: View-Only / Edit permissions
# ------------------------------------------------------------------

def get_user_permission(user_id):
    """Return 'View Only' or 'Edit' for a user. Fails closed to 'View Only'."""
    if user_id is None or str(user_id).strip() == "":
        return "View Only"

    user_id = str(user_id).strip()

    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT RolePermission FROM Users WHERE UserID = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()

        if not row or not row.get("RolePermission"):
            return "View Only"
        return row["RolePermission"]

    except Exception:
        return "View Only"   # fail closed


def can_edit(user_id):
    """True when the user has 'Edit' permission."""
    return get_user_permission(user_id) == "Edit"


def log_permission_attempt(user_id):
    """Record a blocked write attempt by a View-Only user."""
    if user_id is None or str(user_id).strip() == "":
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Permission_Audit_Log (UserID) VALUES (%s)",
            (str(user_id).strip(),)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass   # logging must never break the flow


def set_user_permission(user_id, permission):
    """Set RolePermission ('View Only' | 'Edit') for a user."""
    if user_id is None or str(user_id).strip() == "":
        return False, "User ID is required."

    if permission not in ("View Only", "Edit"):
        return False, f"Invalid permission: {permission!r}"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Users SET RolePermission = %s WHERE UserID = %s",
            (permission, str(user_id).strip())
        )

        if cursor.rowcount == 0:
            cursor.execute("SELECT 1 FROM Users WHERE UserID = %s", (str(user_id).strip(),))
            if cursor.fetchone() is None:
                cursor.close()
                conn.close()
                return False, f"No user found with UserID '{user_id}'."

        conn.commit()
        cursor.close()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def search_users(query):
    """Search Users by UserID or name (partial, case-insensitive). Returns list of dicts."""
    if query is None:
        query = ""
    query = str(query).strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if not query:
            cursor.execute(
                "SELECT UserID, FirstName, LastName, Role, RolePermission "
                "FROM Users ORDER BY LastName, FirstName LIMIT 200"
            )
        else:
            like = f"%{query}%"
            cursor.execute(
                "SELECT UserID, FirstName, LastName, Role, RolePermission "
                "FROM Users "
                "WHERE UserID LIKE %s OR FirstName LIKE %s OR LastName LIKE %s "
                "   OR CONCAT(FirstName, ' ', LastName) LIKE %s "
                "ORDER BY LastName, FirstName LIMIT 200",
                (like, like, like, like)
            )

        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    except Exception as e:
        print(f"Failed to search users: {e}")
        return []

def _to_str(value):
    """Some connector versions return INFORMATION_SCHEMA text as bytes."""
    return value.decode() if isinstance(value, (bytes, bytearray)) else str(value)

def _load_schema_columns():
    """Reads every (table, column) pair of the current database in a single query."""
    conn = mysql.connector.connect(**db_config, connection_timeout=_SCHEMA_CONNECT_TIMEOUT)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE()"
        )
        rows = cursor.fetchall()
        cursor.close()
        return frozenset((_to_str(t).lower(), _to_str(c).lower()) for t, c in rows)
    finally:
        conn.close()

def _get_schema_columns(force=False):
    """Returns the cached set of (table, column) pairs, reloading it when stale or forced."""
    with _schema_lock:
        loaded_at = _schema_cache["loaded_at"]
        fresh = loaded_at is not None and (time.monotonic() - loaded_at) < _schema_cache["ttl"]

        if force or not fresh:
            try:
                columns = _load_schema_columns()
                _schema_cache.update(columns=columns, ttl=_SCHEMA_TTL_SECONDS, error=None)
            except mysql.connector.Error as err:
                _schema_cache.update(columns=frozenset(), ttl=_SCHEMA_RETRY_SECONDS,
                                     error=format_mysql_error(err))
            except Exception as e:
                _schema_cache.update(columns=frozenset(), ttl=_SCHEMA_RETRY_SECONDS, error=str(e))
            _schema_cache["loaded_at"] = time.monotonic()

        return _schema_cache["columns"]

def refresh_schema_cache():
    """Forces a fresh read of the database schema (e.g. after adding a column in MySQL)."""
    _get_schema_columns(force=True)

def get_schema_load_error():
    """Returns a readable message if the schema could not be read from MySQL, else None."""
    _get_schema_columns()
    return _schema_cache["error"]

def _parse_column_paths(full_column_path):
    """'dbo.Students.FirstName, dbo.Students.LastName' -> [('students','firstname'), ('students','lastname')].
    Returns None if the input is empty or any entry is malformed.
    """
    if not full_column_path or not full_column_path.strip():
        return None

    pairs = []
    for raw in full_column_path.split(","):
        raw = raw.strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(".")]
        if len(parts) < 2 or not parts[-2] or not parts[-1]:
            return None
        pairs.append((parts[-2].lower(), parts[-1].lower()))

    return pairs or None

def check_column_exists(full_column_path):
    """Parses single or comma-separated paths (e.g. 'dbo.Students.FirstName, dbo.Students.LastName')
    and checks if ALL columns exist in the current MySQL database (in-memory, uses the schema snapshot).
    """
    pairs = _parse_column_paths(full_column_path)
    if not pairs:
        return False

    known = _get_schema_columns()
    return all(pair in known for pair in pairs)

def find_invalid_mappings(mappings):
    """Returns [(field_label, typed_path), ...] for every mapping that doesn't resolve to a real column."""
    return [(label, path) for label, path in mappings.items() if not check_column_exists(path)]

def get_my_adviser_name(user_id):
    """Resolves the AdviserName linked to a given UserID, for US-23's
    auto-scoped "my advisees" roster filter.

    An adviser's login uses their AdviserID as the UserID (e.g. Users.UserID 'ADV0000001'
    = Adviser.AdviserID 'ADV0000001'), so the link needs no extra column.

    Args:
        user_id: The UserID of the logged-in user.

    Returns:
        str: the adviser's AdviserName, when this user has a linked Adviser row.
        None: when user_id is empty, the user has no Adviser row, or on error.
    """
    if user_id is None or str(user_id).strip() == "":
        return None

    user_id = str(user_id).strip()

    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT AdviserName FROM Adviser WHERE AdviserID = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()
        return row["AdviserName"] if row else None

    except mysql.connector.Error as e:
        print(f"Failed to fetch adviser name: {format_mysql_error(e)}")
        return None

    except Exception as e:
        print(f"Failed to fetch adviser name: {e}")
        return None


# ===========================================================================
# LIFECYCLE STATUS EDITING (Student Profile)
#
# Saving a status:
#   1. INSERT a row into that pillar's history table (StudentNumber, Status, UpdatedAt = NOW())
#   2. Read the student's latest history row for that pillar
#   3. UPDATE Student_Lifecycle: the pillar's status + its "...UpdatedAt" = that row's time
#   4. UPDATE Student_Lifecycle.LastUpdate = the most recent of the three "...UpdatedAt" columns
# All of it runs in ONE transaction, so the history and the lifecycle can't get out of sync.
# Column names are read from the database (information_schema), so small naming
# differences like CourseworkUpdateAt vs CourseworkUpdatedAt don't break it.
# ===========================================================================
LIFECYCLE_PILLARS = {
    "coursework": {"history": "Student_Course_Status_History", "status_col": "CourseworkStatus", "prefix": "coursework"},
    "compexam":   {"history": "CompExam_Status_History",       "status_col": "CompExamStatus",   "prefix": "compexam"},
    "capstone":   {"history": "Capstone_Status_History",       "status_col": "CapstoneStatus",   "prefix": "capstone"},
}
_LIFECYCLE_TABLE = "Student_Lifecycle"
# Time written to the history tables / Student_Lifecycle. Philippines = UTC+8 (no daylight saving).
from datetime import timezone as _tz, timedelta as _td
_APP_TZ = _tz(_td(hours=8))


def _now_local():
    return datetime.now(_APP_TZ).replace(tzinfo=None, microsecond=0)
_lifecycle_schema_cache = {"schema": None, "loaded_at": 0.0}
_LIFECYCLE_SCHEMA_TTL = 600  # seconds


def _enum_values(column_type):
    """"enum('A','B')" -> ['A', 'B']; anything else -> None."""
    ct = str(column_type or "")
    if not ct.lower().startswith("enum("):
        return None
    inner = ct[ct.index("(") + 1: ct.rindex(")")]
    return [v.strip().strip("'").replace("''", "'") for v in inner.split("','")] if inner else []


def _match_enum(value, allowed):
    """Case/spacing-insensitive match of a status to the values a column allows."""
    if allowed is None:
        return value
    norm = lambda v: str(v).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    for a in allowed:
        if norm(a) == norm(value):
            return a
    raise ValueError(f"'{value}' is not an allowed value ({', '.join(allowed)})")


def _get_lifecycle_schema(force=False):
    cache = _lifecycle_schema_cache
    if not force and cache["schema"] and (time.monotonic() - cache["loaded_at"]) < _LIFECYCLE_SCHEMA_TTL:
        return cache["schema"]

    tables = [_LIFECYCLE_TABLE] + [p["history"] for p in LIFECYCLE_PILLARS.values()]
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY, EXTRA "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            f"AND LOWER(TABLE_NAME) IN ({', '.join(['%s'] * len(tables))})",
            [t.lower() for t in tables],
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    dec = lambda v: v.decode() if isinstance(v, (bytes, bytearray)) else v
    for r in rows:
        for k in ("TABLE_NAME", "COLUMN_NAME", "COLUMN_TYPE", "COLUMN_KEY", "EXTRA"):
            r[k] = dec(r[k])
    cols, real_name = {}, {}
    for r in rows:
        cols.setdefault(r["TABLE_NAME"].lower(), []).append(r)
        real_name[r["TABLE_NAME"].lower()] = r["TABLE_NAME"]

    def col_name(r):
        return r["COLUMN_NAME"]

    life_cols = cols.get(_LIFECYCLE_TABLE.lower(), [])
    if not life_cols:
        raise RuntimeError(f"Table {_LIFECYCLE_TABLE} was not found in this database.")
    schema = {"lifecycle_table": real_name[_LIFECYCLE_TABLE.lower()], "pillars": {}, "last_col": None,
              "term_col": next((col_name(r) for r in life_cols if col_name(r).lower() == "termid"), None)}

    for r in life_cols:
        if col_name(r).lower().replace("_", "") in ("lastupdate", "lastupdated", "lastupdatedat", "lastupdateat"):
            schema["last_col"] = col_name(r)

    for key, p in LIFECYCLE_PILLARS.items():
        status_row = next((r for r in life_cols if col_name(r).lower() == p["status_col"].lower()), None)
        updated_row = next((r for r in life_cols
                            if col_name(r).lower().replace("_", "").startswith(p["prefix"])
                            and "update" in col_name(r).lower()), None)
        hist_cols = cols.get(p["history"].lower(), [])
        h = {col_name(r).lower(): r for r in hist_cols}
        pk = next((r for r in hist_cols if r["COLUMN_KEY"] == "PRI"), None)
        h_status = h.get("status")
        h_updated = next((r for n, r in h.items() if "update" in n), None)
        schema["pillars"][key] = {
            "status_col": col_name(status_row) if status_row else p["status_col"],
            "status_enum": _enum_values(status_row["COLUMN_TYPE"]) if status_row else None,
            "updated_col": col_name(updated_row) if updated_row else None,
            "history_table": real_name.get(p["history"].lower(), p["history"]) if hist_cols else None,
            "history_id": col_name(pk) if pk else None,
            "history_id_auto": bool(pk and "auto_increment" in str(pk["EXTRA"]).lower()),
            "history_student": col_name(h["studentnumber"]) if "studentnumber" in h else None,
            "history_status": col_name(h_status) if h_status else None,
            "history_status_enum": _enum_values(h_status["COLUMN_TYPE"]) if h_status else None,
            "history_updated": col_name(h_updated) if h_updated else None,
            "history_term": col_name(h["termid"]) if "termid" in h else None,
            "history_updated_type": str(h_updated["COLUMN_TYPE"]).lower() if h_updated else "",
        }

    cache["schema"], cache["loaded_at"] = schema, time.monotonic()
    return schema


def get_lifecycle_status_options(pillar, preferred):
    """The dropdown options for a pillar, spelled exactly the way the database stores them."""
    try:
        allowed = _get_lifecycle_schema()["pillars"][pillar]["status_enum"]
    except Exception:
        return list(preferred)
    out = []
    for v in preferred:
        try:
            out.append(_match_enum(v, allowed))
        except ValueError:
            continue
    return out or list(preferred)


def get_student_lifecycle_detail(student_number):
    """Current status + last-updated time of each pillar, plus LastUpdate, for one student."""
    try:
        schema = _get_lifecycle_schema()
        pillars = schema["pillars"]
        select = []
        for key, p in pillars.items():
            select.append(f"`{p['status_col']}` AS `{key}_status`")
            select.append(f"`{p['updated_col']}` AS `{key}_updated`" if p["updated_col"] else f"NULL AS `{key}_updated`")
        select.append(f"`{schema['last_col']}` AS `last_update`" if schema["last_col"] else "NULL AS `last_update`")
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"SELECT {', '.join(select)} FROM `{schema['lifecycle_table']}` WHERE StudentNumber = %s",
                (str(student_number),),
            )
            row = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        return row
    except Exception as e:
        print(f"Failed to fetch lifecycle detail: {e}")
        return None


def _alert_advisers(student_number):
    """US-37: after a status is saved, alert the student's adviser if it moved to a bad status."""
    try:
        from advisee_alerts import scan_status_changes   # imported here: advisee_alerts imports this module
        scan_status_changes(student_number)
    except Exception as e:
        print(f"US-37 advisee alert check failed: {e}")


def update_lifecycle_statuses(student_number, changes):
    """Save one or more pillar changes for a student.

    changes: {"coursework": "Pending", "compexam": "Passed", ...}
    Returns (True, message) or (False, error message). Nothing is saved if any step fails.
    """
    if not changes:
        return False, "Nothing to save."
    try:
        schema = _get_lifecycle_schema(force=True)
    except Exception as e:
        return False, f"Could not read the lifecycle tables: {e}"

    life = schema["lifecycle_table"]
    sn = str(student_number)
    conn = get_db_connection()
    try:
        if conn.in_transaction:
            conn.rollback()
        conn.start_transaction()
        cur = conn.cursor()
        for pillar, new_status in changes.items():
            p = schema["pillars"][pillar]
            missing = [k for k in ("history_table", "history_id", "history_student", "history_status", "history_updated")
                       if not p[k]]
            if missing:
                raise RuntimeError(f"{LIFECYCLE_PILLARS[pillar]['history']} is missing columns: {', '.join(missing)}")
            status_life = _match_enum(new_status, p["status_enum"])
            status_hist = _match_enum(new_status, p["history_status_enum"])
            ht, hid = p["history_table"], p["history_id"]

            # 1. log the change in the history table (TermID copied from Student_Lifecycle when both have it)
            now = _now_local()
            cols_ = [p["history_student"], p["history_status"], p["history_updated"]]
            vals_ = [sn, status_hist, now]
            if not p["history_id_auto"]:
                cur.execute(f"SELECT COALESCE(MAX(`{hid}`), 0) + 1 FROM `{ht}` FOR UPDATE")
                cols_.insert(0, hid)
                vals_.insert(0, cur.fetchone()[0])
            if p["history_term"] and schema["term_col"]:
                cur.execute(f"SELECT `{schema['term_col']}` FROM `{life}` WHERE StudentNumber = %s", (sn,))
                term_row = cur.fetchone()
                cols_.append(p["history_term"])
                vals_.append(term_row[0] if term_row else None)
            cur.execute(
                f"INSERT INTO `{ht}` ({', '.join(f'`{c}`' for c in cols_)}) "
                f"VALUES ({', '.join(['%s'] * len(vals_))})",
                vals_,
            )

            # 2. latest history row for this student
            cur.execute(
                f"SELECT `{p['history_updated']}` FROM `{ht}` WHERE `{p['history_student']}` = %s "
                f"ORDER BY `{hid}` DESC LIMIT 1",
                (sn,),
            )
            latest_time = cur.fetchone()[0]
            if p["history_updated_type"] == "date":   # history column only stores the day -> keep the real time here
                latest_time = now

            # 3. copy status + time into Student_Lifecycle
            sets, params = [f"`{p['status_col']}` = %s"], [status_life]
            if p["updated_col"]:
                sets.append(f"`{p['updated_col']}` = %s")
                params.append(latest_time)
            cur.execute(f"UPDATE `{life}` SET {', '.join(sets)} WHERE StudentNumber = %s", params + [sn])
            if cur.rowcount == 0:
                cur.execute(f"SELECT COUNT(*) FROM `{life}` WHERE StudentNumber = %s", (sn,))
                if cur.fetchone()[0] == 0:
                    raise RuntimeError(f"Student {sn} has no row in {life}.")

        # 4. LastUpdate = most recent of the three pillar times
        if schema["last_col"]:
            parts = [f"COALESCE(`{p['updated_col']}`, '1000-01-01')"
                     for p in schema["pillars"].values() if p["updated_col"]]
            if parts:
                cur.execute(
                    f"UPDATE `{life}` SET `{schema['last_col']}` = "
                    f"NULLIF(GREATEST({', '.join(parts)}), '1000-01-01') WHERE StudentNumber = %s",
                    (sn,),
                )
        conn.commit()
        cur.close()
        _alert_advisers(sn)   # US-37
        return True, f"Saved {len(changes)} change(s)."
    except Exception as e:
        conn.rollback()
        msg = format_mysql_error(e) if isinstance(e, mysql.connector.Error) else str(e)
        return False, f"Nothing was saved: {msg}"
    finally:
        conn.close()


# ===========================================================================
# ENROLLMENT STATUS EDITING (Student Profile)
#   1. INSERT into Enrollment_Status_History (StudentNumber, Status, UpdatedAt)
#   2. Read the student's latest history row
#   3. UPDATE Students: EnrollmentStatus + LastUpdate = that row's time
# One transaction, like the lifecycle statuses. Tables come from create_enrollment_history.sql.
# ===========================================================================
ENROLLMENT_HISTORY_TABLE = "Enrollment_Status_History"


def update_enrollment_status(student_number, new_status):
    """Returns (True, message) or (False, error message). Nothing is saved if any step fails."""
    sn = str(student_number)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) IN ('students', %s)",
            (ENROLLMENT_HISTORY_TABLE.lower(),),
        )
        dec = lambda v: v.decode() if isinstance(v, (bytes, bytearray)) else v
        info = {}
        for t, c, ty in cur.fetchall():
            info.setdefault(dec(t).lower(), {})[dec(c).lower()] = (dec(c), dec(ty))
        hist = info.get(ENROLLMENT_HISTORY_TABLE.lower())
        students = info.get("students", {})
        if not hist:
            return False, (f"Nothing was saved: table {ENROLLMENT_HISTORY_TABLE} doesn't exist yet. "
                           "Run create_enrollment_history.sql first.")
        status_students = _match_enum(new_status, _enum_values(students.get("enrollmentstatus", ("", ""))[1]))
        status_hist = _match_enum(new_status, _enum_values(hist.get("status", ("", ""))[1]))
        now = _now_local()

        # the column lookup above already opened a (read-only) transaction; close it first,
        # otherwise start_transaction() fails with "Transaction already in progress"
        if conn.in_transaction:
            conn.rollback()
        conn.start_transaction()
        cur.execute(
            f"INSERT INTO `{ENROLLMENT_HISTORY_TABLE}` (StudentNumber, Status, UpdatedAt) VALUES (%s, %s, %s)",
            (sn, status_hist, now),
        )
        cur.execute(
            f"SELECT UpdatedAt FROM `{ENROLLMENT_HISTORY_TABLE}` WHERE StudentNumber = %s "
            "ORDER BY HistoryID DESC LIMIT 1",
            (sn,),
        )
        latest_time = cur.fetchone()[0]
        sets, params = ["EnrollmentStatus = %s"], [status_students]
        if "lastupdate" in students:
            sets.append(f"`{students['lastupdate'][0]}` = %s")
            params.append(latest_time)
        cur.execute(f"UPDATE Students SET {', '.join(sets)} WHERE StudentNumber = %s", params + [sn])
        conn.commit()
        cur.close()
        _alert_advisers(sn)   # US-37
        return True, "Enrollment status saved."
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        msg = format_mysql_error(e) if isinstance(e, mysql.connector.Error) else str(e)
        return False, f"Enrollment status not saved: {msg}"
    finally:
        conn.close()

# ===========================================================================
# US-27: AT-RISK THRESHOLD (one number per program, used for every stage)
#
# Stored in Program_Stage.ExpectedDays (one row per program per stage).
# US-27 = the same threshold for every stage, so saving writes the number to
# all of that program's stage rows at once.
# The flags themselves come from the v_student_stage_flags view, which reads
# Program_Stage every time -> a new threshold applies immediately.
# ===========================================================================
PROGRAM_STAGES = [
    # Pillar,       StageLabel,           StageOrder
    ("Coursework", "Coursework Completion", 1),   # US-30: ETYSB tracker names
    ("CompExam",   "Comprehensive Exam", 2),
    ("Capstone",   "Capstone Paper",     3),
]


def get_program_threshold(program_id):
    """The program's At-Risk threshold in days, or None if it isn't set yet.

    If the stages somehow have different numbers, the smallest one is returned
    (the strictest one is what actually flags students first).
    """
    if program_id is None:
        return None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT MIN(ExpectedDays) FROM Program_Stage WHERE ProgramID = %s", (program_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return int(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"Failed to fetch threshold: {e}")
        return None


def set_program_threshold(user_id, program_id, days):
    """Set the At-Risk threshold for ALL stages of one program (US-27).

    Only users with Edit permission can do this; a blocked attempt is logged
    to Permission_Audit_Log (same as every other blocked write).
    Missing stage rows for the program are created first.

    Returns (True, message) or (False, error message).
    """
    if program_id is None:
        return False, "Pick a program first."
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        return False, "The threshold must be a whole number of days above 0."
    if not can_edit(user_id):
        log_permission_attempt(user_id)
        return False, "You have View Only access, so you can't change the threshold."

    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            # make sure the program has all 3 stage rows
            for pillar, label, order in PROGRAM_STAGES:
                cur.execute(
                    "INSERT INTO Program_Stage (ProgramID, Pillar, StageLabel, StageOrder, IsRequired, ExpectedDays) "
                    "SELECT %s, %s, %s, %s, 1, %s FROM DUAL "
                    "WHERE NOT EXISTS (SELECT 1 FROM Program_Stage WHERE ProgramID = %s AND Pillar = %s)",
                    (program_id, pillar, label, order, days, program_id, pillar),
                )
            # same number for every stage
            cur.execute("UPDATE Program_Stage SET ExpectedDays = %s WHERE ProgramID = %s", (days, program_id))
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return True, f"At-Risk threshold saved: {days} days in a single stage."
    except mysql.connector.IntegrityError as e:
        if e.errno == 1452:
            return False, f"Program ID {program_id} does not exist."
        return False, f"Integrity error: {e.msg}"
    except mysql.connector.Error as e:
        return False, format_mysql_error(e)
    except Exception as e:
        return False, f"Unexpected error: {e}"


def get_flagged_students(program_id=None):
    """Time in stage + At-Risk flag per student, from the v_student_stage_flags view.

    Columns: StudentNumber, ProgramID, current_stage, stage_label, stage_start,
             days_in_stage, expected_days, is_flagged (0/1), flag_reason.
    Returns an empty DataFrame on error (the dashboard then shows "—").
    """
    try:
        sql = "SELECT * FROM v_student_stage_flags"
        params = None
        if program_id is not None:
            sql += " WHERE ProgramID = %s"
            params = (program_id,)
        conn = get_db_connection()
        try:
            df = pd.read_sql(sql + " ORDER BY is_flagged DESC, days_in_stage DESC", conn, params=params)
        finally:
            conn.close()
        return df
    except Exception as e:
        print(f"Failed to fetch stage flags: {e}")
        return pd.DataFrame()


# ===========================================================================
# NIGHTLY DATA REFRESH (scheduled sync)
#   - Refresh runs every night at the time saved in Admin Configuration (default 02:00, Asia/Manila)
#   - A failed scheduled refresh is logged by trigger_data_sync() -> local error log (US-16)
#   - Manual "Refresh Now" (Student Roster) / "Run Sync Attempt" (Admin) still work for urgent updates
# The schedule + last-run info live in the App_Settings table (created automatically).
# A small background thread in the Streamlit server checks every 30 s whether tonight's run is due;
# a database "claim" makes sure it runs only once per day even if several app processes are running.
# ===========================================================================
SETTINGS_TABLE = "App_Settings"
DEFAULT_REFRESH_TIME = "02:00"
REFRESH_TIMEZONE_LABEL = "Asia/Manila"
_SCHEDULER_CHECK_SECONDS = 30
_scheduler_lock = threading.Lock()
_scheduler_started = False
_settings_table_ready = False   # CREATE TABLE only runs once per app process, not on every read
_last_handled_date = None       # SPEED: once today's run is done/claimed, skip the DB claim on later 30 s checks
_last_unreachable_logged = None  # date we already wrote a "database unreachable" row to the sync log (once per day)


def _ensure_settings_table(cur):
    global _settings_table_ready
    if _settings_table_ready:
        return
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SETTINGS_TABLE} (
            SettingKey   VARCHAR(64)  NOT NULL PRIMARY KEY,
            SettingValue VARCHAR(255) NOT NULL,
            UpdatedBy    VARCHAR(64)  NULL,
            UpdatedAt    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )
    _settings_table_ready = True


def get_settings(keys):
    """Read several App_Settings values with ONE connection + ONE query. Returns {key: value}."""
    keys = list(keys)
    if not keys:
        return {}
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            _ensure_settings_table(cur)
            cur.execute(
                f"SELECT SettingKey, SettingValue FROM {SETTINGS_TABLE} "
                f"WHERE SettingKey IN ({', '.join(['%s'] * len(keys))})",
                keys,
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()
        return {k: v for k, v in rows}
    except Exception as e:
        print(f"Failed to read settings: {e}")
        return {}


def get_setting(key, default=None):
    """Read one value from App_Settings (default if missing or on error)."""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            _ensure_settings_table(cur)
            cur.execute(f"SELECT SettingValue FROM {SETTINGS_TABLE} WHERE SettingKey = %s", (key,))
            row = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        return row[0] if row else default
    except Exception as e:
        print(f"Failed to read setting {key}: {e}")
        return default


def set_setting(key, value, user_id=None):
    """Insert or update one value in App_Settings."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        _ensure_settings_table(cur)
        cur.execute(
            f"INSERT INTO {SETTINGS_TABLE} (SettingKey, SettingValue, UpdatedBy) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE SettingValue = VALUES(SettingValue), UpdatedBy = VALUES(UpdatedBy)",
            (key, str(value), None if user_id is None else str(user_id)),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _parse_hhmm(text):
    """'02:00' -> (2, 0); raises ValueError if it isn't a valid 24-hour time."""
    hh, mm = str(text).strip().split(":")[:2]
    hh, mm = int(hh), int(mm)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("time must be between 00:00 and 23:59")
    return hh, mm


def get_refresh_schedule():
    """What the Admin page / sidebar show:
    {"time": "02:00", "timezone": "Asia/Manila", "last_run": "2026-09-29 02:00:04" | None,
     "last_status": "Success" | "Failed" | None}
    """
    vals = get_settings(["refresh_time", "last_scheduled_run", "last_scheduled_status"])   # one round trip
    time_txt = vals.get("refresh_time") or DEFAULT_REFRESH_TIME
    try:
        _parse_hhmm(time_txt)
    except Exception:
        time_txt = DEFAULT_REFRESH_TIME
    return {
        "time": time_txt,
        "timezone": REFRESH_TIMEZONE_LABEL,
        "last_run": vals.get("last_scheduled_run"),
        "last_status": vals.get("last_scheduled_status"),
    }


def set_refresh_time(user_id, hhmm):
    """Save the nightly refresh time ('HH:MM', Asia/Manila). Edit permission only; blocked attempts are logged.

    Returns (True, message) or (False, error message).
    """
    try:
        hh, mm = _parse_hhmm(hhmm)
    except Exception:
        return False, "Enter a valid time (HH:MM, 24-hour)."
    if not can_edit(user_id):
        log_permission_attempt(user_id)
        return False, "You have View Only access, so you can't change the refresh schedule."
    try:
        set_setting("refresh_time", f"{hh:02d}:{mm:02d}", user_id)
        return True, f"Data refresh scheduled nightly at {hh:02d}:{mm:02d} ({REFRESH_TIMEZONE_LABEL})."
    except mysql.connector.Error as e:
        return False, format_mysql_error(e)
    except Exception as e:
        return False, f"Unexpected error: {e}"


def _log_scheduler_unreachable(today, message):
    """The nightly refresh is due but the database can't be reached. Before, this only printed to the
    console, so the Sync Logs table never showed it. Now it is logged (FAILED), once per day, so it can
    be seen in Admin Config > System Sync Logs as soon as the connection works again."""
    global _last_unreachable_logged
    if _last_unreachable_logged == today:
        return
    _last_unreachable_logged = today
    try:
        log_sync_attempt_local("FAILED", error_message=f"Scheduled refresh could not start: {message}", login_id="SCHEDULED")
    except Exception as e:
        print(f"Could not write the sync log: {e}")


def run_scheduled_refresh_if_due(now=None):
    global _last_handled_date
    """Runs tonight's refresh if its time has passed and it hasn't run yet today. Returns True if it ran."""
    now = now or _now_local()
    try:
        hh, mm = _parse_hhmm(get_setting("refresh_time", DEFAULT_REFRESH_TIME) or DEFAULT_REFRESH_TIME)
    except Exception:
        hh, mm = _parse_hhmm(DEFAULT_REFRESH_TIME)
    if (now.hour, now.minute) < (hh, mm):
        return False

    today = now.date().isoformat()
    if _last_handled_date == today:
        return False
    # claim today's run in the database, so only ONE process runs it even if several are up
    try:
        conn = get_db_connection()
    except mysql.connector.Error as err:      # database unreachable (wrong host, DNS, server down, full...)
        _log_scheduler_unreachable(today, format_mysql_error(err))
        return False                           # not marked as handled -> it retries on the next 30 s check
    try:
        cur = conn.cursor()
        _ensure_settings_table(cur)
        cur.execute(
            f"INSERT IGNORE INTO {SETTINGS_TABLE} (SettingKey, SettingValue) VALUES ('last_scheduled_date', '')"
        )
        cur.execute(
            f"UPDATE {SETTINGS_TABLE} SET SettingValue = %s, UpdatedBy = 'SCHEDULER' "
            "WHERE SettingKey = 'last_scheduled_date' AND SettingValue <> %s",
            (today, today),
        )
        claimed = cur.rowcount == 1
        conn.commit()
        cur.close()
    finally:
        conn.close()
    _last_handled_date = today
    if not claimed:
        return False   # already ran today

    ok = trigger_data_sync(login_id="SCHEDULED")   # failures are logged there (US-16)
    try:
        set_setting("last_scheduled_run", _now_local().strftime("%Y-%m-%d %H:%M:%S"), "SCHEDULER")
        set_setting("last_scheduled_status", "Success" if ok else "Failed", "SCHEDULER")
    except Exception as e:
        print(f"Scheduled refresh ran but its status couldn't be saved: {e}")

    # US-48: nightly configuration backup, right after the refresh (a failure shows in System Sync Logs)
    try:
        from config_backup import create_backup   # imported here: config_backup imports this module
        backup_ok, backup_msg, _ = create_backup("SCHEDULER", "scheduled")
        if not backup_ok:
            log_sync_attempt_local("FAILED", error_message=f"Scheduled config backup: {backup_msg}",
                                   login_id="SCHEDULED")
    except Exception as e:
        print(f"Scheduled config backup failed: {e}")

    # US-36: email the Dean about any KPI that just went below its threshold (a failure shows in System Sync Logs)
    try:
        from kpi_alerts import check_kpi_alerts   # imported here: kpi_alerts imports this module
        alerts = check_kpi_alerts()
        if alerts["failed"] or (alerts["errors"] and not alerts["sent"]):
            log_sync_attempt_local("FAILED", error_message=f"KPI alert email: {alerts['errors'][0]}",
                                   login_id="SCHEDULED")
    except Exception as e:
        print(f"Scheduled KPI alert check failed: {e}")

    # US-37: advisee status alerts (catches status changes saved outside the dashboard too)
    try:
        from advisee_alerts import scan_status_changes   # imported here: advisee_alerts imports this module
        scan_status_changes()
    except Exception as e:
        print(f"Scheduled advisee alert check failed: {e}")
    return True


def _refresh_scheduler_loop():
    while True:
        try:
            run_scheduled_refresh_if_due()
        except Exception as e:
            print(f"Scheduled refresh check failed: {e}")
        reap_idle_connections()
        time.sleep(_SCHEDULER_CHECK_SECONDS)


def start_refresh_scheduler():
    """Starts the background checker once per app process (safe to call many times)."""
    global _scheduler_started
    if os.getenv("DISABLE_REFRESH_SCHEDULER") == "1":
        return
    with _scheduler_lock:
        if _scheduler_started:
            return
        threading.Thread(target=_refresh_scheduler_loop, name="nightly-refresh", daemon=True).start()
        _scheduler_started = True


# every page imports db_connect, so the nightly refresh starts as soon as the app is running
start_refresh_scheduler()
# ------------------------------------------------------------------
# US-29: Config-driven KPI tiles (stored as JSON on Program.KpiTiles)
# ------------------------------------------------------------------

DEFAULT_KPI_TILES = [
    {"key": "total_enrolled",     "label": "Total Enrolled",          "source": "total_enrolled",     "order": 1, "visible": True, "color": "#b91b21"},
    {"key": "on_time_rate",       "label": "On-Time Graduation Rate", "source": "on_time_rate",       "order": 2, "visible": True, "color": "#ffca06"},
    {"key": "overall_completion", "label": "Overall Completion",      "source": "overall_completion", "order": 3, "visible": True, "color": "#1F3864"},
    {"key": "remaining",          "label": "Remaining Students",      "source": "remaining",          "order": 4, "visible": True, "color": "#1F3864"},
    {"key": "at_risk",            "label": "Students at Risk",        "source": "at_risk",            "order": 5, "visible": True, "color": "#C62828"},
]


def get_kpi_tiles(program_id=None, visible_only=True):
    """Return the KPI tile list for a program.

    Reads Program.KpiTiles (JSON). Programs created later from the dashboard
    start with KpiTiles = NULL -> they fall back to DEFAULT_KPI_TILES.
    """
    import json as _json

    tiles = None
    if program_id is not None:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT KpiTiles FROM Program WHERE ProgramID = %s", (program_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if row and row.get("KpiTiles"):
                raw = row["KpiTiles"]
                tiles = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            tiles = None

    if not tiles:
        tiles = [dict(t) for t in DEFAULT_KPI_TILES]

    tiles = sorted(tiles, key=lambda t: int(t.get("order", 0)))
    if visible_only:
        tiles = [t for t in tiles if t.get("visible", True)]
    return tiles


def get_all_kpi_tiles(program_id=None):
    """Same as get_kpi_tiles but keeps hidden tiles too (for the Admin editor)."""
    return get_kpi_tiles(program_id=program_id, visible_only=False)


def save_kpi_tiles(program_id, tiles):
    """Persist a list of tile dicts to Program.KpiTiles as JSON.

    Args:
        program_id: ProgramID to update. Must not be None.
        tiles:      list[dict] with keys key, label, source, order, visible, color.

    Returns: (True, None) on success, (False, error_message) on failure.
    """
    if program_id is None:
        return False, "A specific program is required to save KPI tiles."

    try:
        import json as _json

        clean = []
        for i, t in enumerate(sorted(tiles, key=lambda x: int(x.get("order", 0))), start=1):
            clean.append({
                "key":     str(t.get("key", "")).strip().lower().replace(" ", "_"),
                "label":   str(t.get("label", "")).strip(),
                "source":  str(t.get("source", "")).strip(),
                "order":   i,
                "visible": bool(t.get("visible", True)),
                "color":   str(t.get("color", "#1F3864")).strip(),
            })

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Program SET KpiTiles = %s WHERE ProgramID = %s",
            (_json.dumps(clean), program_id)
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT 1 FROM Program WHERE ProgramID = %s", (program_id,))
            if cursor.fetchone() is None:
                cursor.close()
                conn.close()
                return False, f"No program found with ProgramID {program_id}."
        conn.commit()
        cursor.close()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def reset_kpi_tiles(program_id):
    """Clear Program.KpiTiles so the program falls back to DEFAULT_KPI_TILES."""
    if program_id is None:
        return False, "A specific program is required."
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Program SET KpiTiles = NULL WHERE ProgramID = %s", (program_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


# ===========================================================================
# US-30: PROGRAM-SPECIFIC STAGE LABELS (terminology)
#
#   Each program can rename its 3 stages (e.g. "Capstone Paper" -> "Thesis").
#   Labels live in Program_Stage.StageLabel (one row per program per stage),
#   the same rows that hold the At-Risk threshold (ExpectedDays).
#   Every page asks get_stage_labels(program_id) for the names, so one change
#   in Admin Config shows up everywhere. The v_student_stage_flags view also
#   reads StageLabel, so the At-Risk reasons use the new names too.
# ===========================================================================

# Default names = the ETYSB tracker's existing terms (used when a program has no label saved,
# and when a page shows "All Programs").
DEFAULT_STAGE_LABELS = {
    "Coursework": "Coursework Completion",
    "CompExam":   "Comprehensive Exam",
    "Capstone":   "Capstone Paper",
}
STAGE_LABEL_MAX_LENGTH = 50
_STAGE_ORDER_BY_PILLAR = {"Coursework": 1, "CompExam": 2, "Capstone": 3}


def get_stage_labels(program_id=None):
    """{"Coursework": ..., "CompExam": ..., "Capstone": ...} for one program.

    program_id=None (e.g. "All Programs") or any error -> the default labels.
    A stage with no saved label also falls back to its default.
    """
    labels = dict(DEFAULT_STAGE_LABELS)
    if program_id is None:
        return labels
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT Pillar, StageLabel FROM Program_Stage WHERE ProgramID = %s", (program_id,))
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()
    except Exception as e:
        print(f"Failed to fetch stage labels: {e}")
        return labels

    by_lower = {k.lower(): k for k in DEFAULT_STAGE_LABELS}   # 'coursework' / 'Coursework' both match
    for pillar, label in rows:
        pillar = pillar.decode() if isinstance(pillar, (bytes, bytearray)) else str(pillar)
        key = by_lower.get(pillar.strip().lower())
        if key and label is not None and str(label).strip():
            labels[key] = str(label).strip()
    return labels


def set_stage_label(user_id, program_id, pillar, label):
    """Rename one stage for one program. Edit permission only (blocked attempts are logged).

    Returns (True, message) or (False, error message).
    """
    if program_id is None:
        return False, "Pick a program first."
    if pillar not in DEFAULT_STAGE_LABELS:
        return False, f"Unknown stage: {pillar!r}"
    label = str(label or "").strip()
    if not label:
        return False, "A stage label can't be empty."
    if len(label) > STAGE_LABEL_MAX_LENGTH:
        return False, f"Keep stage labels under {STAGE_LABEL_MAX_LENGTH} characters."
    if not can_edit(user_id):
        log_permission_attempt(user_id)
        return False, "You have View Only access, so you can't change stage labels."

    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            # Row already there (usual case) -> only the label changes.
            # No row yet -> create it, reusing the program's current At-Risk threshold.
            cur.execute(
                "INSERT INTO Program_Stage (ProgramID, Pillar, StageLabel, StageOrder, IsRequired, ExpectedDays) "
                "VALUES (%s, %s, %s, %s, 1, %s) "
                "ON DUPLICATE KEY UPDATE StageLabel = VALUES(StageLabel)",
                (program_id, pillar, label, _STAGE_ORDER_BY_PILLAR[pillar], get_program_threshold(program_id)),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return True, f'Saved "{label}".'
    except mysql.connector.IntegrityError as e:
        if e.errno == 1452:
            return False, f"Program ID {program_id} does not exist."
        return False, f"Integrity error: {e.msg}"
    except mysql.connector.Error as e:
        return False, format_mysql_error(e)
    except Exception as e:
        return False, f"Unexpected error: {e}"

def get_student_email(student_number):
    """The student's email address (Students.StudentEmail), or None if it's blank / not found."""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT StudentEmail FROM Students WHERE StudentNumber = %s", (str(student_number),))
            row = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        email = (row[0] if row else None) or ""
        email = email.decode() if isinstance(email, (bytes, bytearray)) else str(email)
        return email.strip() or None
    except Exception as e:
        print(f"Failed to fetch student email: {e}")
        return None
# ------------------------------------------------------------------
# US-42: Program Instances console
# ------------------------------------------------------------------

def get_program_instances():
    """Every program with its owner and status, for the admin console.

    Returns a list of dicts:
      {ProgramID, ProgramCode, ProgramName, OwnerUserID, OwnerName,
       IsActive, CreatedAt, StudentCount}
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                p.ProgramID,
                p.ProgramCode,
                p.ProgramName,
                p.OwnerUserID,
                CONCAT(u.FirstName, ' ', u.LastName) AS OwnerName,
                u.Email                              AS OwnerEmail,
                p.IsActive,
                p.CreatedAt,
                (SELECT COUNT(*) FROM Students s WHERE s.ProgramID = p.ProgramID) AS StudentCount,
                -- the Program Chair (Users.CurrentProgramID = p.ProgramID)
                (SELECT cu.UserID FROM Users cu
                  WHERE cu.CurrentProgramID = p.ProgramID AND cu.Role = 'Program_Chair'
                  LIMIT 1) AS ChairUserID
            FROM Program p
            LEFT JOIN Users u ON u.UserID = p.OwnerUserID
            ORDER BY p.IsActive DESC, p.ProgramName ASC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except mysql.connector.Error as e:
        print(f"Failed to fetch program instances: {e}")
        return []


def set_program_owner(program_id, user_id):
    """Assign (or clear) the owner of a program. Pass user_id=None to clear."""
    if program_id is None:
        return False, "A program is required."
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Program SET OwnerUserID = %s WHERE ProgramID = %s",
            (None if user_id in (None, "") else str(user_id).strip(), program_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True, None
    except mysql.connector.Error as e:
        return False, str(e)

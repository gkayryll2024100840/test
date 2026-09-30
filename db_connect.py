import os
import time
import threading
import mysql.connector 
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

def get_db_connection():
    """Return a live MySQL connection using the shared db_config.
    Callers are responsible for closing the connection.
    """
    return mysql.connector.connect(**db_config)

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

        with open("last_sync.txt", "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
    """Fetches the roster filtered by the given program ID.

    If program_id is None, returns an empty DataFrame.
    """
    if program_id is None:
        return pd.DataFrame()

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

        # 3. Run the program-scoped query
        conn = mysql.connector.connect(**db_config)
        query = """
            SELECT 
                s.StudentNumber,
                CONCAT(s.FirstName, ' ', s.LastName) AS Student,
                s.Cohort,
                s.EnrollmentStatus,
                a.AdviserName AS Adviser,
                sl.CourseworkStatus,
                sl.CompExamStatus,
                sl.CapstoneStatus,
                sl.LastUpdate
            FROM Students s
            LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
            LEFT JOIN (
                -- students with 2 advisers -> one row, e.g. "Dr. A, Dr. B"
                SELECT sa.StudentNumber,
                       GROUP_CONCAT(a.AdviserName ORDER BY a.AdviserName SEPARATOR ', ') AS AdviserName
                FROM Student_Adviser sa
                JOIN Adviser a ON sa.AdviserID = a.AdviserID
                GROUP BY sa.StudentNumber
            ) a ON a.StudentNumber = s.StudentNumber
            WHERE s.ProgramID = %s
        """
        df = pd.read_sql(query, conn, params=(program_id,))
        conn.close()
        return df

    except Exception as e:
        print(f"Mapping validation failed: {e}")
        raise e

def get_last_updated_time():
    """Checks last_sync.txt for the last successful sync timestamp."""
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
        conn = mysql.connector.connect(**db_config)
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
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = ["ProgramID = %s"]
        params = [program_id]

        if status_filter not in ("All", "All Students", None, ""):
            conditions.append("EnrollmentStatus = %s")
            params.append(status_filter)

        if cohort and cohort != "All Cohorts":
            conditions.append("Cohort = %s")
            params.append(cohort)

        query = "SELECT COUNT(*) FROM Students WHERE " + " AND ".join(conditions)

        cursor.execute(query, tuple(params))
        count = cursor.fetchone()[0]
        cursor.close()
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
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = (
            "SELECT DISTINCT Cohort FROM Students "
            "WHERE Cohort IS NOT NULL AND ProgramID = %s "
            "ORDER BY Cohort DESC"
        )
        cursor.execute(query, (program_id,))
        cohorts = [row[0] for row in cursor.fetchall()]
        cursor.close()
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
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT ProgramID, ProgramCode, ProgramName, IsActive, CreatedAt
            FROM Program
        """
        if active_only:
            query += " WHERE IsActive = 1"
        query += " ORDER BY ProgramName ASC"

        cursor.execute(query)
        programs = cursor.fetchall()
        cursor.close()
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
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT p.ProgramID, p.ProgramCode, p.ProgramName, p.IsActive
            FROM Users u
            JOIN Program p ON u.CurrentProgramID = p.ProgramID
            WHERE u.UserID = %s
        """
        cursor.execute(query, (user_id,))
        row = cursor.fetchone()

        cursor.close()
        conn.close()
        return row  # None if no match

    except mysql.connector.Error as e:
        print(f"Failed to fetch user program: {format_mysql_error(e)}")
        return None

    except Exception as e:
        print(f"Failed to fetch user program: {e}")
        return None
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
        conn = mysql.connector.connect(**db_config)
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
        conn = mysql.connector.connect(**db_config)
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
_SCHEMA_TTL_SECONDS = 60        # how long a successful snapshot is trusted
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
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT RolePermission FROM Users WHERE UserID = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        cursor.close()
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
 
    Schema assumption: Adviser.UserID (int, NULLABLE, FK to Users.UserID)
    links an Adviser row to the login that IS that adviser. If this column
    doesn't exist yet on your live table, add it first:
        ALTER TABLE Adviser ADD COLUMN UserID INT NULL;
        ALTER TABLE Adviser ADD FOREIGN KEY (UserID) REFERENCES Users(UserID);
 
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
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT AdviserName FROM Adviser WHERE UserID = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        cursor.close()
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
    conn = mysql.connector.connect(**db_config)
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
        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT {', '.join(select)} FROM `{schema['lifecycle_table']}` WHERE StudentNumber = %s",
            (str(student_number),),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception as e:
        print(f"Failed to fetch lifecycle detail: {e}")
        return None


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
    conn = mysql.connector.connect(**db_config)
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
    conn = mysql.connector.connect(**db_config)
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
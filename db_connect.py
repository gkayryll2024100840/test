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
def get_student_roster_data():
    try:
        # 1. Load the mappings from the JSON file
        mappings = load_mappings()
        
        # 2. Validate EVERY mapped field against the cached schema snapshot (no per-field DB round trips)
        invalid = find_invalid_mappings(mappings)
        if invalid:
            schema_error = get_schema_load_error()
            if schema_error:
                raise ValueError(f"Could not verify field mappings: {schema_error}")
            details = "; ".join(f"'{label}': '{path}'" for label, path in invalid)
            raise ValueError(f"Invalid or unverified mapping(s) - {details}")

        # 3. If everything is valid, run the database query normally
        conn = mysql.connector.connect(**db_config)
        query = """
            SELECT 
                s.StudentNumber,
                CONCAT(s.FirstName, ' ', s.LastName) AS Student,
                s.Cohort,
                s.EnrollmentStatus,
                a.AdvisorName AS Advisor,
                sl.CourseworkStatus,
                sl.CompExamStatus,
                sl.CapstoneStatus
            FROM Students s
            LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
            LEFT JOIN Advisor a ON sl.AdvisorID = a.AdvisorID
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df

    except Exception as e:
        print(f"Mapping validation failed: {e}")
        raise e  # This passes the error straight to your student roster page!

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
        
        query = """
            SELECT 
                s.StudentNumber,
                CONCAT(s.LastName, ', ', s.FirstName) AS Student,
                s.Cohort,
                s.EnrollmentStatus,
                a.AdvisorName,
                sl.CourseworkStatus,
                sl.CompExamStatus,
                sl.CapstoneStatus
            FROM Students s
            LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
            LEFT JOIN Advisor a ON sl.AdvisorID = a.AdvisorID
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

def get_enrollment_count(status_filter="All", cohort=None):
    """
    Returns the count of MBA students based on EnrollmentStatus filter,
    optionally narrowed to a specific cohort.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []

        if status_filter not in ("All", "All Students", None, ""):
            conditions.append("EnrollmentStatus = %s")
            params.append(status_filter)

        if cohort and cohort != "All Cohorts":
            conditions.append("Cohort = %s")
            params.append(cohort)

        query = "SELECT COUNT(*) FROM Students"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, tuple(params) if params else None)
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    except Exception as e:
        print(f"Failed to fetch enrollment count: {e}")
        return 0

def get_available_cohorts():
    """Fetches distinct cohort values for the Student Roster dropdown filter."""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = "SELECT DISTINCT Cohort FROM Students WHERE Cohort IS NOT NULL ORDER BY Cohort DESC"
        cursor.execute(query)
        cohorts = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return cohorts
    except Exception as e:
        print(f"Failed to fetch cohorts: {e}")
        return []

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
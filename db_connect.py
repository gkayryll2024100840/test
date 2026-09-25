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
                sl.CapstoneStatus
            FROM Students s
            LEFT JOIN Student_Lifecycle sl ON s.StudentNumber = sl.StudentNumber
            LEFT JOIN Student_Adviser sa ON s.StudentNumber = sa.StudentNumber
            LEFT JOIN Adviser a ON sa.AdviserID = a.AdviserID
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
 
import os
import mysql.connector 
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv 
from system_log import log_sync_attempt_local, get_system_logs_local, get_max_retry_count_local

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

        # Normalize lifecycle columns for US-07, US-08, and US-09
        for col in ['CourseworkStatus', 'CompExamStatus', 'CapstoneStatus']:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .map(LIFECYCLE_STATUS_MAP)
                    .fillna(df[col])
                )

        return df
    except Exception as e:
        print(f"Failed to fetch roster data: {e}")
        return pd.DataFrame()

# Checks last_sync.txt for the last successful sync timestamp
def get_last_updated_time():
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

def get_enrollment_count(status_filter="All"):
    """Fetches the total count of MBA students based on EnrollmentStatus filter."""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        if status_filter == "All":
            query = "SELECT COUNT(*) FROM Students"
            cursor.execute(query)
        else:
            query = "SELECT COUNT(*) FROM Students WHERE EnrollmentStatus = %s"
            cursor.execute(query, (status_filter,))
            
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

def check_column_exists(full_column_path):
    """Parses single or comma-separated paths (e.g. 'dbo.Students.FirstName, dbo.Students.LastName')
    and checks if ALL columns exist in the MySQL database.
    """
    if not full_column_path or not full_column_path.strip():
        return False

    # Split on commas and strip whitespace so "FirstName, LastName" works
    raw_paths = [p.strip() for p in full_column_path.split(",") if p.strip()]

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE LOWER(TABLE_NAME) = LOWER(%s)
              AND LOWER(COLUMN_NAME) = LOWER(%s)
        """

        for single_path in raw_paths:
            parts = single_path.split(".")
            if len(parts) < 2:
                return False

            table_name = parts[-2]
            column_name = parts[-1]

            cursor.execute(query, (table_name, column_name))
            result = cursor.fetchone()

            # If ANY individual column in the list doesn't exist, fail validation
            if not result or result[0] == 0:
                print(f"[check_column_exists] NOT FOUND: {table_name}.{column_name}")
                return False

        return True

    except Exception as e:
        # Visible error so silent failures don't happen anymore
        print(f"[check_column_exists] error for '{full_column_path}': {e}")
        return False

    finally:
        # Always clean up, even on early return
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

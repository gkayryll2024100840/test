import os
import mysql.connector 
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv 
from system_log import log_sync_attempt_local, get_system_logs_local, get_max_retry_count_local

#Load database credentials from .env file into memory 
load_dotenv(override=True)  

# Dictionary mappping environment variables. Reused when connecting to MySQL database.
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306))
}

#can python successfully talk to SQL DB?
def trigger_data_sync(login_id=None):
    """Attempts data sync with Aiven MySQL, logging failures locally if connection fails."""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        #Tests the connection to the cloud database by running this query
        cursor.execute("SELECT * FROM Students LIMIT 1")
        cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Successful sync updates last_sync.txt and returns true
        with open("last_sync.txt", "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return True  

    # Handle MySQL-specific errors and log them locally    
    except mysql.connector.Error as err:
        error_code = err.errno

        if error_code == 1045:
            msg = "Authentication failed: Check database username or password in .env"
        elif error_code == 1049:
            msg = "Database not found: Verify DB_NAME in your environment configuration"
        elif error_code == 1146:
            msg = "Schema error: Required database table is missing"
        elif error_code in (2003, 2026):
            msg = "Connection timeout to SQL Server host"
        elif error_code in (2013, 2006):
            msg = "Network socket closed unexpected during bulk data transfer"
        else:
            msg = f"Database error ({error_code}): {err.msg}"
            
        # If sync fails, "FAILED" is logged in the local SQLite database (under the column "Status"with the error message and session ID
        log_sync_attempt_local("FAILED", error_message=msg, login_id=login_id)
        return False

    # all other sync failures that are not definied in the if statement are logged here   
    except Exception as e:
        log_sync_attempt_local("FAILED", error_message=str(e), login_id=login_id)
        return False

# Retrieve system_logs.py for admin view. usueful for centralized retrieval 
def get_system_logs():
    """Wrapper to pull logs from local SQLite storage for admin view."""
    return get_system_logs_local()

def get_max_retry_count(login_id):
    """Wrapper to check retry count from local storage."""
    return get_max_retry_count_local(login_id)

#connects to database > queries rows from Students table > converts results into a Pandas Dataframe  
def get_students_data():
    try:
        conn = mysql.connector.connect(**db_config)
        query = "SELECT * FROM Students"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        print(f"Failed to fetch students: {e}")
        return pd.DataFrame()

#checks last_sync.txt for the last successful sync timestamp. Returns "No sync recorded" if file doesn't exist or is empty.
def get_last_updated_time():
    try:
        if os.path.exists("last_sync.txt"):
            with open("last_sync.txt", "r") as f:
                return f.read().strip()
        return "No sync recorded"
    except Exception:
        return "Unavailable"

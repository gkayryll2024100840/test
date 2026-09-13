import sqlite3 #local file data storage for system logs
from datetime import datetime

DB_NAME = "local_logs.db"

#SQL Lite: creates a local database and table for system logs. This is used to track sync attempts and errors for the admin view (US-16).
def init_local_log_db():
    """Initializes the local SQLite system logs database and table."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor() #use cursor to execute SQL commands
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS System_Logs (
            RowID INTEGER PRIMARY KEY AUTOINCREMENT,
            LoginID TEXT,
            Timestamp TEXT,
            Status TEXT,
            ErrorMessage TEXT,
            RetryCount INTEGER
        )
    """)
    conn.commit()
    conn.close()

#saves an error log whenever cloud sync fails. This is used for the admin view (US-16) to track sync attempts and errors.
def log_sync_attempt_local(status, error_message=None, login_id=None):
    """Writes failed sync attempts to the local SQLite log table."""
    init_local_log_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    #When a sync fails right now, this code checks: "How many times has this user already failed in the past?"
    #it adds 1 to that number and saves it in the RetryCount column. 
    current_retry = 1
    if login_id:
        cursor.execute("SELECT MAX(RetryCount) FROM System_Logs WHERE LoginID = ?", (login_id,))
        result = cursor.fetchone()
        if result and result[0] is not None:
            current_retry = result[0] + 1

    #logs the failed sync attempt with the session ID, timestamp, status, error message, and retry count
    query = """
        INSERT INTO System_Logs (LoginID, Timestamp, Status, ErrorMessage, RetryCount) 
        VALUES (?, ?, ?, ?, ?)
    """
    ## Safely insert the log data into the database using placeholders
    cursor.execute(query, (login_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, error_message, current_retry))
    conn.commit()
    conn.close()


def get_system_logs_local():
    """Fetches system logs from the local SQLite database for the admin screen."""
    init_local_log_db() #checks to make sure database and table exist before trying to read them
    conn = sqlite3.connect(DB_NAME) #opens a connection to the local SQLite database
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    #grabs 20 most recent logs (from newest to oldest) and displays it in the IT_screen.py
    cursor.execute("SELECT * FROM System_Logs ORDER BY Timestamp DESC, RowID DESC LIMIT 20")
    rows = cursor.fetchall()
    logs = [dict(row) for row in rows]
    conn.close()
    return logs

#check retry counts (just reads it doesnt insert anything)
def get_max_retry_count_local(login_id):
    """Checks the maximum retry count for the active session from local logs."""
    init_local_log_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(RetryCount) FROM System_Logs WHERE LoginID = ?", (login_id,))
    res = cursor.fetchone() #fetch one row
    conn.close()
    return res[0] if res and res[0] is not None else 0 
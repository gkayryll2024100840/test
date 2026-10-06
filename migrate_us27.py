"""One-time migration for US-27. Run once from VS Code's terminal, not repeatedly."""
from db_connect import get_db_connection

def column_exists(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column)
    )
    return cursor.fetchone() is not None

conn = get_db_connection()
cursor = conn.cursor()

if column_exists(cursor, "Program", "AtRiskThresholdDays"):
    print("Column already exists — nothing to do.")
else:
    cursor.execute("ALTER TABLE Program ADD COLUMN AtRiskThresholdDays INT NOT NULL DEFAULT 180")
    conn.commit()
    print("Added Program.AtRiskThresholdDays (default 180).")

cursor.close()
conn.close()
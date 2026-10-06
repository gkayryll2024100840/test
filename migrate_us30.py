"""One-time seed for US-30. Run once from VS Code's terminal."""
from db_connect import get_db_connection

# These match the ETYSB tracker's existing terms — the exact strings
# currently hardcoded in student_profile.py's PILLARS list.
DEFAULT_LABELS = [
    ("coursework", "Coursework Completion", 1),
    ("compexam",   "Comprehensive Exam", 2),
    ("capstone",  "Capstone Paper",   3)
]

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("SELECT ProgramID FROM Program WHERE ProgramCode = 'MBA'")
row = cursor.fetchone()
if not row:
    print("MBA program not found - nothing seeded.")
else:
    program_id = row[0]
    for pillar, label, order in DEFAULT_LABELS:
        cursor.execute(
            "SELECT 1 FROM Program_Stage WHERE ProgramID = %s AND Pillar = %s",
            (program_id, pillar)
        )
        if cursor.fetchone():
            print(f"{pillar}: already exists, left untouched.")
            continue
        cursor.execute(
            "INSERT INTO Program_Stage (ProgramID, Pillar, StageLabel, StageOrder, IsRequired) "
            "VALUES (%s, %s, %s, %s, 1)",
            (program_id, pillar, label, order)
        )
        print(f"{pillar}: seeded as '{label}'.")
    conn.commit()

cursor.close()
conn.close()
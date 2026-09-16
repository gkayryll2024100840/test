import json
import os

CONFIG_FILE = "field_mappings.json"

DEFAULT_MAPPINGS = {
    "Student ID": "dbo.Students.StudentNumber",
    "Student Name": "dbo.Students.FirstName, dbo.Students.LastName",
    "Cohort": "dbo.Students.Cohort",
    "Coursework Status": "dbo.Student_Lifecycle.CourseworkStatus",
    "Comprehensive Exam Status": "dbo.Student_Lifecycle.CompExamStatus",
    "Capstone Status": "dbo.Student_Lifecycle.CapstoneStatus",
    "Assigned Advisor": "dbo.Advisor.AdvisorName",
}

def load_mappings():
  """Loads field mappings from persistent storage."""
  if os.path.exists(CONFIG_FILE):
    try:
      with open(CONFIG_FILE, "r") as f:
        return json.load(f)
    except Exception:
      return DEFAULT_MAPPINGS
  return DEFAULT_MAPPINGS


def save_mappings(mappings):
  """Saves updated field mappings to persistent storage."""
  with open(CONFIG_FILE, "w") as f:
    json.dump(mappings, f, indent=4)
import json
import os


CONFIG_FILE = "field_mappings.json"

DEFAULT_MAPPINGS = {
    "Student ID": "dbo.Student.StudentID",
    "Student Name": "dbo.Student.FullName",
    "Cohort": "dbo.Enrollment.CohortLabel",
    "Coursework Status": "dbo.CourseworkTracking.Status",
    "Comprehensive Exam Status": "dbo.CompExamTracking.Status",
    "Capstone Status": "dbo.CapstoneTracking.Status",
    "Assigned Advisor": "dbo.AdvisorAssignment.AdvisorName",
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
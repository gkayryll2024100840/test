-- Create database
CREATE DATABASE IF NOT EXISTS defaultdb;
USE defaultdb;

-- Course (Parent table)
CREATE TABLE Course (
    CourseCode VARCHAR(10) PRIMARY KEY, 
    CourseName VARCHAR(100) NOT NULL
);

-- Advisor (Parent table)
CREATE TABLE Advisor (
    AdvisorID VARCHAR(10) PRIMARY KEY,
    AdvisorName VARCHAR(100) NOT NULL
);

-- Students (Parent table)
CREATE TABLE Students (
    StudentNumber BIGINT PRIMARY KEY CHECK (StudentNumber BETWEEN 1000000000 AND 9999999999),
    StudentEmail VARCHAR(100) NOT NULL,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    Cohort VARCHAR(6),
    EnrollmentStatus ENUM('Enrolled','Conditionally Enrolled') NOT NULL
);

-- Student Lifecycle (Child table)
CREATE TABLE Student_Lifecycle (
    StudentNumber BIGINT,
    AdvisorID VARCHAR(10),
    CourseworkStatus ENUM('Completed','Cancelled','Pending'),
    CompExamStatus ENUM('passed','incomplete','in-progress'),
    CapstoneStatus ENUM('In-Progress','Defended for Completion'),
    PRIMARY KEY (StudentNumber, AdvisorID),
    FOREIGN KEY (StudentNumber) REFERENCES Students(StudentNumber) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (AdvisorID) REFERENCES Advisor(AdvisorID) ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Student Course Status (Child table)
CREATE TABLE Student_Course_Status (
    StudentNumber BIGINT NOT NULL, 
    CourseCode VARCHAR(10) NOT NULL,
    Status ENUM('done','incomplete','abs/failed','not yet taken', 'current load', 'cancelled') NOT NULL,
    PRIMARY KEY (StudentNumber, CourseCode),
    FOREIGN KEY (StudentNumber) REFERENCES Students(StudentNumber) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (CourseCode) REFERENCES Course(CourseCode) ON UPDATE CASCADE ON DELETE CASCADE
);

-- Advisor Notes (Child table)
CREATE TABLE Advisor_Notes (
    NoteID INT AUTO_INCREMENT PRIMARY KEY,
    StudentNumber BIGINT NOT NULL,
    AdvisorID VARCHAR(10),
    NoteText TEXT,
    NoteDate DATE DEFAULT (CURRENT_DATE),
    FOREIGN KEY (StudentNumber) REFERENCES Students(StudentNumber) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (AdvisorID) REFERENCES Advisor(AdvisorID) ON UPDATE CASCADE ON DELETE SET NULL
);

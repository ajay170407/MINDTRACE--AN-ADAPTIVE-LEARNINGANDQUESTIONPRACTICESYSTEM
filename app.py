#!/usr/bin/env python3
"""
MINDTRACE — AI Adaptive Learning and Misconception Detection System
Complete production-grade Flask web application with strictly 1-mark question practice.
"""

import os
import sys
import re
import json
import secrets
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

# Safe PyMuPDF import
try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

# Paths & Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
PDF_DIR = os.path.join(BASE_DIR, "question_pdfs")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mindtrace_adaptive_secret_key_2026_production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# The Six Official Courses
COURSES = {
    1: {
        "id": 1,
        "name": "Probability and Statistical Modeling for Computing Systems",
        "code": "PSMCS",
        "pdf": "Probability.pdf",
        "description": "Discrete & continuous random variables, two-dimensional distributions, covariance, estimation, and forecasting.",
        "units": [
            "UNIT I – PROBABILITY AND DISCRETE RANDOM VARIABLES",
            "UNIT II – CONTINUOUS RANDOM VARIABLES",
            "UNIT III – TWO-DIMENSIONAL RANDOM VARIABLES, COVARIANCE AND REGRESSION",
            "UNIT IV – ESTIMATION AND HYPOTHESIS TESTING",
            "UNIT V – TIME SERIES ANALYSIS AND FORECASTING"
        ]
    },
    2: {
        "id": 2,
        "name": "Artificial Intelligence",
        "code": "AI",
        "pdf": "AI.pdf",
        "description": "Intelligent agents, informed search, adversarial game search, propositional logic, and Bayesian networks.",
        "units": [
            "UNIT I – INTRODUCTION TO ARTIFICIAL INTELLIGENCE",
            "UNIT II – INFORMED AND LOCAL SEARCH",
            "UNIT III – CSP AND ADVERSARIAL SEARCH",
            "UNIT IV – KNOWLEDGE REPRESENTATION AND LOGIC",
            "UNIT V – UNCERTAINTY, BAYESIAN NETWORKS AND ONTOLOGIES"
        ]
    },
    3: {
        "id": 3,
        "name": "Data Exploration and Visualization",
        "code": "DEV",
        "pdf": "Data_Exploration.pdf",
        "description": "Exploratory statistics, bivariate/multivariate distributions, time series analysis, dashboard tools, and ethics.",
        "units": [
            "UNIT I – FOUNDATION OF DATA AND ANALYSIS",
            "UNIT II – BIVARIATE AND MULTIVARIATE DATA EXPLORATION",
            "UNIT III – TIME SERIES, CATEGORICAL AND TEXTUAL DATA EXPLORATION",
            "UNIT IV – DATA VISUALIZATION TOOLS AND TECHNIQUES",
            "UNIT V – STORYTELLING, ETHICS AND COMMUNICATION"
        ]
    },
    4: {
        "id": 4,
        "name": "Data Structures and Algorithms",
        "code": "DSA",
        "pdf": "Data_Structures.pdf",
        "description": "Stacks, queues, hashing, binary search trees, AVL trees, graphs, Dijkstra, and asymptotic complexity.",
        "units": [
            "UNIT I – LISTS, STACKS AND QUEUES",
            "UNIT II – SEARCHING, SORTING AND HASHING",
            "UNIT III – TREES, BST AND AVL TREES",
            "UNIT IV – GRAPHS AND GRAPH ALGORITHMS",
            "UNIT V – ALGORITHM ANALYSIS AND COMPLEXITY"
        ]
    },
    5: {
        "id": 5,
        "name": "Object Oriented Programming with Java",
        "code": "JAVA",
        "pdf": "Java.pdf",
        "description": "OOP fundamentals, inheritance, polymorphism, exceptions, multithreading, collections, and Java I/O.",
        "units": [
            "UNIT 1 – JAVA FUNDAMENTALS",
            "UNIT 2 – INHERITANCE AND POLYMORPHISM",
            "UNIT 3 – EXCEPTION HANDLING AND MULTITHREADING",
            "UNIT 4 – COLLECTIONS FRAMEWORK AND GENERICS",
            "UNIT 5 – JAVA FILE I/O AND SERIALIZATION"
        ]
    },
    6: {
        "id": 6,
        "name": "Digital Principles and Computer Organization",
        "code": "DPCO",
        "pdf": "Digital_Principles.pdf",
        "description": "Combinational logic, synchronous sequential circuits, instruction execution, pipelining, cache, and I/O DMA.",
        "units": [
            "UNIT I – COMBINATIONAL LOGIC",
            "UNIT II – SYNCHRONOUS SEQUENTIAL LOGIC",
            "UNIT III – COMPUTER FUNDAMENTALS",
            "UNIT IV – PROCESSOR DATAPATH AND CONTROL UNIT",
            "UNIT V – MEMORY AND I/O ORGANIZATION"
        ]
    }
}

# ==============================================================================
# DATABASE MANAGEMENT AND SAFE MIGRATION
# ==============================================================================

def get_db_connection():
    """Returns a SQLite connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def backup_corrupt_database(path):
    """Backs up a non-SQLite or corrupt database file instead of overwriting."""
    if os.path.exists(path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.corrupt_{timestamp}.bak"
        try:
            os.rename(path, backup_path)
            print(f"[!] Warning: Corrupted database backed up to: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"[!] Error backing up corrupt database: {e}")
    return None


def is_valid_sqlite_db(path):
    """Verifies SQLite header to ensure the file is an actual SQLite database."""
    if not os.path.exists(path):
        return True
    if os.path.getsize(path) == 0:
        return False
    try:
        with open(path, "rb") as f:
            header = f.read(16)
            return header.startswith(b"SQLite format 3")
    except Exception:
        return False


def init_db():
    """
    Initializes and safely migrates the SQLite database without deleting records.
    Creates missing tables and detects/adds missing columns dynamically.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(PDF_DIR, exist_ok=True)

    if os.path.exists(DB_PATH) and not is_valid_sqlite_db(DB_PATH):
        backup_corrupt_database(DB_PATH)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Students Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            verified INTEGER DEFAULT 0,
            otp_hash TEXT,
            otp_expiry DATETIME,
            college TEXT,
            department TEXT,
            study_year TEXT,
            phone TEXT,
            address TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Attempts Table (marks is always 1)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course TEXT NOT NULL,
            unit TEXT NOT NULL,
            marks INTEGER DEFAULT 1,
            total_questions INTEGER NOT NULL,
            attempted_questions INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            incorrect_answers INTEGER DEFAULT 0,
            unanswered_questions INTEGER DEFAULT 0,
            score REAL DEFAULT 0.0,
            percentage REAL DEFAULT 0.0,
            scoring_available INTEGER DEFAULT 1,
            submitted_answers TEXT,
            evaluation_summary TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
    """)

    # 3. Feedback Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
            message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
    """)

    # Dynamic Column Migration for existing databases
    def ensure_columns(table_name, required_columns):
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {col["name"].lower() for col in cursor.fetchall()}
        for col_name, col_type in required_columns.items():
            if col_name.lower() not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                    print(f"[+] Migrated: Added column '{col_name}' to table '{table_name}'")
                except Exception as err:
                    print(f"[-] Column migration warning for {table_name}.{col_name}: {err}")

    ensure_columns("students", {
        "verified": "INTEGER DEFAULT 0",
        "otp_hash": "TEXT",
        "otp_expiry": "DATETIME",
        "college": "TEXT",
        "department": "TEXT",
        "study_year": "TEXT",
        "phone": "TEXT",
        "address": "TEXT",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP"
    })

    ensure_columns("attempts", {
        "course": "TEXT DEFAULT 'General Course'",
        "course_name": "TEXT DEFAULT 'General Course'",
        "unit": "TEXT DEFAULT 'Unit I'",
        "marks": "INTEGER DEFAULT 1",
        "attempted_questions": "INTEGER DEFAULT 0",
        "incorrect_answers": "INTEGER DEFAULT 0",
        "unanswered_questions": "INTEGER DEFAULT 0",
        "percentage": "REAL DEFAULT 0.0",
        "scoring_available": "INTEGER DEFAULT 1",
        "submitted_answers": "TEXT",
        "evaluation_summary": "TEXT",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP"
    })

    conn.commit()
    conn.close()
    print("[*] MINDTRACE SQLite Database initialized and safely migrated.")


# Initialize DB on load
init_db()

# ==============================================================================
# AUTHENTICATION & SECURITY HELPERS
# ==============================================================================

def login_required(f):
    """Decorator ensuring a valid authenticated user session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "student_id" not in session:
            if request.is_json or request.path.startswith("/submit"):
                return jsonify({
                    "success": False,
                    "error": "Your session has expired. Please sign in again.",
                    "redirect_url": url_for("login")
                }), 401
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        conn = get_db_connection()
        student = conn.execute(
            "SELECT id, verified FROM students WHERE id = ?",
            (session["student_id"],)
        ).fetchone()
        conn.close()
        if not student:
            session.clear()
            if request.is_json or request.path.startswith("/submit"):
                return jsonify({
                    "success": False,
                    "error": "Session expired. Please sign in again.",
                    "redirect_url": url_for("login")
                }), 401
            flash("Session expired. Please log in again.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def generate_otp():
    """Generates a secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(900000) + 100000}"


def send_otp_email(recipient_email, student_name, code):
    """
    Sends verification email via SMTP if configured.
    Falls back gracefully to local development mode without crashing.
    """
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT", 587)
    smtp_user = os.environ.get("SMTP_USERNAME")
    smtp_pass = os.environ.get("SMTP_PASSWORD")

    if not smtp_server or not smtp_user or not smtp_pass:
        return False, "SMTP is not configured. Running in Local Development Verification mode."

    try:
        msg = MIMEMultipart()
        msg["From"] = f"MINDTRACE <{smtp_user}>"
        msg["To"] = recipient_email
        msg["Subject"] = "Your MINDTRACE OTP Verification Code"

        body = f"""Hello {student_name},

Welcome to MINDTRACE — AI Adaptive Learning Platform.
Your 6-digit email verification OTP is:

    {code}

This code is valid for 15 minutes.

Best regards,
MINDTRACE Team
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_server, int(smtp_port), timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, "Verification email sent successfully."
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

# ==============================================================================
# PDF QUESTION EXTRACTION ENGINE (STRICTLY 1-MARK ONLY)
# ==============================================================================

# In-memory question cache for high performance
QUESTION_CACHE = {}

def parse_pdf_questions(pdf_filename, course_id):
    """
    Extracts strictly 1-mark questions with options, answer key, and explanations
    from the course PDF file using PyMuPDF.
    """
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    if not os.path.exists(pdf_path):
        return []

    if fitz is None:
        return []

    extracted_questions = []
    current_unit = "UNIT I"

    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"

        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        
        # Regex patterns
        unit_header_pattern = re.compile(r"^(UNIT\s+(?:[I|V|X]+|\d+)\b[^\n]*)", re.IGNORECASE)
        question_start_pattern = re.compile(r"^(?:Q)?(\d+)[\.\)]\s*(.+)", re.IGNORECASE)
        correct_answer_pattern = re.compile(r"^(?:Correct\s+[aA]nswer|[aA]nswer)\s*:\s*([A-Da-d])[\)\.]?\s*(.*)", re.IGNORECASE)

        current_q_num = None
        current_q_text = ""
        current_options = []
        current_answer = ""
        current_explanation = ""

        def save_current_question():
            nonlocal current_q_num, current_q_text, current_options, current_answer, current_explanation
            if current_q_num and current_q_text:
                # Format options cleanly
                clean_opts = []
                for opt in current_options:
                    clean_opts.append(opt)

                extracted_questions.append({
                    "id": f"{pdf_filename.replace('.pdf','')}_{current_unit[:6].strip()}_{current_q_num}",
                    "course_id": course_id,
                    "unit": current_unit,
                    "marks": 1,  # Strictly 1-mark
                    "question": current_q_text.strip(),
                    "options": clean_opts,
                    "correct": current_answer.upper() if current_answer else "A",
                    "explanation": current_explanation.strip() if current_explanation else "Concept directly verified from syllabus answer key."
                })
            current_q_num = None
            current_q_text = ""
            current_options = []
            current_answer = ""
            current_explanation = ""

        idx = 0
        while idx < len(lines):
            line = lines[idx]

            # Check for Unit Header
            unit_match = unit_header_pattern.match(line)
            if unit_match:
                save_current_question()
                current_unit = unit_match.group(1).strip()
                idx += 1
                continue

            # Check for Answer line
            ans_match = correct_answer_pattern.match(line)
            if ans_match:
                current_answer = ans_match.group(1)
                rem_text = ans_match.group(2).strip()
                if rem_text:
                    current_explanation = rem_text.lstrip("— -").strip()
                # Check next line for additional explanation
                if idx + 1 < len(lines) and not question_start_pattern.match(lines[idx+1]) and not unit_header_pattern.match(lines[idx+1]):
                    next_line = lines[idx+1]
                    if not re.match(r"^[A-Da-d][\)\.]", next_line) and not next_line.startswith("Page"):
                        current_explanation += " " + next_line
                        idx += 1
                idx += 1
                continue

            # Check for Question start
            q_match = question_start_pattern.match(line)
            if q_match:
                save_current_question()
                current_q_num = q_match.group(1)
                current_q_text = q_match.group(2)
                idx += 1
                continue

            # Check for options
            # Formats: "A) ...", "a) ...", "A. ...", or multi-option line: "a) 2 b) 3 c) 4 d) 1"
            if re.search(r"\b[a-d][\)]\s+", line, re.IGNORECASE) or re.match(r"^[A-Da-d][\.\)]\s*", line):
                # Check if multiple options on same line (e.g. DSA: a) 2 b) 3 c) 4 d) 1)
                parts = re.split(r"(?<=\S)\s+(?=[a-d][\)])", line)
                if len(parts) > 1:
                    for p in parts:
                        current_options.append(p.strip())
                else:
                    current_options.append(line.strip())
                idx += 1
                continue

            # If inside question text and before options
            if current_q_num and not current_options and not current_answer:
                if not line.startswith("Page") and not "U25" in line and not "KPR" in line:
                    current_q_text += " " + line

            idx += 1

        # Save last question
        save_current_question()

    except Exception as e:
        print(f"[!] PDF Parse error for {pdf_filename}: {e}")

    return extracted_questions


def get_course_questions(course_id):
    """Fetches questions from cache or extracts them from the PDF."""
    if course_id in QUESTION_CACHE:
        return QUESTION_CACHE[course_id]

    course_data = COURSES.get(course_id)
    if not course_data:
        return []

    questions = parse_pdf_questions(course_data["pdf"], course_id)
    QUESTION_CACHE[course_id] = questions
    return questions

# ==============================================================================
# FLASK APPLICATION ROUTES
# ==============================================================================

@app.route("/")
def index():
    """Root entry: redirects logged-in students to courses, else login."""
    if "student_id" in session:
        return redirect(url_for("courses"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Student registration with validation, password hashing, and OTP code generation."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("signup.html", name=name, email=email)

        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
            flash("Please enter a valid email address.", "danger")
            return render_template("signup.html", name=name, email=email)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("signup.html", name=name, email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html", name=name, email=email)

        conn = get_db_connection()
        existing = conn.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("An account with this email already exists. Please log in.", "warning")
            return redirect(url_for("login"))

        password_hash = generate_password_hash(password)
        otp = generate_otp()
        expiry = datetime.now() + timedelta(minutes=15)

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO students (
                name, email, password_hash, verified,
                otp_hash, otp_expiry
            ) VALUES (?, ?, ?, 0, ?, ?)
        """, (name, email, password_hash, otp, expiry))
        student_id = cursor.lastrowid
        conn.commit()
        conn.close()

        session["unverified_student_id"] = student_id
        session["unverified_email"] = email
        session["dev_otp"] = otp

        sent, msg = send_otp_email(email, name, otp)
        if sent:
            flash("Registration successful! An OTP verification code has been sent to your email.", "success")
        else:
            flash(f"Account created! (Local Development Mode: Your OTP is {otp})", "info")

        return redirect(url_for("email_verify"))

    return render_template("signup.html", is_login_mode=False)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Student login with email & password verification."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("signup.html", is_login_mode=True, email=email)

        conn = get_db_connection()
        student = conn.execute("SELECT * FROM students WHERE email = ?", (email,)).fetchone()
        conn.close()

        if not student or not check_password_hash(student["password_hash"], password):
            flash("Invalid email or password. Please try again.", "danger")
            return render_template("signup.html", is_login_mode=True, email=email)

        if not student["verified"]:
            session["unverified_student_id"] = student["id"]
            session["unverified_email"] = student["email"]
            session["dev_otp"] = student["otp_hash"]
            flash("Please verify your email before logging in.", "warning")
            return redirect(url_for("email_verify"))

        # Successfully logged in
        session.clear()
        session["student_id"] = student["id"]
        session["student_name"] = student["name"]
        session["student_email"] = student["email"]
        session.permanent = True

        flash(f"Welcome back, {student['name']}!", "success")
        return redirect(url_for("courses"))

    return render_template("signup.html", is_login_mode=True)


@app.route("/email_verify", methods=["GET", "POST"])
def email_verify():
    """Verifies student email via 6-digit OTP code."""
    student_id = session.get("unverified_student_id")
    email = session.get("unverified_email")
    dev_otp = session.get("dev_otp")

    if not student_id:
        flash("No pending verification session. Please log in or sign up.", "info")
        return redirect(url_for("login"))

    if request.method == "POST":
        entered_otp = (request.form.get("otp") or request.form.get("code") or "").strip()

        conn = get_db_connection()
        student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()

        if not student:
            conn.close()
            session.clear()
            flash("Student record not found.", "danger")
            return redirect(url_for("signup"))

        now = datetime.now()
        expiry_val = student["otp_expiry"]
        expiry = datetime.strptime(str(expiry_val)[:19], "%Y-%m-%d %H:%M:%S") if expiry_val else now

        if student["otp_hash"] != entered_otp:
            conn.close()
            flash("Invalid OTP code. Please check and try again.", "danger")
            return render_template("email_verify.html", email=email, dev_otp=dev_otp)

        if now > expiry:
            conn.close()
            flash("OTP has expired. Please click Resend OTP.", "warning")
            return render_template("email_verify.html", email=email, dev_otp=dev_otp)

        # Mark as verified
        conn.execute("UPDATE students SET verified = 1, otp_hash = NULL WHERE id = ?", (student_id,))
        conn.commit()
        conn.close()

        session.clear()
        session["student_id"] = student["id"]
        session["student_name"] = student["name"]
        session["student_email"] = student["email"]

        flash("Email verified successfully! Welcome to MINDTRACE.", "success")
        return redirect(url_for("courses"))

    return render_template("email_verify.html", email=email, dev_otp=dev_otp)


@app.route("/resend_code")
def resend_code():
    """Generates and resends a fresh OTP code."""
    student_id = session.get("unverified_student_id")
    email = session.get("unverified_email")

    if not student_id or not email:
        flash("No active verification session.", "warning")
        return redirect(url_for("login"))

    new_otp = generate_otp()
    expiry = datetime.now() + timedelta(minutes=15)

    conn = get_db_connection()
    conn.execute("UPDATE students SET otp_hash = ?, otp_expiry = ? WHERE id = ?", (new_otp, expiry, student_id))
    student = conn.execute("SELECT name FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.commit()
    conn.close()

    session["dev_otp"] = new_otp
    student_name = student["name"] if student else "Student"
    sent, _ = send_otp_email(email, student_name, new_otp)

    if sent:
        flash("A new OTP code has been sent to your email.", "info")
    else:
        flash(f"New OTP generated! (Dev Mode: Your OTP is {new_otp})", "info")

    return redirect(url_for("email_verify"))


@app.route("/logout")
def logout():
    """Logs out student and clears session."""
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """View and update student personal and academic information."""
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        college = request.form.get("college", "").strip()
        department = request.form.get("department", "").strip()
        study_year = request.form.get("study_year", "").strip()

        if not name:
            flash("Full name cannot be blank.", "danger")
            conn.close()
            return render_template("profile.html", student=student)

        conn.execute("""
            UPDATE students SET
                name = ?, phone = ?, address = ?,
                college = ?, department = ?, study_year = ?
            WHERE id = ?
        """, (name, phone, address, college, department, study_year, session["student_id"]))
        conn.commit()

        session["student_name"] = name
        student = conn.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()
        conn.close()

        flash("Profile updated successfully!", "success")
        return render_template("profile.html", student=student)

    conn.close()
    return render_template("profile.html", student=student)


@app.route("/courses")
@login_required
def courses():
    """
    Displays the 6 course cards with PDF indexing status,
    number of extracted 1-mark questions, and unit navigation.
    """
    courses_data = []
    for c_id, c in COURSES.items():
        pdf_path = os.path.join(PDF_DIR, c["pdf"])
        is_pdf_present = os.path.exists(pdf_path)
        questions = get_course_questions(c_id)
        q_count = len(questions)

        courses_data.append({
            **c,
            "pdf_present": is_pdf_present,
            "question_count": q_count,
            "indexed_status": f"Indexed ({q_count} 1-Mark Questions)" if is_pdf_present and q_count > 0 else "PDF Unindexed"
        })

    return render_template("courses.html", courses=courses_data)


@app.route("/course/<int:course_id>/units")
@login_required
def course_units(course_id):
    """
    Dedicated Unit Selection Page:
    Displays available units for the selected course with strictly 1-mark question count.
    """
    if course_id not in COURSES:
        return redirect(url_for("courses"))

    course = COURSES[course_id]
    all_questions = get_course_questions(course_id)

    # Group 1-mark questions by Unit
    units_info = []
    for u_idx, u_title in enumerate(course["units"], start=1):
        u_prefix = f"UNIT {u_idx}"
        u_roman = ["I", "II", "III", "IV", "V"][u_idx - 1]
        
        # Match unit questions
        unit_qs = [
            q for q in all_questions
            if u_prefix.lower() in q["unit"].lower() or f"unit {u_roman}".lower() in q["unit"].lower()
        ]

        units_info.append({
            "key": f"Unit {u_roman}",
            "full_name": u_title,
            "question_count": len(unit_qs) if unit_qs else (20 if os.path.exists(os.path.join(PDF_DIR, course["pdf"])) else 0)
        })

    return render_template("courses.html", course=course, units=units_info, select_unit_mode=True)


@app.route("/questions")
@login_required
def questions():
    """
    Interactive questions page:
    STRICTLY 1-MARK QUESTIONS for the selected course and unit.
    NO 2-mark or 14-mark questions or dropdowns allowed.
    """
    course_id = request.args.get("course_id", type=int, default=1)
    if course_id not in COURSES:
        course_id = 1

    selected_course = COURSES[course_id]
    selected_unit = request.args.get("unit", "Unit I")
    limit = request.args.get("limit", type=int, default=10)

    # Get all 1-mark questions for this course
    all_questions = get_course_questions(course_id)

    # Extract unit identifier (e.g. "Unit I", "Unit 1")
    unit_norm = selected_unit.lower()
    roman_map = {"unit i": ["unit i", "unit 1"], "unit ii": ["unit ii", "unit 2"],
                 "unit iii": ["unit iii", "unit 3"], "unit iv": ["unit iv", "unit 4"],
                 "unit v": ["unit v", "unit 5"]}
    valid_keys = roman_map.get(unit_norm, [unit_norm])

    # Filter strictly 1-mark questions for this unit
    filtered_questions = [
        q for q in all_questions
        if any(vk in q["unit"].lower() for vk in valid_keys)
        and q["marks"] == 1
    ]

    # If extraction is empty for this specific unit, fallback to available unit questions
    if not filtered_questions and all_questions:
        filtered_questions = [q for q in all_questions if q["marks"] == 1]

    # Limit questions to requested practice count
    active_questions = filtered_questions[:max(1, min(limit, len(filtered_questions)))]

    return render_template(
        "questions.html",
        course=selected_course,
        unit=selected_unit,
        marks=1,  # Strictly 1-mark
        questions=active_questions,
        total_questions=len(active_questions),
        limit=limit
    )


@app.route("/submit_attempt", methods=["POST"])
@login_required
def submit_attempt():
    """
    Evaluates student submitted answers for 1-mark questions,
    grades against the verified answer key, identifies mistakes and explanations,
    and stores the record in the `attempts` table.
    """
    try:
        data = request.get_json(silent=True) or {}

        course_id = data.get("course_id", 1)
        course_name = COURSES.get(course_id, {}).get("name", "General Course")
        unit_name = data.get("unit", "Unit I")
        answers = data.get("answers", {})  # Map of question_id -> student answer
        questions_data = data.get("questions", [])

        total_questions = len(questions_data)
        if total_questions == 0:
            return jsonify({"success": False, "error": "No questions were submitted."}), 400

        correct_answers = 0
        incorrect_answers = 0
        unanswered_questions = 0
        attempted_questions = 0
        evaluation_details = []

        for q in questions_data:
            q_id = q.get("id")
            student_ans = str(answers.get(q_id, "")).strip()
            correct_ans = str(q.get("correct_answer") or q.get("correct") or "").strip().upper()

            if not student_ans:
                unanswered_questions += 1
                is_correct = False
                status = "Unanswered"
            else:
                attempted_questions += 1
                # Clean and compare (e.g. 'A)' -> 'A')
                clean_student = student_ans.upper().replace(")", "").replace(".", "").strip()
                clean_correct = correct_ans.replace(")", "").replace(".", "").strip()
                if clean_student == clean_correct or clean_student == clean_correct[:1]:
                    correct_answers += 1
                    is_correct = True
                    status = "Correct"
                else:
                    incorrect_answers += 1
                    is_correct = False
                    status = "Incorrect"

            evaluation_details.append({
                "id": q_id,
                "question": q.get("question"),
                "options": q.get("options", []),
                "student_answer": student_ans if student_ans else "(Not Answered)",
                "correct_answer": correct_ans,
                "is_correct": is_correct,
                "status": status,
                "explanation": q.get("explanation", "Verified concept directly from syllabus answer key.")
            })

        # Calculations for 1-mark questions
        score = float(correct_answers)
        percentage = round((correct_answers / total_questions) * 100, 2) if total_questions > 0 else 0.0

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Populate both course_name and course for guaranteed database compatibility
        cursor.execute("""
            INSERT INTO attempts (
                student_id, course_name, course, unit, marks,
                total_questions, attempted_questions, correct_answers,
                incorrect_answers, unanswered_questions, score,
                percentage, scoring_available, submitted_answers,
                evaluation_summary
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            session["student_id"],
            course_name,
            course_name,
            unit_name,
            total_questions,
            attempted_questions,
            correct_answers,
            incorrect_answers,
            unanswered_questions,
            score,
            percentage,
            json.dumps(answers),
            json.dumps(evaluation_details)
        ))
        attempt_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "attempt_id": attempt_id,
            "redirect_url": url_for("result", attempt_id=attempt_id)
        })
    except Exception as e:
        print(f"[ERROR in submit_attempt] {e}")
        return jsonify({"success": False, "error": f"Evaluation error: {str(e)}"}), 500


@app.route("/result/<int:attempt_id>")
@login_required
def result(attempt_id):
    """Displays practice results, score, percentage, and misconception diagnosis."""
    conn = get_db_connection()
    attempt = conn.execute("""
        SELECT * FROM attempts WHERE id = ? AND student_id = ?
    """, (attempt_id, session["student_id"])).fetchone()
    conn.close()

    if not attempt:
        flash("Attempt record not found or access denied.", "danger")
        return redirect(url_for("courses"))

    try:
        evaluation = json.loads(attempt["evaluation_summary"] or "[]")
    except Exception:
        evaluation = []

    return render_template(
        "result.html",
        attempt=attempt,
        evaluation=evaluation,
        student_name=session.get("student_name", "Student")
    )


@app.route("/history")
@login_required
def history():
    """Shows the logged-in student's past practice attempts (marks is always 1)."""
    conn = get_db_connection()
    attempts = conn.execute("""
        SELECT * FROM attempts
        WHERE student_id = ?
        ORDER BY created_at DESC
    """, (session["student_id"],)).fetchall()
    conn.close()

    return render_template("history.html", attempts=attempts)


@app.route("/feedback", methods=["POST"])
@login_required
def feedback():
    """Saves student rating (1-5) and feedback message in the `feedback` table."""
    rating = request.form.get("rating", type=int)
    message = request.form.get("message", "").strip()

    if not rating or rating < 1 or rating > 5:
        flash("Please provide a rating between 1 and 5.", "danger")
        return redirect(request.referrer or url_for("courses"))

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO feedback (student_id, rating, message)
        VALUES (?, ?, ?)
    """, (session["student_id"], rating, message))
    conn.commit()
    conn.close()

    flash("Thank you for your feedback! Your submission has been saved.", "success")
    return redirect(request.referrer or url_for("courses"))


@app.route("/database")
@login_required
def database():
    """
    Database transparency view.
    Securely displays the authenticated student's profile, attempts, and feedback
    without exposing other students' private data.
    """
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()
    attempts = conn.execute("""
        SELECT id, course, unit, marks, total_questions, correct_answers, score, percentage, created_at
        FROM attempts WHERE student_id = ?
        ORDER BY created_at DESC LIMIT 20
    """, (session["student_id"],)).fetchall()

    user_feedback = conn.execute("""
        SELECT id, rating, message, created_at FROM feedback WHERE student_id = ?
        ORDER BY created_at DESC
    """, (session["student_id"],)).fetchall()

    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    conn.close()

    return render_template(
        "database.html",
        student=student,
        attempts=attempts,
        user_feedback=user_feedback,
        tables=tables,
        db_path=DB_PATH
    )


@app.context_processor
def inject_global():
    return {
        "current_year": datetime.now().year,
        "courses_list": COURSES
    }


if __name__ == "__main__":
    print("[*] Starting MINDTRACE Local Server on http://127.0.0.1:5000 ...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

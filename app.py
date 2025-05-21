# -*- coding: utf-8 -*-
import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from dotenv import load_dotenv
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, auth, _auth_utils
from firebase_admin.auth import UserNotFoundError
from config import FIREBASE_CREDENTIALS, FIREBASE_CONFIG  # Assuming config.py exists with FIREBASE_CREDENTIALS
from src.pipeline.predict_pipline import CustomData, PredictPipeline
from src.utils import login_required  # Assuming utils.py exists with login_required decorator
import pandas as pd
from flask import Blueprint, request, send_file
import matplotlib
from matplotlib import pyplot as plt
from reportlab.lib.utils import ImageReader
# from src.auth import login_required

from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from collections import defaultdict  # Import defaultdict
from bson import ObjectId
import random
import string
import traceback
import json
matplotlib.use('Agg')  # For better error logging

# Initialize Flask App
application = Flask(__name__)
app = application
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_dev')  # Use environment variable for production

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK

try:
    if not firebase_admin._apps:
        firebase_config_json = os.environ.get("FIREBASE_CONFIG")
        if not firebase_config_json:
            raise ValueError("FIREBASE_CONFIG environment variable not set.")
        
        firebase_config = json.loads(firebase_config_json)
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")


# MongoDB setup
mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/student_performance")  # Use env variable
try:
    client = MongoClient(mongo_uri)
    # The ismaster command is cheap and does not require auth.
    client.admin.command('ismaster')
    db = client.student_performance  # Use the specific database name directly
    print("MongoDB connection successful.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    # Handle connection error appropriately
    # exit(1)


# ==================== UTILITY FUNCTION FOR TEMPLATES ====================
def safe_get(data, key, default=None):
    """Safely get a value from a dictionary, returning default if key missing."""
    return data.get(key, default) if isinstance(data, dict) else default


app.jinja_env.globals.update(safe_get=safe_get)

# ==================== ROOT ====================
@app.route('/')
def index():
    # Redirect logged-in users to their respective dashboards
    user = session.get('user')
    if user:
        if user.get('role') == 'student':
            return redirect(url_for('student_dashboard'))
        elif user.get('role') == 'tutor':
            return redirect(url_for('tutor_dashboard'))  # Or tutor_student_view
        elif user.get('role') == 'admin':
            return redirect(url_for('admin_panel'))
    return render_template('index.html')

# ==================== REGISTER ====================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        gender = request.form.get("gender")
        role = "student"  # Only student registration allowed

        # Basic form validation
        if not all([name, email, password, confirm_password, gender]):
            flash("Please fill in all fields.", "warning")
            return redirect(url_for('register'))

        if password != confirm_password:
            flash("Passwords do not match.", "warning")
            return redirect(url_for('register'))

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return redirect(url_for('register'))

        # Data to insert into MongoDB
        user_data_to_insert = {
            "uid": None,  # Will be added after Firebase creation
            "email": email,
            "name": name,
            "gender": gender,
            "role": role,
            "marks_history": [],
            "login_restricted": False  # Default for students
        }

        try:
            # Check if user already exists in Firebase
            try:
                auth.get_user_by_email(email)
                flash("An account with this email already exists.", "warning")
                return redirect(url_for('login'))
            except UserNotFoundError:
                pass  # Safe to continue if user doesn't exist

            # Create user in Firebase Auth
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )

            # Add Firebase UID to MongoDB
            user_data_to_insert["uid"] = user.uid
            db.users.insert_one(user_data_to_insert)

            flash("Registration successful! You can now login.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            print(f"Registration Error: {e}\n{traceback.format_exc()}")
            flash("An unexpected error occurred. Please try again.", "danger")
            return redirect(url_for("register"))

    return render_template("register.html")

# ==================== LOGIN (Handles Students Only Now) ====================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")  # The password is not used directly on the backend; Firebase handles it.

        # Check if email or password is empty
        if not email or not password:
            flash("Please enter both email and password.", "warning")
            return redirect(url_for("login"))

        try:
            # 1. Get user by email from Firebase (without verifying password)
            user = auth.get_user_by_email(email)

            # 2. Fetch user data from MongoDB (assuming you're storing user roles and other data here)
            user_data = db.users.find_one({"uid": user.uid})

            if not user_data:
                flash("User data not found in our database. Please contact support.", "danger")
                return redirect(url_for("login"))

            # 3. Check Role (Only Students should be allowed to log in here)
            if user_data.get("role") != "student":
                flash("Invalid login. This login is for students only. Please use the appropriate login page.", "warning")
                return redirect(url_for("login"))

            # <<< MODIFIED >>> Check if student login is restricted by tutor/admin
            if user_data.get("login_restricted", False):
                flash("Your account access has been restricted. Please contact your tutor or administrator.", "danger")
                return redirect(url_for("login"))

            # 4. Verify ID token sent by frontend (firebase_token sent from frontend)
            id_token = request.form.get("id_token")

            if not id_token:
                flash("Authentication failed. Please login again.", "danger")
                return redirect(url_for("login"))

            # 5. Verify the ID token using Firebase Admin SDK
            decoded_token = auth.verify_id_token(id_token)
            uid_from_token = decoded_token['uid']

            # Check if the UID in the token matches the user UID
            if uid_from_token != user.uid:
                flash("Invalid token. Authentication failed.", "danger")
                return redirect(url_for("login"))

            # 6. Set session (user is authenticated)
            session["user"] = {
                "email": user.email,
                "uid": user.uid,
                "name": user_data.get("name", user.display_name),  # Prefer DB name over Firebase
                "role": user_data.get("role")
            }

            flash("Login successful.", "success")
            return redirect(url_for("student_dashboard"))

        except auth.UserNotFoundError:
            flash("No account found with that email. Please register.", "warning")
            return redirect(url_for("register"))
        except Exception as e:
            # Log error details for debugging
            print(f"Login Error: {e}\n{traceback.format_exc()}")
            flash("Login error: An unexpected issue occurred. Please try again.", "danger")
            return redirect(url_for("login"))

    # If GET request or failed POST
    return render_template("login.html")



# ==================== STUDENT DASHBOARD ====================
@app.route("/student_dashboard")
@login_required(role="student")
def student_dashboard():
    user_session = session.get("user")
    if not user_session:
        return redirect(url_for('login'))

    try:
        # Get student data from database
        student_data = db.users.find_one({"uid": user_session["uid"]})
        if not student_data:
            flash("Could not retrieve student data.", "danger")
            return redirect(url_for('logout'))

        # Process marks history with proper defaults
        processed_history = []
        subjects = ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']
        
        for entry in student_data.get("marks_history", []):
            # Create a new entry with all required fields
            processed_entry = {
                '_id': str(entry.get('_id', '')),
                'semester': entry.get('semester', 'N/A'),
                'pass_status': entry.get('pass_status', 'Pending'),
                'average': entry.get('average', 0),
                'percentage': entry.get('percentage', 0)
            }
            
            # Add all subject data with defaults
            for subject in subjects:
                processed_entry[f'{subject}_predicted'] = entry.get(f'{subject}_predicted', 0)
                processed_entry[f'{subject}_internal1'] = entry.get(f'{subject}_internal1', 0)
                processed_entry[f'{subject}_internal2'] = entry.get(f'{subject}_internal2', 0)
                processed_entry[f'{subject}_internal3'] = entry.get(f'{subject}_internal3', 0)
            
            processed_history.append(processed_entry)

        # Ensure student_data has all required fields
        student_data.setdefault('name', 'Unknown')
        student_data.setdefault('email', 'No email')
        student_data.setdefault('gender', 'Not specified')

        return render_template(
            "student_dashboard.html",
            user=student_data,
            history=processed_history
        )
        
    except Exception as e:
        print(f"Error loading dashboard: {str(e)}\n{traceback.format_exc()}")
        flash("An error occurred while loading your dashboard.", "danger")
        return redirect(url_for('logout'))


# ==================== PREDICT DATA (Handles Student & Tutor-for-Student) ====================
@app.route('/predict_datappoint', methods=['GET', 'POST'])
@login_required(role="student,tutor")
def predict_datappoint():
    if request.method == 'POST':
        try:
            semester = request.form.get("semester")
            if not semester or not semester.isdigit() or int(semester) not in range(1, 9):
                flash("Please select a valid semester (1-8).", "danger")
                return redirect(request.url)
            semester = int(semester)

            fields = ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']
            internal_marks = {}

            for subject in fields:
                for i in range(1, 4):
                    field_name = f"{subject}_internal{i}"
                    value = request.form.get(field_name)
                    if not value:
                        flash(f"Missing input for {field_name}.", "danger")
                        return redirect(request.url)
                    try:
                        internal_marks[field_name] = float(value)
                    except ValueError:
                        flash(f"Invalid input for {field_name}.", "danger")
                        return redirect(request.url)

            data = CustomData(**internal_marks)
            pred_df = data.get_data_as_dataframe()
            pipeline = PredictPipeline()
            results = pipeline.predict(pred_df)[0].tolist()

            predicted_scores_dict = {
                f"{subject}_predicted": round(prediction, 2)
                for subject, prediction in zip(fields, results)
            }

            average = round(sum(results) / len(fields), 2)
            pass_status = "Pass" if average >= 45 else "Fail"

            new_entry = {
                "_id": ObjectId(),
                "semester": semester,
                **internal_marks,
                **predicted_scores_dict,
                "average": average,
                "percentage": average,  # Assuming 100 max
                "pass_status": pass_status,
                "predicted_by": session['user']['uid']
            }

            user_role = session['user']['role']
            if user_role == 'tutor':
                student_uid = request.form.get('student_uid')
                if student_uid:
                    db.users.update_one({"uid": student_uid}, {"$push": {"marks_history": new_entry}})
                    flash("Prediction saved for student.", "success")
                    return redirect(url_for('tutor_view_student_dashboard', student_uid=student_uid))
                flash("Missing student UID.", "danger")
                return redirect(request.url)

            elif user_role == 'student':
                db.users.update_one({"uid": session['user']['uid']}, {"$push": {"marks_history": new_entry}})
                flash("Prediction saved.", "success")
                return render_template(
                    "home.html",
                    results=predicted_scores_dict,
                    internal_marks=internal_marks,
                    average=average,
                    percentage=average,
                    pass_status=pass_status,
                    student_uid=session['user']['uid'],
                    student_name=session['user']['name'],
                    selected_semester=semester
                )

        except Exception as e:
            print(f"Prediction Error: {e}\n{traceback.format_exc()}")
            flash("Prediction failed.", "danger")
            return redirect(request.url)

    user_role = session.get('user', {}).get('role')
    if user_role == 'student':
        return render_template('home.html', results=None, internal_marks={}, student_uid=session['user']['uid'], student_name=session['user']['name'], selected_semester="")
    elif user_role == 'tutor':
        return redirect(url_for('tutor_student_view'))
    return redirect(url_for('login'))


# ==================== DOWNLOAD REPORT ====================
# This route seems okay, but ensure it handles tutor downloading student report correctly
# Might need to adjust @login_required if tutors should also download any student report
@app.route('/download_report', methods=['POST'])
@login_required(role="student,tutor")
def download_report():
    uid_to_download = request.form.get('uid')
    requesting_user = session.get('user')

    if not uid_to_download:
        flash("No user specified for report.", "warning")
        return redirect(request.referrer or url_for('index'))

    if requesting_user['role'] == 'student' and requesting_user['uid'] != uid_to_download:
        flash("You are not authorized to download this report.", "danger")
        return redirect(url_for('student_dashboard'))

    user = db.users.find_one({'uid': uid_to_download, 'role': 'student'})
    if not user:
        flash("Student data not found.", "warning")
        return redirect(url_for('tutor_student_view') if requesting_user['role'] == 'tutor' else url_for('student_dashboard'))

    history = user.get('marks_history', [])
    if not history:
        flash("No prediction history found for this student.", "warning")
        return redirect(url_for('tutor_student_view') if requesting_user['role'] == 'tutor' else url_for('student_dashboard'))

    latest = history[-1]
    semester = latest.get("semester", "N/A")
    subjects = ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']

    try:
        # Create buffer for PDF
        buffer = BytesIO()
        
        # Set up PDF canvas with A4 size in portrait
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # Color Palette
        primary_color = (0.2, 0.4, 0.8)       # Navy Blue
        secondary_color = (0.3, 0.3, 0.3)      # Dark Gray
        accent_color = (0.8, 0.2, 0.2)         # Red
        success_color = (0.2, 0.6, 0.3)        # Green
        warning_color = (0.9, 0.6, 0.1)        # Orange
        
        # Set background to white
        p.setFillColorRGB(1, 1, 1)
        p.rect(0, 0, width, height, fill=1, stroke=0)
        
        # Header with minimal design
        p.saveState()
        p.setFillColorRGB(*primary_color)
        p.rect(0, height - 80, width, 80, fill=1, stroke=0)
        
        # Logo/Title
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 18)
        p.drawCentredString(width / 2, height - 50, "ACADEMIC PERFORMANCE REPORT")
        p.setFont("Helvetica", 10)
        p.drawCentredString(width / 2, height - 70, f"Semester {semester} • Generated on {pd.Timestamp.now().strftime('%d %b %Y')}")
        p.restoreState()
        
        # Student Information Section
        p.saveState()
        p.setFillColorRGB(0.95, 0.95, 0.95)  # Light gray background
        p.roundRect(40, height - 150, width - 80, 70, 5, fill=1, stroke=0)
        p.restoreState()
        
        y_position = height - 160
        p.setFillColorRGB(*secondary_color)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y_position, "STUDENT INFORMATION")
        y_position -= 20
        
        # Student info in two columns
        col1_x = 50
        col2_x = width / 2
        line_height = 16
        
        info_data = [
            ("Full Name:", user.get('name', 'N/A')),
            ("Student ID:", user.get('uid', 'N/A')),
            ("Email:", user.get('email', 'N/A')),
            ("Gender:", user.get('gender', 'N/A').capitalize()),
            ("Program:", "B.Tech Computer Science"),
            ("Department:", "Computer Science")
        ]
        
        p.setFont("Helvetica", 10)
        for i, (label, value) in enumerate(info_data):
            x = col1_x if i % 2 == 0 else col2_x
            y = y_position - (i // 2) * line_height
            
            p.setFillColorRGB(0.4, 0.4, 0.4)
            p.drawString(x, y, label)
            p.setFillColorRGB(*secondary_color)
            p.drawString(x + 70, y, value)
        
        # Performance Highlights
        y_position -= 100
        
        # Section Header
        p.setFillColorRGB(*secondary_color)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y_position, "PERFORMANCE HIGHLIGHTS")
        y_position -= 25
        
        # Highlight Cards
        card_width = (width - 100) / 3
        card_height = 70
        
        # Card 1: Overall Average
        draw_rounded_card(p, 40, y_position - card_height, card_width - 10, card_height, primary_color)
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(40 + (card_width-10)/2, y_position - 40, "OVERALL AVERAGE")
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(40 + (card_width-10)/2, y_position - 65, f"{latest.get('average', 'N/A')}")
        
        # Card 2: Percentage
        draw_rounded_card(p, 50 + card_width, y_position - card_height, card_width - 10, card_height, secondary_color)
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(50 + card_width + (card_width-10)/2, y_position - 40, "PERCENTAGE")
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(50 + card_width + (card_width-10)/2, y_position - 65, f"{latest.get('percentage', 'N/A')}%")
        
        # Card 3: Status
        status = latest.get('pass_status', 'N/A')
        status_color = success_color if status.lower() == 'pass' else accent_color
        draw_rounded_card(p, 60 + 2*card_width, y_position - card_height, card_width - 10, card_height, status_color)
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(60 + 2*card_width + (card_width-10)/2, y_position - 40, "STATUS")
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(60 + 2*card_width + (card_width-10)/2, y_position - 65, status.upper())
        
        # Subject Performance Table
        y_position -= 100
        
        # Section Header
        p.setFillColorRGB(*secondary_color)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y_position, "SUBJECT PERFORMANCE DETAILS")
        y_position -= 25
        
        # Table Headers
        headers = ["Subject", "Int 1", "Int 2", "Int 3", "Predicted", "Avg"]
        col_widths = [80, 60, 60, 60, 80, 60]
        table_start_x = 50
        
        # Header Background
        p.saveState()
        p.setFillColorRGB(0.9, 0.9, 0.9)
        p.roundRect(table_start_x, y_position - 5, sum(col_widths), 20, 3, fill=1, stroke=0)
        p.restoreState()
        
        # Header Text
        p.setFont("Helvetica-Bold", 9)
        p.setFillColorRGB(*secondary_color)
        for i, header in enumerate(headers):
            p.drawString(table_start_x + sum(col_widths[:i]) + 5, y_position, header)
        
        y_position -= 20
        
        # Table Rows
        p.setFont("Helvetica", 9)
        for idx, sub in enumerate(subjects):
            # Alternate row background
            if idx % 2 == 0:
                p.saveState()
                p.setFillColorRGB(0.97, 0.97, 0.97)
                p.roundRect(table_start_x, y_position - 3, sum(col_widths), 15, 2, fill=1, stroke=0)
                p.restoreState()
            
            # Calculate average
            internals = [
                latest.get(f"{sub}_internal1", 0),
                latest.get(f"{sub}_internal2", 0),
                latest.get(f"{sub}_internal3", 0)
            ]
            avg = sum(mark for mark in internals if isinstance(mark, (int, float))) / 3 if all(isinstance(mark, (int, float)) for mark in internals) else "N/A"
            
            # Subject name
            p.setFillColorRGB(*secondary_color)
            p.setFont("Helvetica-Bold", 9)
            p.drawString(table_start_x + 5, y_position, sub.upper())
            
            # Internal marks
            p.setFont("Helvetica", 9)
            p.setFillColorRGB(*secondary_color)
            for i, mark in enumerate(internals, start=1):
                p.drawString(table_start_x + sum(col_widths[:i]) + (col_widths[i-1]/2 - 5), y_position, str(mark))
            
            # Predicted mark
            predicted = latest.get(f"{sub}_predicted", "N/A")
            p.drawString(table_start_x + sum(col_widths[:4]) + (col_widths[4]/2 - 5), y_position, str(predicted))
            
            # Average (with conditional coloring)
            if isinstance(avg, (int, float)):
                if avg < 40:  # Red for low scores
                    p.setFillColorRGB(*accent_color)
                elif avg < 60:  # Orange for medium scores
                    p.setFillColorRGB(*warning_color)
                else:  # Green for good scores
                    p.setFillColorRGB(*success_color)
                p.setFont("Helvetica-Bold", 9)
                p.drawString(table_start_x + sum(col_widths[:5]) + (col_widths[5]/2 - 5), y_position, f"{avg:.1f}")
            else:
                p.setFillColorRGB(*secondary_color)
                p.drawString(table_start_x + sum(col_widths[:5]) + (col_widths[5]/2 - 5), y_position, str(avg))
            
            y_position -= 15
        
        # Performance Charts Section
        y_position -= 30
        p.setFillColorRGB(*secondary_color)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y_position, "PERFORMANCE VISUALIZATION")
        y_position -= 25
        
        try:
            chart_scores = [latest.get(f"{sub}_predicted", 0) for sub in subjects]
            valid_scores = [s for s in chart_scores if isinstance(s, (int, float))]
            valid_labels = [sub.capitalize() for s, sub in zip(chart_scores, subjects) if isinstance(s, (int, float))]
            
            if valid_scores:
                # Create donut chart
                pie_buffer = BytesIO()
                fig, ax = plt.subplots(figsize=(5, 5))
                
                # Color palette
                colors = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948']
                
                # Outer pie
                wedges, texts, autotexts = ax.pie(
                    valid_scores,
                    labels=valid_labels,
                    colors=colors[:len(valid_scores)],
                    startangle=90,
                    wedgeprops=dict(width=0.4, edgecolor='w'),
                    textprops={'fontsize': 8},
                    pctdistance=0.85,
                    autopct=lambda p: f'{p:.1f}%' if p >= 5 else ''
                )
                
                # Inner circle
                centre_circle = plt.Circle((0,0), 0.2, color='white', fc='white', linewidth=0)
                ax.add_artist(centre_circle)
                
                # Center text
                avg_score = sum(valid_scores)/len(valid_scores) if valid_scores else 0
                ax.text(0, 0, f"{avg_score:.1f}\nAvg", ha='center', va='center', 
                       fontsize=12, fontweight='bold', color=secondary_color)
                
                ax.set_title('Subject Score Distribution', fontsize=10, pad=15, 
                            fontweight='bold', color=secondary_color)
                plt.tight_layout()
                plt.savefig(pie_buffer, format='PNG', dpi=150, bbox_inches='tight', transparent=True)
                pie_buffer.seek(0)
                plt.close(fig)
                
                # Add pie chart to PDF
                pie_image = ImageReader(pie_buffer)
                p.drawImage(pie_image, 50, y_position - 200, width=250, height=200)
                
                # Create bar chart
                bar_buffer = BytesIO()
                fig, ax = plt.subplots(figsize=(6, 4))
                
                # Calculate internal averages
                internal_avgs = []
                for sub in subjects:
                    internals = [
                        latest.get(f"{sub}_internal1", 0),
                        latest.get(f"{sub}_internal2", 0),
                        latest.get(f"{sub}_internal3", 0)
                    ]
                    avg = sum(mark for mark in internals if isinstance(mark, (int, float))) / 3 if all(isinstance(mark, (int, float)) for mark in internals) else 0
                    internal_avgs.append(avg)
                
                x = range(len(subjects))
                width_bar = 0.35
                
                # Bar styling
                bars1 = ax.bar(
                    [i - width_bar/2 for i in x], 
                    internal_avgs, 
                    width_bar, 
                    label='Internal Avg', 
                    color=primary_color,
                    edgecolor='white',
                    linewidth=0.5
                )
                
                bars2 = ax.bar(
                    [i + width_bar/2 for i in x], 
                    chart_scores, 
                    width_bar, 
                    label='Predicted', 
                    color=success_color,
                    edgecolor='white',
                    linewidth=0.5
                )
                
                # Value labels
                for bars in [bars1, bars2]:
                    for bar in bars:
                        height = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2., height-5,
                                f'{int(height)}',
                                ha='center', va='bottom',
                                color='white', fontsize=6, fontweight='bold')
                
                ax.set_xticks(x)
                ax.set_xticklabels([sub.capitalize() for sub in subjects], 
                                  fontsize=8, color=secondary_color)
                ax.set_ylabel('Scores', fontsize=8, color=secondary_color)
                ax.set_title('Internal vs Predicted Scores', 
                             fontsize=10, pad=10, 
                             fontweight='bold', color=secondary_color)
                ax.legend(fontsize=7, framealpha=0.9)
                ax.grid(axis='y', linestyle='--', alpha=0.4)
                ax.set_axisbelow(True)
                
                # Clean up chart
                for spine in ['top', 'right']:
                    ax.spines[spine].set_visible(False)
                
                plt.tight_layout()
                plt.savefig(bar_buffer, format='PNG', dpi=150, bbox_inches='tight', transparent=True)
                bar_buffer.seek(0)
                plt.close(fig)
                
                # Add bar chart to PDF
                bar_image = ImageReader(bar_buffer)
                p.drawImage(bar_image, width/2 + 20, y_position - 200, width=250, height=200)
                
            else:
                p.setFont("Helvetica", 9)
                p.setFillColorRGB(*accent_color)
                p.drawString(50, y_position - 20, "No valid score data available for charts.")
        except Exception as chart_err:
            print(f"Chart generation error: {chart_err}")
            p.setFont("Helvetica", 9)
            p.setFillColorRGB(*accent_color)
            p.drawString(50, y_position - 20, "Chart generation failed")
        
        # Performance Insights
        y_position -= 230
        
        # Section Header
        p.setFillColorRGB(*secondary_color)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y_position, "PERFORMANCE INSIGHTS")
        y_position -= 25
        
        # Insight Cards
        top_subject = max([(sub, latest.get(f"{sub}_predicted", 0)) for sub in subjects], key=lambda x: x[1])
        weak_subject = min([(sub, latest.get(f"{sub}_predicted", 0)) for sub in subjects], key=lambda x: x[1])
        avg_score = latest.get('average', 0)
        
        insight_data = [
            ("Top Performing Subject", f"{top_subject[0].capitalize()} ({top_subject[1]}%)", primary_color),
            ("Needs Improvement", f"{weak_subject[0].capitalize()} ({weak_subject[1]}%)", accent_color),
            ("Recommendation", 
             "Focus on consistent practice across all subjects" if avg_score < 60 
             else "Excellent performance - maintain your efforts", 
             success_color if avg_score >= 60 else warning_color)
        ]
        
        card_width = (width - 100) / 3
        card_height = 70
        
        for i, (title, value, color) in enumerate(insight_data):
            draw_rounded_card(p, 50 + i*(card_width + 5), y_position - card_height, card_width - 10, card_height, color)
            p.setFillColorRGB(1, 1, 1)
            p.setFont("Helvetica-Bold", 9)
            p.drawCentredString(50 + i*(card_width + 5) + (card_width-10)/2, y_position - 40, title.upper())
            p.setFont("Helvetica", 8)
            text = p.beginText(50 + i*(card_width + 5) + 10, y_position - 60)
            text.setFont("Helvetica", 9)
            text.textLines(value)
            p.drawText(text)
        
        # Footer
        p.saveState()
        p.setFillColorRGB(0.9, 0.9, 0.9)
        p.rect(0, 20, width, 30, fill=1, stroke=0)
        p.setFillColorRGB(*secondary_color)
        p.setFont("Helvetica-Oblique", 7)
        p.drawCentredString(
            width / 2, 
            30,
            f"Generated by EduPredict • {pd.Timestamp.now().strftime('%d %b %Y %H:%M')} • Confidential"
        )
        p.restoreState()
        
        # Watermark (subtle)
        p.saveState()
        p.setFont("Helvetica", 40)
        p.setFillColorRGB(0.95, 0.95, 0.95)
        p.setFillAlpha(0.1)
        p.drawCentredString(width / 2, height / 2, "EDUPREDICT")
        p.restoreState()
        
        p.save()
        buffer.seek(0)
        
        # Generate filename
        student_name = user.get('name', 'student').replace(' ', '_')
        filename = f"Academic_Report_{student_name}_Sem_{semester}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as pdf_err:
        print(f"PDF generation error: {pdf_err}\n{traceback.format_exc()}")
        flash("An error occurred while generating the PDF report.", "danger")
        return redirect(url_for('tutor_student_view') if requesting_user['role'] == 'tutor' else url_for('student_dashboard'))

def draw_rounded_card(canvas, x, y, width, height, fill_color, radius=5):
    """Helper function to draw rounded rectangle cards"""
    canvas.saveState()
    canvas.setFillColor(fill_color)
    canvas.setStrokeColorRGB(0.8, 0.8, 0.8)
    canvas.setLineWidth(0.5)
    canvas.roundRect(x, y, width, height, radius, fill=1, stroke=1)
    canvas.restoreState()
    
# ==================== GENERATE INVITE CODE ====================
@app.route('/generate_invite', methods=['GET'])
@login_required(role="admin")  # Only admin can generate
def generate_invite():
    invite_code = 'TUTOR-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    try:
        db.tutor_invites.insert_one({'code': invite_code, 'used': False, 'created_at': pd.Timestamp.now()})
        flash(f"Invite code generated: {invite_code}", "success")
    except Exception as e:
        print(f"Error generating invite code: {e}")
        flash("Failed to generate invite code.", "danger")
    return redirect(url_for('admin_panel'))  # Redirect to admin panel


# ==================== TOGGLE TUTOR ACCESS (Admin Action) ====================
@app.route('/toggle_tutor_access/<tutor_uid>', methods=['POST'])
@login_required(role='admin')
def toggle_tutor_access(tutor_uid):
    try:
        tutor = db.users.find_one({'uid': tutor_uid, 'role': 'tutor'})
        if not tutor:
            flash('Tutor not found.', 'danger')
            return redirect(url_for('admin_panel'))

        current_status = tutor.get('access_restricted', False)
        new_status = not current_status

        db.users.update_one({'uid': tutor_uid}, {'$set': {'access_restricted': new_status}})

        # Optional: Disable tutor's Firebase account as well for complete restriction
        # try:
        #     auth.update_user(tutor_uid, disabled=new_status)
        # except Exception as firebase_err:
        #     print(f"Firebase user disable/enable error for {tutor_uid}: {firebase_err}")
        #     flash(f"Tutor access updated in DB, but Firebase status update failed: {firebase_err}", "warning")
        #     # Decide if you should revert DB change or just warn

        flash(f"Tutor '{tutor.get('name')}' access has been {'RESTRICTED' if new_status else 'UNRESTRICTED'}.", 'success')

    except Exception as e:
        print(f"Error toggling tutor access for {tutor_uid}: {e}\n{traceback.format_exc()}")
        flash("An error occurred while updating tutor access.", 'danger')

    return redirect(url_for('admin_panel'))



# ==================== REGISTER TUTOR ====================
@app.route('/tutor_register', methods=['GET', 'POST'])
def tutor_register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        invite_code = request.form.get('invite_code')

        if not all([email, password, name, invite_code]):
            flash("Please fill all fields.", "warning")
            return redirect(url_for('tutor_register'))

        # Validate invite code
        try:
            invite = db.tutor_invites.find_one({'code': invite_code})
            if not invite:
                 flash('Invalid invite code.', 'warning')
                 return redirect(url_for('tutor_register'))
            if invite.get('used'):
                 flash('This invite code has already been used.', 'warning')
                 return redirect(url_for('tutor_register'))

            # Check if user already exists before trying to create
            try:
                auth.get_user_by_email(email)
                flash("An account with this email already exists. Please log in.", "warning")
                return redirect(url_for('tutor_login'))
            except _auth_utils.UserNotFoundError:
                pass # Email is available

            # 1. Create the user in Firebase Authentication
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
                # Add email verification if desired: email_verified=False
            )

            # 2. Store tutor data in MongoDB
            db.users.insert_one({
                'uid': user.uid,
                'email': email,
                'name': name,
                'role': 'tutor', # Set the role to 'tutor'
                 # Add other tutor-specific fields if needed later
                 'access_restricted': False # Tutors aren't restricted by default here
            })

            # 3. Mark the invite code as used *after* successful user creation
            db.tutor_invites.update_one(
                 {'code': invite_code},
                 {'$set': {'used': True, 'used_by_uid': user.uid, 'used_at': pd.Timestamp.now()}}
            )

            flash('Tutor registered successfully. Please log in.', 'success')
            return redirect(url_for('tutor_login'))

        except Exception as e:
            print(f"Tutor Registration error: {e}\n{traceback.format_exc()}")
            # Attempt to clean up if Firebase user was created but DB insert failed
            try:
                 created_user = auth.get_user_by_email(email)
                 # Check if it's the one we potentially just created
                 # Be careful with cleanup logic. Maybe just log and alert admin.
                 # auth.delete_user(created_user.uid) # Use with caution
            except _auth_utils.UserNotFoundError:
                 pass # User wasn't created or was already deleted
            except Exception as cleanup_err:
                 print(f"Cleanup error during registration failure: {cleanup_err}")

            flash(f'Registration error: An unexpected issue occurred. Please try again.', 'danger')
            return redirect(url_for('tutor_register'))

    return render_template('tutor_register.html')



# ==================== TUTOR LOGIN ====================
@app.route('/tutor_login', methods=['GET', 'POST'])
def tutor_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')  # Handled client-side
        id_token = request.form.get('id_token')

        if not email or not password or not id_token:
            flash("Please fill in all required fields.", "warning")
            return redirect(url_for('tutor_login'))

        try:
            # Verify ID token
            decoded_token = auth.verify_id_token(id_token)
            uid_from_token = decoded_token['uid']

            # Fetch user data from MongoDB
            user_data = db.users.find_one({"uid": uid_from_token})

            if not user_data:
                flash("Tutor data not found in the database.", "danger")
                return redirect(url_for('tutor_login'))

            # Ensure email matches
            if user_data.get("email") != email:
                flash("Email mismatch. Authentication failed.", "danger")
                return redirect(url_for('tutor_login'))

            # Ensure role is tutor
            if user_data.get("role") != "tutor":
                flash("Access denied. This login is for tutors only.", "warning")
                return redirect(url_for('tutor_login'))

            # Check if login is restricted
            if user_data.get("access_restricted", False):
                flash("Your account has been restricted. Please contact admin.", "danger")
                return redirect(url_for('tutor_login'))

            # Set session
            session["user"] = {
                "email": user_data["email"],
                "uid": user_data["uid"],
                "name": user_data.get("name", ""),
                "role": user_data["role"]
            }

            flash("Tutor login successful.", "success")
            return redirect(url_for("tutor_dashboard"))

        except auth.InvalidIdTokenError:
            flash("Invalid token. Please login again.", "danger")
        except auth.ExpiredIdTokenError:
            flash("Session expired. Please login again.", "danger")
        except Exception as e:
            print(f"Tutor Login Error: {e}\n{traceback.format_exc()}")
            flash("An unexpected error occurred. Please try again.", "danger")

        return redirect(url_for('tutor_login'))

    return render_template("tutor_login.html")      
# ==================== ADMIN PANEL ====================
@app.route('/admin_panel')
@login_required(role='admin')
def admin_panel():
    try:
        tutors = list(db.users.find({'role': 'tutor'}))
        invites = list(db.tutor_invites.find().sort('created_at', -1)) # Sort by creation time

        # Prepare data for template (handle missing fields, convert ObjectId)
        processed_tutors = []
        for tutor in tutors:
            tutor['_id'] = str(tutor.get('_id')) # Convert ObjectId
            tutor['uid'] = tutor.get('uid', 'N/A')
            tutor['name'] = tutor.get('name', 'N/A')
            tutor['email'] = tutor.get('email', 'N/A')
            # tutor['gender'] = tutor.get('gender', 'N/A') # Gender not collected for tutors
            tutor['access_restricted'] = tutor.get('access_restricted', False)
            processed_tutors.append(tutor)

        processed_invites = []
        for invite in invites:
            invite['_id'] = str(invite.get('_id'))
            invite['used_by_email'] = 'N/A' # Fetch email if needed
            if invite.get('used') and invite.get('used_by_uid'):
                try:
                     used_by_user = db.users.find_one({'uid': invite['used_by_uid']}, {'email': 1})
                     if used_by_user:
                         invite['used_by_email'] = used_by_user.get('email', 'UID: ' + invite['used_by_uid'])
                     else:
                         invite['used_by_email'] = 'User not found (UID: ' + invite['used_by_uid'] +')'
                except Exception as find_err:
                     print(f"Error finding user for invite {invite['code']}: {find_err}")
                     invite['used_by_email'] = 'Error finding user'

            # Format dates if they are datetime objects
            if isinstance(invite.get('created_at'), pd.Timestamp):
                invite['created_at_str'] = invite['created_at'].strftime('%Y-%m-%d %H:%M')
            if isinstance(invite.get('used_at'), pd.Timestamp):
                invite['used_at_str'] = invite['used_at'].strftime('%Y-%m-%d %H:%M')

            processed_invites.append(invite)

        return render_template("admin_panel.html", tutors=processed_tutors, invites=processed_invites)
    except Exception as e:
        print(f"Error loading admin panel: {e}\n{traceback.format_exc()}")
        flash("Failed to load admin panel data.", "danger")
        return redirect(url_for('index')) # Or logout


# ==================== ADMIN LOGIN ====================
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Fetch admin credentials from environment variables
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_password = os.environ.get('ADMIN_PASSWORD')

        if not admin_email or not admin_password:
             flash('Admin account is not configured on the server.', 'danger')
             print("ERROR: ADMIN_EMAIL or ADMIN_PASSWORD environment variables not set.")
             return redirect(url_for('admin_login'))

        if email == admin_email and password == admin_password:
            # No Firebase check for the hardcoded admin. Use with caution.
            # Consider creating a proper admin user in Firebase/DB if needed.
            session['user'] = {
                'email': email,
                'uid': 'admin_special_uid',  # Keep a unique identifier
                'name': 'Administrator',
                'role': 'admin'
            }
            flash('Admin logged in successfully.', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Invalid admin credentials.', 'danger')
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')

# ==================== TUTOR DASHBOARD ====================
@app.route('/tutor_dashboard')
@login_required(role="tutor")
def tutor_dashboard():
    # Get all students
    students = list(db.users.find({"role": "student"}))
    
    # Calculate statistics
    total_students = len(students)
    passed_students = sum(1 for s in students if s.get('marks_history') and s['marks_history'][-1]['pass_status'] == 'Pass')
    failed_students = total_students - passed_students
    pass_percentage = (passed_students / total_students * 100) if total_students > 0 else 0
    
    # Calculate average subject scores
    subjects = ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']
    avg_subjects = {}
    
    for subject in subjects:
        scores = []
        for student in students:
            if student.get('marks_history'):
                latest = student['marks_history'][-1]
                scores.append(latest.get(f"{subject}_predicted", 0))
        if scores:
            avg_subjects[subject] = sum(scores) / len(scores)
    
    return render_template(
        'tutor_dashboard.html',
        students=students,
        total_students=total_students,
        passed_students=passed_students,
        failed_students=failed_students,
        pass_percentage=pass_percentage,
        avg_subjects=avg_subjects
    )
# ==================== TUTOR-STUDENT VIEW (Student List for Tutor) ====================
@app.route('/tutor/students')
@login_required(role="tutor")
def tutor_student_view():
    try:
        students = list(db.users.find({"role": "student"}).sort('name', 1))
        
        processed_students = []
        for idx, student in enumerate(students, 1):
            # Ensure 'marks_history' exists and has at least one entry
            marks_history = student.get('marks_history', [])
            latest_entry = marks_history[-1] if marks_history else {}

            # Extract predicted scores and internal marks from the latest entry
            predicted_scores = {
                subject: latest_entry.get(f"{subject}_predicted", "N/A")
                for subject in ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']
            }
            internal_marks = {
                subject: [
                    latest_entry.get(f"{subject}_internal1", "N/A"),
                    latest_entry.get(f"{subject}_internal2", "N/A"),
                    latest_entry.get(f"{subject}_internal3", "N/A")
                ]
                for subject in ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']
            }

            # Calculate average and pass status
            average = latest_entry.get("average", "N/A")
            pass_status = latest_entry.get("pass_status", "N/A")

            processed_students.append({
                's_no': idx,
                'uid': student.get('uid', 'N/A'),
                'name': student.get('name', 'N/A'),
                'email': student.get('email', 'N/A'),
                'predicted': predicted_scores,
                'internals': internal_marks,
                'average': average,
                'status': pass_status,
                'login_restricted': student.get('login_restricted', False)
            })
        
        return render_template(
            'tutor_student_view.html',
            students=processed_students,
            tutor_name=session['user']['name']
        )
        
    except Exception as e:
        print(f"Error fetching students: {str(e)}")
        flash('Error loading student data', 'danger')
        return render_template('tutor_student_view.html', students=[], tutor_name=session['user']['name'])


# ==================== TUTOR PREDICT FOR STUDENT ====================
@app.route('/tutor/predict-page/<student_uid>', methods=['GET'])
@login_required(role="tutor")
def tutor_student_prediction_page(student_uid):
    student = db.users.find_one({'uid': student_uid})
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('tutor_student_view'))

    return render_template(
        "home.html",
        student=student,
        student_uid=student_uid,
        student_name=student.get("name", ""),
        internal_marks={},        # Prevent Jinja error
        results=None,
        average=None,
        percentage=None,
        pass_status=None,
        selected_semester=""
    )


# ==================== TUTOR VIEW STUDENT DASHBOARD ====================
@app.route("/tutor/student/<student_uid>")
@login_required(role="tutor")
def tutor_view_student_dashboard(student_uid):
    try:
        # Get student data with proper error handling
        student_data = db.users.find_one({"uid": student_uid})
        if not student_data:
            flash("Student not found", "danger")
            return redirect(url_for('tutor_student_view'))

        # Process marks history with default values
        processed_history = []
        for entry in student_data.get("marks_history", []):
            # Ensure all required fields exist with default values
            processed_entry = {
                'semester': entry.get('semester', 'N/A'),
                'pass_status': entry.get('pass_status', 'Pending'),
                'average': entry.get('average', 0),
                'percentage': entry.get('percentage', 0),
                '_id': str(entry.get('_id', ''))
            }
            
            # Add all subject data with defaults
            subjects = ['math', 'physics', 'chemistry', 'cs', 'english', 'aptitude']
            for subject in subjects:
                processed_entry[f'{subject}_predicted'] = entry.get(f'{subject}_predicted', 0)
                processed_entry[f'{subject}_internal1'] = entry.get(f'{subject}_internal1', 0)
                processed_entry[f'{subject}_internal2'] = entry.get(f'{subject}_internal2', 0)
                processed_entry[f'{subject}_internal3'] = entry.get(f'{subject}_internal3', 0)
            
            processed_history.append(processed_entry)

        return render_template(
            "student_dashboard.html",
            user=student_data,
            history=processed_history,
            tutor_name=session['user']['name']
        )
        
    except Exception as e:
        print(f"Error viewing student dashboard: {str(e)}")
        flash("Error loading student dashboard", "danger")
        return redirect(url_for('tutor_student_view'))

# Add this to your route temporarily
@app.route('/tutor/student_debug')
@login_required(role="tutor")
def tutor_student_debug():
    student_uid = request.args.get('student_uid')  # Retrieve student_uid from the request arguments
    if not student_uid:
        flash("Student UID is missing.", "danger")
        return redirect(url_for('tutor_student_view'))  # Redirect to a relevant page
    student = db.users.find_one({'uid': student_uid})  # Retrieve the student from the database
    print(f"Attempting to view student: {student_uid}")
    print(f"Student found: {bool(student)}")
    print(f"Template path: {os.path.exists(os.path.join(app.template_folder, 'student_dashboard.html'))}")
@app.route('/tutor/toggle-login/<student_uid>', methods=['POST'])
@login_required(role="tutor")
def toggle_student_login(student_uid):
    """Allows tutor to restrict/unrestrict student login."""
    student = db.users.find_one({'uid': student_uid})
    if not student:
        flash('Student not found', 'danger')
        return redirect(url_for('tutor_student_view'))
    
    new_status = not student.get('login_restricted', False)
    db.users.update_one(
        {'uid': student_uid},
        {'$set': {'login_restricted': new_status}}
    )
    
    action = "restricted" if new_status else "unrestricted"
    flash(f'Login {action} for {student["name"]}', 'success')
    return redirect(url_for('tutor_student_view'))

# ======


# ==================== ASSIGN STUDENT TO TUTOR ====================
@app.route('/assign_student', methods=['POST'])
@login_required(role="tutor")
def assign_student():
    """Assigns a student to a tutor."""
    tutor_uid = session['user']['uid']
    student_uid = request.form.get('student_uid')

    # Input validation
    if not student_uid:
        flash('No student selected.', 'danger')
        return redirect(url_for('tutor_dashboard'))

    # Check if student exists and is a student
    student = db.users.find_one({'uid': student_uid, 'role': 'student'})
    if not student:
        flash('Invalid student selected.', 'danger')
        return redirect(url_for('tutor_dashboard'))

    # Check if the student is already assigned.
    tutor = db.users.find_one({'uid': tutor_uid}, {'assigned_students': 1})
    assigned_students = tutor.get('assigned_students', [])
    if student_uid in assigned_students:
        flash('Student already assigned to you.', 'warning') 
        return redirect(url_for('tutor_dashboard'))

    try:
        # Update the tutor's assigned_students list.
        db.users.update_one({'uid': tutor_uid}, {'$push': {'assigned_students': student_uid}})
        flash('Student assigned successfully.', 'success')
    except Exception as e:
        print(f"Error assigning student: {e}")
        flash('Failed to assign student.', 'danger')
    return redirect(url_for('tutor_dashboard'))


# ==================== UNASSIGN STUDENT FROM TUTOR ====================
@app.route('/unassign_student', methods=['POST'])
@login_required(role="tutor")
def unassign_student():
    """Unassigns a student from a tutor."""
    tutor_uid = session['user']['uid']
    student_uid = request.form.get('student_uid')

    # Input validation
    if not student_uid:
        flash('No student selected.', 'danger')
        return redirect(url_for('tutor_dashboard'))

     # Check if student exists and is a student
    student = db.users.find_one({'uid': student_uid, 'role': 'student'})
    if not student:
        flash('Invalid student selected.', 'danger')
        return redirect(url_for('tutor_dashboard'))

    try:
        # Remove the student from the tutor's assigned_students list.
        db.users.update_one({'uid': tutor_uid}, {'$pull': {'assigned_students': student_uid}})
        flash('Student unassigned successfully.', 'success')
    except Exception as e:
        print(f"Error unassigning student: {e}")
        flash('Failed to unassign student.', 'danger')
    return redirect(url_for('tutor_dashboard'))



# ==================== VIEW ALL STUDENTS (FOR ADMIN) ====================
@app.route('/admin/students')
@login_required(role="admin")
def admin_view_all_students():
    """View all students in the system."""
    students = list(db.users.find({'role': 'student'}, {'name': 1, 'uid': 1, 'email': 1}))
    for student in students:
        student['_id'] = str(student['_id'])
    return render_template('admin_view_students.html', students=students)  # New template


# ==================== VIEW ALL TUTORS (FOR ADMIN) ====================
@app.route('/admin/tutors')
@login_required(role="admin")
def admin_view_all_tutors():
    """View all tutors in the system."""
    tutors = list(db.users.find({'role': 'tutor'}, {'name': 1, 'uid': 1, 'email': 1}))
    for tutor in tutors:
        tutor['_id'] = str(tutor['_id'])
    return render_template('admin_view_tutors.html', tutors=tutors)  # New template


# ==================== STUDENT SEARCH (FOR TUTOR and ADMIN) ====================
@app.route('/search', methods=['GET'])
@login_required(role="tutor,admin")
def search():
    """Search for students by name or email."""
    query = request.args.get('query', '')  # Get the search query
    user_role = session.get('user').get('role')

    if not query:
        flash("Please enter a search query.", "warning")
        if user_role == 'tutor':
            return redirect(url_for('tutor_student_view'))
        else:
            return redirect(url_for('admin_view_all_students'))

    # Search the database
    search_results = list(db.users.find(
        {
            'role': 'student',  # Only search within students
            '$or': [
                {'name': {'$regex': query, '$options': 'i'}},  # Case-insensitive name search
                {'email': {'$regex': query, '$options': 'i'}}  # Case-insensitive email search
            ]
        },
        {'name': 1, 'uid': 1, 'email': 1} # only return these fields
    ))
    for result in search_results:
        result['_id'] = str(result['_id'])

    if not search_results:
        flash("No students found matching your query.", "info")
    # Render the appropriate template based on the user's role
    if user_role == 'tutor':
        return render_template('tutor_student_view.html', students=search_results, query=query, tutor_name=session['user']['name']) #same template
    else:
        return render_template('admin_view_students.html', students=search_results, query=query)  # You might need a new template


# ==================== RESTRICT STUDENT LOGIN (FOR TUTOR and ADMIN) ====================
@app.route('/restrict_login', methods=['POST'])
@login_required(role="tutor,admin")
def restrict_login():
    """Restrict a student's login."""
    student_uid = request.form.get('student_uid')
    tutor_uid = session.get('user').get('uid')
    user_role = session.get('user').get('role')

    if not student_uid:
        flash('No student selected.', 'danger')
        return redirect(request.referrer)  # Redirect back

    # Check if the student exists and is a student
    student = db.users.find_one({'uid': student_uid, 'role': 'student'})
    if not student:
        flash('Invalid student.', 'danger')
        return redirect(request.referrer)

    if user_role == 'tutor':
        # Check if the student is assigned to the tutor
        tutor = db.users.find_one({'uid': tutor_uid}, {'assigned_students': 1})
        assigned_students = tutor.get('assigned_students', [])
        if student_uid not in assigned_students:
            flash("You are not authorized to restrict this student's login.", "danger")
            return redirect(request.referrer)

    try:
        db.users.update_one({'uid': student_uid}, {'$set': {'login_restricted': True}})
        flash('Student login restricted.', 'success')
    except Exception as e:
        print(f"Error restricting login: {e}")
        flash('Failed to restrict student login.', 'danger')
    return redirect(request.referrer)

# ==================== UNRESTRICT STUDENT LOGIN (FOR TUTOR and ADMIN) ====================
@app.route('/unrestrict_login', methods=['POST'])
@login_required(role="tutor,admin")
def unrestrict_login():
    """Unrestrict a student's login."""
    student_uid = request.form.get('student_uid')
    tutor_uid = session.get('user').get('uid')
    user_role = session.get('user').get('role')

    if not student_uid:
        flash('No student selected.', 'danger')
        return redirect(request.referrer)  # Redirect back

    # Check if the student exists and is a student
    student = db.users.find_one({'uid': student_uid, 'role': 'student'})
    if not student:
        flash('Invalid student.', 'danger')
        return redirect(request.referrer)

    if user_role == 'tutor':
        # Check if the student is assigned to the tutor
        tutor = db.users.find_one({'uid': tutor_uid}, {'assigned_students': 1})
        assigned_students = tutor.get('assigned_students', [])
        if student_uid not in assigned_students:
            flash("You are not authorized to unrestrict this student's login.", "danger")
            return redirect(request.referrer)

    try:
        db.users.update_one({'uid': student_uid}, {'$set': {'login_restricted': False}})
        flash('Student login unrestricted.', 'success')
    except Exception as e:
        print(f"Error unrestricting login: {e}")
        flash('Failed to unrestrict student login.', 'danger')
    return redirect(request.referrer)



# ==================== LOGOUT ====================
@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))



# ==================== HOME ROUTE (Generic prediction form - might be less used now) ====================
# This might become redundant if prediction is always initiated from dashboards
# Kept for compatibility or direct access if needed.
@app.route('/home')
@login_required(role="student,tutor") # Can be accessed by logged-in users
def home():
    # If accessed directly, render the form without specific student context
    # Check if a student_uid is passed (e.g., from redirect after failed prediction)
    student_uid = request.args.get('student_uid')  # Check query params
    student_name = None
    internal_marks = {}
    if session['user']['role'] == 'tutor' and student_uid:
        try:
            student = db.users.find_one({'uid': student_uid}, {'name': 1})
            if student:
                student_name = student.get('name')
        except Exception as e:
            print(f"Error finding student name for home route: {e}")

    return render_template('home.html', results=None, student_uid=student_uid, student_name=student_name, internal_marks=internal_marks)


# ==================== MAIN ====================
if __name__ == "__main__":
    # Use Gunicorn or Waitress for production instead of Flask development server
    port = int(os.environ.get("PORT", 5000))  # Default to 5000 if PORT not set
    # For development: debug=True, use_reloader=True
    # For production: debug=False, use_reloader=False, threaded=True (or use WSGI server)
    app.run(host='0.0.0.0', port=port, debug=True)


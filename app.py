# -*- coding: utf-8 -*-
import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, session,send_file
from dotenv import load_dotenv
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, auth, _auth_utils
from firebase_admin.auth import UserNotFoundError
from config import FIREBASE_CREDENTIALS,FIREBASE_CONFIG# Assuming config.py exists with FIREBASE_CREDENTIALS
from src.pipeline.predict_pipline import CustomData, PredictPipline
from src.utils import login_required # Assuming utils.py exists with login_required decorator
import pandas as pd
from flask import Blueprint, request, send_file
import matplotlib
from matplotlib import pyplot as plt
from reportlab.lib.utils import ImageReader

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from collections import defaultdict  # Import defaultdict
from bson import ObjectId
import random
import string
import traceback
matplotlib.use('Agg')
 # For better error logging

# Define Blueprint (if used elsewhere, otherwise optional for this snippet)
# download_bp = Blueprint('download_bp', __name__)

# Initialize Flask App
application = Flask(__name__)
app = application
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_dev') # Use environment variable for production

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred)
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")
    # Depending on severity, you might want to exit or handle differently
    # exit(1)



# MongoDB setup
mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/student_performance") # Use env variable
try:
    client = MongoClient(mongo_uri)
    # The ismaster command is cheap and does not require auth.
    client.admin.command('ismaster')
    db = client.student_performance # Use the specific database name directly
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
            return redirect(url_for('tutor_dashboard')) # Or tutor_student_view
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

# Route to display the student dashboard
# @app.route("/student_dashboard")
# @login_required(role="student")  # Ensure only students access this route
# def student_dashboard():
#     user = session.get("user")
#     if not user:
#         flash("Please log in to access the dashboard.", "danger")
#         return redirect(url_for("login"))

#     # Get student data from MongoDB or Firebase as needed
#     student_data = db.students.find_one({"uid": user["uid"]})
#     return render_template("student_dashboard.html", student_data=student_data)

# # Example login_required decorator with role-based access
# def login_required(role=None):
#     """
#     Decorator to ensure a user is logged in and has the specified role.
#     :param role: Optional, the role that the user must have (e.g. "student", "admin")
#     """
#     from functools import wraps
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             if "user" not in session:
#                 flash("You need to log in first.", "warning")
#                 return redirect(url_for("login"))

#             # If a role is specified, check if the user's role matches
#             if role and session["user"].get("role") != role:
#                 flash(f"Access restricted to {role}s only.", "danger")
#                 return redirect(url_for("login"))

#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator



# Other routes like student_dashboard, register, etc.




# ==================== STUDENT DASHBOARD ====================
@app.route("/student_dashboard")
@login_required(role="student") # Ensure only students access this
def student_dashboard():
    user_session = session.get("user")
    if not user_session:
        return redirect(url_for('login')) # Should be caught by decorator, but safety first

    try:
        student_data = db.users.find_one({"uid": user_session["uid"]})
        if not student_data:
             flash("Could not retrieve student data.", "danger")
             return redirect(url_for('logout')) # Log out if data is missing

        # Convert ObjectIds in history for template rendering
        history = []
        for entry in student_data.get("marks_history", []):
            if isinstance(entry, dict) and '_id' in entry:
                 entry['_id'] = str(entry['_id'])
            history.append(entry)

        return render_template("student_dashboard.html", user=student_data, history=history)
    except Exception as e:
        print(f"Error fetching student dashboard data: {e}\n{traceback.format_exc()}")
        flash("An error occurred while loading your dashboard.", "danger")
        return redirect(url_for('logout'))


# ==================== PREDICT DATA (Handles Student & Tutor-for-Student) ====================
@app.route('/predictdata', methods=['GET', 'POST'])
@login_required(role="student,tutor")
def predict_datappoint():
    if request.method == 'POST':
        try:
            # Extract form values
            gender = request.form.get('gender')
            race_ethnicity = request.form.get('ethnicity')
            parental_level_of_education = request.form.get('parental_level_of_education')
            lunch = request.form.get('lunch')
            test_preparation_course = request.form.get('test_preparation_course')
            reading_score = float(request.form.get('reading_score'))
            writing_score = float(request.form.get('writing_score'))
            physics_score = float(request.form.get('physics_score'))
            chemistry_score = float(request.form.get('chemistry_score'))
            cs_score = float(request.form.get('cs_score'))

            # Create input dataframe
            data = CustomData(
                gender=gender,
                race_ethnicity=race_ethnicity,
                parental_level_of_education=parental_level_of_education,
                lunch=lunch,
                test_preparation_course=test_preparation_course,
                reading_score=reading_score,
                writing_score=writing_score
            )
            pred_df = data.get_data_as_data_frame()
            predict_pipeline = PredictPipline()
            results = predict_pipeline.predict(pred_df)
            predicted_score = round(float(results[0]), 2)

            # Score processing
            total_scores = predicted_score + reading_score + writing_score + physics_score + chemistry_score + cs_score
            average = round(total_scores / 6, 2)
            percentage = round((average / 100) * 100, 2)
            pass_status = "Pass" if percentage >= 45 else "Fail"

            new_entry = {
                "_id": ObjectId(),
                "predicted_math_score": predicted_score,
                "reading_score": reading_score,
                "writing_score": writing_score,
                "physics_score": physics_score,
                "chemistry_score": chemistry_score,
                "cs_score": cs_score,
                "average": average,
                "percentage": percentage,
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
                else:
                    flash("Missing student UID.", "danger")
                    return redirect(url_for('tutor_student_view'))

            elif user_role == 'student':
                db.users.update_one({"uid": session['user']['uid']}, {"$push": {"marks_history": new_entry}})
                flash("Prediction saved.", "success")

                return render_template(
                        "home.html",
                        results=predicted_score,
                        reading_score=reading_score,
                        writing_score=writing_score,
                        physics_score=physics_score,
                        chemistry_score=chemistry_score,
                        cs_score=cs_score,
                        average=average,
                        percentage=percentage,
                        pass_status=pass_status
                    )


        except Exception as e:
            print(f"Prediction Error: {e}\n{traceback.format_exc()}")
            flash("Prediction failed. Ensure all scores are valid.", "danger")
            return redirect(url_for('home'))

    # GET handler
    user_role = session.get('user', {}).get('role')
    if user_role == 'student':
        return render_template('home.html', results=None)
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

    # Only allow students to download their own report, tutors can download any
    if requesting_user['role'] == 'student' and requesting_user['uid'] != uid_to_download:
        flash("You are not authorized to download this report.", "danger")
        return redirect(url_for('student_dashboard'))

    user = db.users.find_one({'uid': uid_to_download, 'role': 'student'})
    if not user:
        flash("Student data not found.", "warning")
        if requesting_user['role'] == 'tutor':
            return redirect(url_for('tutor_student_view'))
        else:
            return redirect(url_for('student_dashboard'))

    history = user.get('marks_history', [])
    if not history:
        flash("No prediction history found for this student.", "warning")
        if requesting_user['role'] == 'tutor':
            return redirect(url_for('tutor_student_view'))
        else:
            return redirect(url_for('student_dashboard'))

    latest = history[-1]

    # Create chart
    chart_buffer = None
    try:
        chart_labels = ['Math', 'Reading', 'Writing', 'Physics', 'Chemistry', 'CS']
        chart_scores = [
            latest.get("predicted_math_score", 0),
            latest.get("reading_score", 0),
            latest.get("writing_score", 0),
            latest.get("physics_score", 0),
            latest.get("chemistry_score", 0),
            latest.get("cs_score", 0)
        ]

        valid_scores = [s for s in chart_scores if isinstance(s, (int, float))]
        valid_labels = [l for s, l in zip(chart_scores, chart_labels) if isinstance(s, (int, float))]

        if valid_scores:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.pie(valid_scores, labels=valid_labels, autopct='%1.1f%%', startangle=90)
            chart_buffer = BytesIO()
            plt.savefig(chart_buffer, format='PNG', bbox_inches='tight')
            chart_buffer.seek(0)
            plt.close(fig)
    except Exception as e:
        print(f"Chart generation error: {e}")
        chart_buffer = None

    # Create PDF
    try:
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        p.setFont("Helvetica-Bold", 16)
        p.drawCentredString(width / 2.0, height - 50, "Student Performance Report")
        p.setFont("Helvetica-Bold", 12)
        p.drawCentredString(width / 2.0, height - 70, user.get('name', 'N/A'))

        # Basic Info
        p.setFont("Helvetica", 11)
        p.drawString(inch, height - 100, f"Email: {user.get('email', 'N/A')}")
        p.drawString(inch, height - 115, f"Gender: {user.get('gender', 'N/A')}")
        p.drawString(inch, height - 130, f"UID: {user.get('uid', 'N/A')}")
        p.line(inch, height - 145, width - inch, height - 145)

        # Prediction Summary
        p.setFont("Helvetica-Bold", 14)
        p.drawString(inch, height - 170, "Latest Prediction Summary:")

        p.setFont("Helvetica", 11)
        y_position = height - 195
        line_height = 18
        col_x = inch + 10

        fields = [
            ("Math Score (Predicted)", latest.get("predicted_math_score")),
            ("Reading Score", latest.get("reading_score")),
            ("Writing Score", latest.get("writing_score")),
            ("Physics Score", latest.get("physics_score")),
            ("Chemistry Score", latest.get("chemistry_score")),
            ("Computer Science Score", latest.get("cs_score")),
        ]

        for label, value in fields:
            p.drawString(col_x, y_position, f"{label}: {value if value is not None else 'N/A'}")
            y_position -= line_height

        # Summary Stats
        y_position -= line_height
        p.setFont("Helvetica-Bold", 11)
        p.drawString(col_x, y_position, f"Overall Average: {latest.get('average', 'N/A')}")
        y_position -= line_height
        p.drawString(col_x, y_position, f"Overall Percentage: {latest.get('percentage', 'N/A')}%")
        y_position -= line_height
        p.drawString(col_x, y_position, f"Pass/Fail Status: {latest.get('pass_status', 'N/A')}")
        y_position -= line_height * 1.5

        # Insert Chart
        if chart_buffer:
            p.setFont("Helvetica-Bold", 14)
            p.drawString(inch, y_position, "Score Distribution Chart:")
            y_position -= line_height

            try:
                chart_image = ImageReader(chart_buffer)
                img_width, img_height = chart_image.getSize()
                aspect = img_height / float(img_width)

                max_chart_width = width - 2 * inch
                max_chart_height = inch * 3
                display_width = max_chart_width
                display_height = display_width * aspect

                if display_height > max_chart_height:
                    display_height = max_chart_height
                    display_width = display_height / aspect

                if y_position - display_height < 50:
                    p.showPage()
                    y_position = height - inch
                    p.setFont("Helvetica-Bold", 14)
                    p.drawString(inch, y_position, "Score Distribution Chart:")
                    y_position -= line_height

                p.drawImage(
                    chart_image,
                    (width - display_width) / 2.0,
                    y_position - display_height,
                    width=display_width,
                    height=display_height,
                    preserveAspectRatio=True
                )

            except Exception as chart_err:
                print(f"Error drawing chart image: {chart_err}")
                p.setFont("Helvetica-Oblique", 10)
                p.drawString(inch, y_position - 15, "(Chart could not be rendered)")
        else:
            p.setFont("Helvetica-Oblique", 10)
            p.drawString(inch, y_position - 15, "(No chart data available)")

        # Footer
        p.setFont("Helvetica-Oblique", 9)
        p.drawCentredString(width / 2.0, 30,
            f"Report generated on {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} by Student Performance System"
        )

        p.showPage()
        p.save()
        buffer.seek(0)

        download_name = f"{user.get('name', 'student').replace(' ', '_')}_performance_report.pdf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/pdf'
        )

    except Exception as pdf_err:
        print(f"PDF Generation Error: {pdf_err}\n{traceback.format_exc()}")
        flash("An error occurred while generating the PDF report.", "danger")
        if requesting_user['role'] == 'tutor':
            return redirect(url_for('tutor_student_view'))
        else:
            return redirect(url_for('student_dashboard'))
# ==================== GENERATE INVITE CODE ====================
@app.route('/generate_invite', methods=['GET'])
@login_required(role="admin")  # Only admin can generate
def generate_invite():
    invite_code = 'TUTOR-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    try:
        db.tutor_invites.insert_one({'code': invite_code, 'used': False, 'created_at': pd.Timestamp.now()})
        flash(f'New invite code generated: {invite_code}', 'success')
    except Exception as e:
        print(f"Error generating invite code: {e}")
        flash('Failed to generate invite code.', 'danger')
    return redirect(url_for('admin_panel'))

# ==================== TUTOR REGISTER ====================
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


@app.route("/tutor_view_student_dashboard/<student_uid>")
@login_required(role="tutor")
def tutor_view_student_dashboard(student_uid):
    try:
        student = db.users.find_one({"uid": student_uid, "role": "student"})
        if not student:
            flash("Student not found.", "danger")
            return redirect(url_for('tutor_student_view'))

        history = student.get("marks_history", [])
        for entry in history:
            if '_id' in entry:
                entry['_id'] = str(entry['_id'])

        return render_template("student_dashboard.html", user=student, history=history)

    except Exception as e:
        print(f"Error loading student dashboard for tutor: {e}")
        flash("Could not load student dashboard.", "danger")
        return redirect(url_for('tutor_student_view'))

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


# ==================== TUTOR DASHBOARD (Old - Kept for Reference/Stats) ====================
# This shows overall stats. The new primary view is tutor_student_view.
@app.route("/tutor_dashboard")
@login_required(role="tutor,admin") # Allow admin to see stats too
def tutor_dashboard():
    # This dashboard can now focus on aggregate statistics
    students = list(db.users.find({"role": "student"}))

    total_students = len(students)
    passed_students = 0
    failed_students = 0
    subject_scores = defaultdict(lambda: {'total': 0, 'count': 0}) # Store total and count for avg

    for student in students:
        latest_history = student.get("marks_history", [])
        if latest_history:
            latest_result = latest_history[-1] # Get the *last* entry

            if isinstance(latest_result, dict): # Ensure it's a dictionary
                if latest_result.get("pass_status") == "Pass":
                    passed_students += 1
                else: # Assumes 'Fail' or anything else is fail
                    failed_students += 1

                # Accumulate scores for averages, checking type
                subjects = ["predicted_math_score", "reading_score", "writing_score", "physics_score", "chemistry_score", "cs_score"]
                subject_keys_map = {"predicted_math_score": "Math", "reading_score": "Reading", "writing_score": "Writing", "physics_score": "Physics", "chemistry_score": "Chemistry", "cs_score": "CS"}

                for db_key in subjects:
                    score = latest_result.get(db_key)
                    if isinstance(score, (int, float)):
                        display_key = subject_keys_map.get(db_key, db_key)
                        subject_scores[display_key]['total'] += score
                        subject_scores[display_key]['count'] += 1

    # Calculate percentages
    pass_percentage = (passed_students / total_students * 100) if total_students > 0 else 0
    fail_percentage = (failed_students / total_students * 100) if total_students > 0 else 0

    # Calculate average scores per subject
    average_scores = {}
    for subject, data in subject_scores.items():
        average_scores[subject] = round(data['total'] / data['count'], 2) if data['count'] > 0 else 0

    return render_template(
        "tutor_dashboard.html", # Keep the old template for stats
        total_students=total_students,
        passed_students=passed_students,
        failed_students=failed_students,
        pass_percentage=pass_percentage,
        fail_percentage=fail_percentage,
        avg_subjects=average_scores
    )


# <<< NEW FEATURE >>> ==================== TUTOR STUDENT VIEW (Primary Table) ====================
@app.route("/tutor_student_view")
@login_required(role="tutor") # Only tutors access this primary view
def tutor_student_view():
    try:
        students = list(db.users.find({"role": "student"}))
        processed_students = []
        s_no = 1
        for student in students:
            latest_marks = {}
            history = student.get("marks_history", [])
            if history and isinstance(history[-1], dict):
                latest_marks = history[-1] # Get the last entry dictionary

            processed_students.append({
                's_no': s_no,
                'uid': student.get('uid', 'N/A'),
                'name': student.get('name', 'N/A'),
                'gender': student.get('gender', 'N/A'),
                'login_restricted': student.get('login_restricted', False), # Get restriction status
                # Safely get scores, defaulting to 'N/A' or 0 if missing
                'math': latest_marks.get('predicted_math_score', 'N/A'),
                'reading': latest_marks.get('reading_score', 'N/A'),
                'writing': latest_marks.get('writing_score', 'N/A'),
                'physics': latest_marks.get('physics_score', 'N/A'),
                'chemistry': latest_marks.get('chemistry_score', 'N/A'),
                'cs': latest_marks.get('cs_score', 'N/A'),
                'average': latest_marks.get('average', 'N/A'),
                'percentage': latest_marks.get('percentage', 'N/A'),
                'status': latest_marks.get('pass_status', 'N/A')
            })
            s_no += 1

        return render_template("tutor_student_view.html", students=processed_students)

    except Exception as e:
        print(f"Error loading tutor student view: {e}\n{traceback.format_exc()}")
        flash("An error occurred while loading student data.", "danger")
        return redirect(url_for('tutor_dashboard')) # Redirect to stats dashboard or logout


# <<< NEW FEATURE >>> ==================== TUTOR PREDICT FOR STUDENT (Form Access) ====================
@app.route('/tutor_predict_for_student/<student_uid>', methods=['GET'])
@login_required(role='tutor')
def tutor_predict_for_student(student_uid):
    try:
        student = db.users.find_one({'uid': student_uid, 'role': 'student'})
        if not student:
            flash("Student not found.", 'danger')
            return redirect(url_for('tutor_student_view'))

        # Render the *existing* prediction form, but pass the student_uid
        # The form's action should point to '/predictdata' (POST)
        return render_template('home.html', results=None, student_uid=student_uid, student_name=student.get('name'))

    except Exception as e:
        print(f"Error accessing prediction form for student {student_uid}: {e}\n{traceback.format_exc()}")
        flash("An error occurred while trying to predict for the student.", "danger")
        return redirect(url_for('tutor_student_view'))


# <<< NEW FEATURE >>> ==================== TOGGLE STUDENT LOGIN (Tutor Action) ====================
@app.route('/toggle_student_login/<student_uid>', methods=['POST'])
@login_required(role='tutor') # Only Tutors can restrict students
def toggle_student_login(student_uid):
    try:
        student = db.users.find_one({'uid': student_uid, 'role': 'student'})
        if not student:
            flash('Student not found.', 'danger')
            return redirect(url_for('tutor_student_view'))

        current_status = student.get('login_restricted', False)
        new_status = not current_status

        db.users.update_one({'uid': student_uid}, {'$set': {'login_restricted': new_status}})

        flash(f"Student '{student.get('name')}' login access has been {'RESTRICTED' if new_status else 'UNRESTRICTED'}.", 'success')

    except Exception as e:
        print(f"Error toggling student login for {student_uid}: {e}\n{traceback.format_exc()}")
        flash('An error occurred while updating student login status.', 'danger')

    return redirect(url_for('tutor_student_view')) # Redirect back to the table


# ==================== LOGOUT ====================
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("index")) # Redirect to landing page


# ==================== HOME ROUTE (Generic prediction form - might be less used now) ====================
# This might become redundant if prediction is always initiated from dashboards
# Kept for compatibility or direct access if needed.
@app.route('/home')
@login_required(role="student,tutor") # Can be accessed by logged-in users
def home():
     # If accessed directly, render the form without specific student context
     # Check if a student_uid is passed (e.g., from redirect after failed prediction)
     student_uid = request.args.get('student_uid') # Check query params
     student_name = None
     if session['user']['role'] == 'tutor' and student_uid:
         try:
             student = db.users.find_one({'uid': student_uid}, {'name': 1})
             if student:
                 student_name = student.get('name')
         except Exception as e:
             print(f"Error finding student name for home route: {e}")

     return render_template('home.html', results=None, student_uid=student_uid, student_name=student_name)

# ==================== MAIN ====================
if __name__ == "__main__":
    # Use Gunicorn or Waitress for production instead of Flask development server
    port = int(os.environ.get("PORT", 5000)) # Default to 5000 if PORT not set
    # For development: debug=True, use_reloader=True
    # For production: debug=False, use_reloader=False, threaded=True (or use WSGI server)
    app.run(host='0.0.0.0', port=port, debug=True) # Debug=True for development ONLY
import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, auth, _auth_utils
from config import FIREBASE_CREDENTIALS
from src.pipeline.predict_pipline import CustomData, PredictPipline
from src.utils import login_required
import pandas as pd
from flask import Blueprint, request, send_file
from matplotlib import pyplot as plt
from reportlab.lib.utils import ImageReader

# Define Blueprint
download_bp = Blueprint('download_bp', __name__)
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
# from database import db  

# Initialize Flask App
application = Flask(__name__)
app = application

# app.register_blueprint(download_bp)
app.secret_key = 'muhsin'  # For production, use env variable

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS)
    firebase_admin.initialize_app(cred)

# MongoDB setup
mongo_uri = "mongodb://localhost:27017/student_performance"
client = MongoClient(mongo_uri)
db = client['student_performance']

# ==================== ROOT ====================
@app.route('/')
def index():
    return render_template('index.html')


# ==================== REGISTER ====================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if len(password) < 6:
            flash("Password must be at least 6 characters long")
            return redirect(url_for('register'))

        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )

            db.users.insert_one({
                "uid": user.uid,
                "email": email,
                "name": name,
                "gender": request.form.get("gender"),
                "role": request.form.get("role", "student"),
                "marks_history": []  # Store prediction history
            })

            flash("Registration successful! You can now login.")
            return redirect(url_for("login"))

        except Exception as e:
            flash(f"Error: {e}")
            return redirect(url_for("register"))

    return render_template("register.html")


# ==================== LOGIN ====================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        try:
            user = auth.get_user_by_email(email)
            user_data = db.users.find_one({"uid": user.uid})

            if not user_data:
                flash("User not found in database.")
                return redirect(url_for("login"))

            session["user"] = {
                "email": user.email,
                "uid": user.uid,
                "name": user.display_name,
                "role": user_data.get("role", "student")
            }

            flash("Login successful.")
            return redirect(url_for("student_dashboard") if session["user"]["role"] == "student" else url_for("tutor_dashboard"))

        except _auth_utils.UserNotFoundError:
            flash("No account found with that email.")
            return redirect(url_for("register"))
        except Exception as e:
            flash(f"Login error: {e}")
            return redirect(url_for("login"))

    return render_template("login.html")


# ==================== STUDENT DASHBOARD ====================
@app.route("/student_dashboard")
@login_required(role="student")
def student_dashboard():
    user = session.get("user")
    student_data = db.users.find_one({"uid": user["uid"]})
    history = student_data.get("marks_history", [])
    return render_template("student_dashboard.html", user=student_data, history=history)


# ==================== PREDICT DATA ====================
@app.route('/predictdata', methods=['GET', 'POST'])
@login_required(role="student,tutor")
def predict_datappoint():
    if request.method == 'POST':
        try:
            gender = request.form.get('gender')
            race_ethnicity = request.form.get('ethnicity')
            lunch = request.form.get('lunch')
            parental_level_of_education = request.form.get('parental_level_of_education')
            test_preparation_course = request.form.get('test_preparation_course')

            reading_score = float(request.form.get('reading_score'))
            writing_score = float(request.form.get('writing_score'))
            physics_score = float(request.form.get('physics_score'))
            chemistry_score = float(request.form.get('chemistry_score'))
            cs_score = float(request.form.get('cs_score'))

            # Create input DataFrame
            data = CustomData(
                gender=gender,
                race_ethnicity=race_ethnicity,
                lunch=lunch,
                parental_level_of_education=parental_level_of_education,
                test_preparation_course=test_preparation_course,
                reading_score=reading_score,
                writing_score=writing_score
            )
            pred_df = data.get_data_as_data_frame()

            # Prediction
            predict_pipeline = PredictPipline()
            results = predict_pipeline.predict(pred_df)
            predicted_score = round(float(results[0]), 2)

            # Calculate overall average, percentage, pass/fail
            total = predicted_score + reading_score + writing_score + physics_score + chemistry_score + cs_score
            average = round(total / 6, 2)
            percentage = round((average / 100) * 100, 2)
            pass_status = "Pass" if percentage >= 45 else "Fail"

            # Save to MongoDB
            user = session["user"]
            new_entry = {
                "predicted_math_score": predicted_score,
                "reading_score": reading_score,
                "writing_score": writing_score,
                "physics_score": physics_score,
                "chemistry_score": chemistry_score,
                "cs_score": cs_score,
                "average": average,
                "percentage": percentage,
                "pass_status": pass_status
            }

            db.users.update_one(
                {"uid": user["uid"]},
                {"$push": {"marks_history": new_entry}}
            )

            return render_template(
                'home.html',
                results=predicted_score,
                average=average,
                percentage=percentage,
                reading_score=reading_score,
                writing_score=writing_score,
                physics_score=physics_score,
                chemistry_score=chemistry_score,
                cs_score=cs_score,
                pass_status=pass_status
            )

        except Exception as e:
            print(f"Prediction error: {e}")
            flash(f"Prediction error: {e}", "danger")
            return redirect(url_for("student_dashboard"))

    return render_template('home.html', results=None)


# ==================== DOWNLOAD REPORT ====================


@app.route('/download_report', methods=['POST'])  # Use POST since you're sending UID
@login_required(role="student,tutor")
def download_report():
    uid = request.form.get('uid')

    # Get user profile from MongoDB
    user = db.users.find_one({'uid': uid})
    if not user:
        return "User not found", 404

    history = user.get('marks_history', [])
    if not history:
        return "No prediction history found", 404

    latest = history[-1]

    # Generate pie chart
    chart_labels = ['Math', 'Reading', 'Writing', 'Physics', 'Chemistry', 'CS']
    chart_scores = [
        latest.get("predicted_math_score"),
        latest.get("reading_score"),
        latest.get("writing_score"),
        latest.get("physics_score"),
        latest.get("chemistry_score"),
        latest.get("cs_score")
    ]

    # Create a chart in memory
    fig, ax = plt.subplots()
    ax.pie(chart_scores, labels=chart_labels, autopct='%1.1f%%', startangle=90)
    ax.set_title('Subject-wise Score Distribution')
    chart_buffer = BytesIO()
    plt.savefig(chart_buffer, format='PNG')
    chart_buffer.seek(0)
    plt.close()

    # Create PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Header Info
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, f"Student Report - {user.get('name')}")

    p.setFont("Helvetica", 12)
    p.drawString(50, height - 80, f"Email: {user.get('email')}")
    p.drawString(50, height - 100, f"Gender: {user.get('gender')}")

    # Report Section
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 140, "Latest Prediction Summary:")

    p.setFont("Helvetica", 12)
    fields = [
        ("Math (Predicted)", latest.get("predicted_math_score")),
        ("Reading", latest.get("reading_score")),
        ("Writing", latest.get("writing_score")),
        ("Physics", latest.get("physics_score")),
        ("Chemistry", latest.get("chemistry_score")),
        ("Computer Science", latest.get("cs_score")),
        ("Average", latest.get("average")),
        ("Percentage", f"{latest.get('percentage')}%"),
        ("Status", latest.get("pass_status")),
    ]

    y = height - 170
    for label, value in fields:
        p.drawString(70, y, f"{label}: {value}")
        y -= 20

    # Insert Chart
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y - 20, "Performance Chart:")
    chart_image = ImageReader(chart_buffer)
    p.drawImage(chart_image, 70, y - 250, width=400, height=250)  # Adjust size/position if needed

    # Footer
    p.setFont("Helvetica-Oblique", 10)
    p.drawString(50, 30, "Generated by Student Performance System")

    p.showPage()
    p.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{user.get('name')}_report.pdf",
        mimetype='application/pdf'
    )



# ==================== TUTOR DASHBOARD ====================
@app.route("/tutor_dashboard")
@login_required(role="tutor")
def tutor_dashboard():
    students = list(db.users.find({"role": "student"}))
    return render_template("tutor_dashboard.html", students=students)


# ==================== LOGOUT ====================
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("index"))


# ==================== HOME ROUTE ====================
@app.route('/home')
def home():
    return render_template('home.html', results=None)

# ==================== MAIN ====================



if __name__ == "__main__":
    app.run(debug=True)

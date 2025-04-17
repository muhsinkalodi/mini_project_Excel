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
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# Initialize Flask App
application = Flask(__name__)
app = application
app.secret_key = 'muhsin'  # Consider using an environment variable for security

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
                "marks": [],
                "predicted_marks": []
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
            role = user_data.get("role", "student")
            return redirect(url_for("student_dashboard") if role == "student" else url_for("tutor_dashboard"))

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
    if not user:
        flash("You are not logged in.", "danger")
        return redirect(url_for("login"))

    student_data = db.users.find_one({"uid": user["uid"]})
    return render_template("student_dashboard.html", user=student_data)


# ==================== PREDICT DATA ====================
@app.route('/predictdata', methods=['GET', 'POST'])
@login_required(role="student,tutor")
def predict_datappoint():
    if request.method == 'POST':
        print("✅ POST request received.")
        try:
            # Extract form data
            gender = request.form.get('gender')
            race_ethnicity = request.form.get('ethnicity')
            lunch = request.form.get('lunch')
            parental_level_of_education = request.form.get('parental_level_of_education')
            test_preparation_course = request.form.get('test_preparation_course')
            reading_score = float(request.form.get('reading_score'))
            writing_score = float(request.form.get('writing_score'))

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
            print(pred_df)

            # Predict
            predict_pipeline = PredictPipline()
            results = predict_pipeline.predict(pred_df)

            predicted_score = results[0].item() if isinstance(results[0], np.ndarray) else results[0]
            predicted_score = round(float(predicted_score), 2)

            # Average, percentage, pass/fail
            average = round((predicted_score + reading_score + writing_score) / 3, 2)
            percentage = round((average / 100) * 100, 2)
            pass_status = "Pass" if percentage >= 45 else "Fail"

            # Save to DB
            user = session["user"]
            db.users.update_one(
                {"uid": user["uid"]},
                {
                    "$push": {
                        "marks": {
                            "reading": reading_score,
                            "writing": writing_score
                        },
                        "predicted_marks": predicted_score
                    }
                }
            )

            db.predictions.insert_one({
                "user_id": user["uid"],
                "predicted_score": predicted_score,
                "reading_score": reading_score,
                "writing_score": writing_score,
                "average_score": average,
                "percentage": percentage,
                "pass_status": pass_status
            })

            print("✅ Prediction saved successfully.")

            # ✅ Render with all needed values
            return render_template(
                'home.html',
                results=predicted_score,
                average=average,
                percentage=percentage,
                reading_score=reading_score,
                writing_score=writing_score,
                pass_status=pass_status
            )

        except Exception as e:
            print(f"Error: {e}")
            flash(f"Prediction error: {e}", "danger")
            return redirect(url_for("student_dashboard"))

    print("✅ GET request received.")
    return render_template('home.html', results=None, average=None, pass_status=None)


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
    # Fix: provide default None values to avoid Jinja errors
    return render_template('home.html', results=None, average=None, pass_status=None)


# ==================== MAIN ====================
if __name__ == "__main__":
    app.run(debug=True)

from flask import Blueprint, render_template, session
from src.utils import login_required
from pymongo import MongoClient

student_bp = Blueprint('student', __name__)
client = MongoClient("mongodb://localhost:27017/student_performance")
db = client['student_performance']

@student_bp.route('/student/dashboard')
@login_required(role='student')
def student_dashboard():
    user_email = session.get("user", {}).get("email")
    user_data = db.users.find_one({"email": user_email})

    # Dummy subject marks - Replace with real DB values later
    performance_data = {
        "Math": user_data.get("math_score", 0),
        "Reading": user_data.get("reading_score", 0),
        "Writing": user_data.get("writing_score", 0)
    }

    return render_template("student_dashboard.html", user=user_data, performance=performance_data)

# config.py
import os
from dotenv import load_dotenv



# Firebase Configuration
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyBn_iWTs20aDePYq1Q8BOD9mwNT7X2_W9s",
    "authDomain": "student-performance-app-3e7d7.firebaseapp.com",
    "projectId": "student-performance-app-3e7d7",
    "storageBucket": "student-performance-app-3e7d7.appspot.com",
    "messagingSenderId": "237531360212",
    "appId": "1:237531360212:web:242060fa878751c16b8441",
    "measurementId": "G-KRZYS5KW7K",
    "databaseURL": ""  # Optional: Only if you use Firebase Realtime Database
}
FIREBASE_CREDENTIALS = "student-performance-app-3e7d7-firebase-adminsdk-fbsvc-ab6415d037.json"

# MongoDB Configuration
MONGO_URI = "mongodb+srv://muhsinkalodi9311:4gw8TReTfRlXvDXM@student-performance.pzommxd.mongodb.net/student_performance?retryWrites=true&w=majority&appName=student-performance"  # Or use your cloud URI
MONGO_DB_NAME = "student_performance"

load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret-key")
JWT_ALGORITHM = "HS256"
print("Secret Key:", os.getenv("SECRET_KEY"))
print("JWT Secret:", os.getenv("JWT_SECRET"))



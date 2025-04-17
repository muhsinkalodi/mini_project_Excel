# src/__init__.py
from flask import Flask

app = Flask(__name__)

# Import routes
from src.routes.auth_routes import *
from src.routes.student_routes import *
from src.routes.tutor_routes import *

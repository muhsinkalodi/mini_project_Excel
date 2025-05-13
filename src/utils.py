import os
import sys
import dill
import jwt
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
from sklearn.metrics import r2_score
from sklearn.model_selection import GridSearchCV
from flask import session, redirect, url_for, flash, request
from functools import wraps

from src.exception import CustomException
from config import JWT_SECRET, JWT_ALGORITHM


### 🔐 Authentication Helpers

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = session.get("user")
            if not user:
                flash("Please login to access this page.", "warning")
                return redirect(url_for("login"))
            if role:
                allowed_roles = role.split(",")
                if user.get("role") not in allowed_roles:
                    flash("Unauthorized access.", "danger")
                    return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapper
    return decorator

def generate_token(user_data):
    payload = {
        "user": user_data,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["user"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    token = request.cookies.get("token")
    if token:
        return decode_token(token)
    return None

def jwt_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash("You must be logged in to access this page.")
                return redirect(url_for("login"))
            if role and user.get("role") != role:
                flash("Access denied.")
                return redirect(url_for("index"))
            return func(*args, **kwargs)
        return wrapper
    return decorator


### 🧪 Model Utilities

def save_object(file_path, obj):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as file_obj:
            dill.dump(obj, file_obj)
    except Exception as e:
        raise CustomException(e, sys)

def load_object(file_path):
    try:
        with open(file_path, 'rb') as file_obj:
            return dill.load(file_obj)
    except Exception as e:
        raise CustomException(e, sys)


### 📊 Model Evaluation

def evaluate_model(x_train, y_train, x_test, y_test, models, param):
    try:
        report = {}
        for i in range(len(models)):
            model = list(models.values())[i]
            model_name = list(models.keys())[i]
            params = param.get(model_name, {})

            gs = GridSearchCV(model, params, cv=3)
            gs.fit(x_train, y_train)

            model.set_params(**gs.best_params_)
            model.fit(x_train, y_train)

            y_test_pred = model.predict(x_test)
            test_score = r2_score(y_test, y_test_pred)
            report[model_name] = test_score
        return report
    except Exception as e:
        raise CustomException(e, sys)

def evaluate_model_multi(x_train, y_train, x_test, y_test, models: dict):
    try:
        report = {}
        for name, model in models.items():
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)

            r2_scores = [
                r2_score(y_test[:, i], y_pred[:, i])
                for i in range(y_test.shape[1])
            ]
            avg_r2 = sum(r2_scores) / len(r2_scores)
            report[name] = avg_r2
        return report
    except Exception as e:
        raise CustomException(e, sys)


### 📈 Chart Generation

def generate_chart(reading, writing, predicted):
    labels = ['Reading', 'Writing', 'Predicted Math']
    scores = [reading, writing, predicted]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, scores, color=['skyblue', 'lightgreen', 'salmon'])
    ax.set_ylim(0, 100)
    ax.set_ylabel('Score')
    ax.set_title('Performance Breakdown')

    for bar, score in zip(bars, scores):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, height + 1, f'{score}', ha='center', va='bottom')

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)

    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    return image_base64

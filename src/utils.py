import os
import sys

# Add the src directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..config.py')))

import numpy as np
import pandas as pd
from src.exception import CustomException
import dill
from sklearn.metrics import r2_score
from sklearn.model_selection import GridSearchCV
from functools import wraps
from flask import session, redirect, url_for, flash
import jwt
import datetime
from flask import request
from config import JWT_SECRET, JWT_ALGORITHM
from dotenv import load_dotenv
from functools import wraps
import matplotlib.pyplot as plt
import io
import base64



def save_object(file_path, obj):
    try:
        dir_path = os.path.dirname(file_path)
        os.makedirs(dir_path, exist_ok=True)

        with open (file_path, 'wb') as file_obj:
            dill.dump(obj, file_obj)

    except Exception as e:
        raise CustomException(e, sys)

def evaluate_model(x_train, y_train, x_test, y_test,models,param):
    try:
        report = {}
        for i in range(len(list(models))):
            model = list(models.values())[i]
            para=param[list(models.keys())[i]]

            gs = GridSearchCV(
                model,
                para,
                cv=3
                # n_jobs=n,
                # verbose=verbose,
                # refit=refit
            )

            gs.fit(x_train, y_train)

            model.set_params(**gs.best_params_)
            model.fit(x_train, y_train)


            # model.fit(x_train, y_train)
            y_train_pred = model.predict(x_train)
            y_test_pred = model.predict(x_test)
            train_model_score = r2_score(y_train, y_train_pred)
            test_model_score  = r2_score(y_test, y_test_pred)
            report[list(models.keys())[i]] = test_model_score
        return report
    except Exception as e:
        raise CustomException(e, sys)
    


def load_object(file_path):
    try:
        with open(file_path, 'rb') as file_obj:
            return dill.load(file_obj)
    except Exception as e:
        raise CustomException(e, sys)
    

def login_required(role=None):
    def wrapper(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            user = session.get("user")
            if not user:
                flash("You must be logged in to access this page.")
                return redirect(url_for("login"))
            if role and user.get("role") != role:
                flash("Access denied.")
                return redirect(url_for("index"))
            return func(*args, **kwargs)
        return decorated_function
    return wrapper





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




def generate_chart(reading, writing, predicted):
    # Data for chart
    labels = ['Reading', 'Writing', 'Predicted Math']
    scores = [reading, writing, predicted]

    # Create the plot
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, scores, color=['skyblue', 'lightgreen', 'salmon'])
    ax.set_ylim(0, 100)
    ax.set_ylabel('Score')
    ax.set_title('Performance Breakdown')

    # Annotate bars with score values
    for bar, score in zip(bars, scores):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, height + 1, f'{score}', ha='center', va='bottom')

    # Save to BytesIO buffer
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)

    # Encode to base64
    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    return image_base64

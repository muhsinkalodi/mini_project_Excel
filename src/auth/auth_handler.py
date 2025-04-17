import firebase_admin
from firebase_admin import credentials, auth
from flask import make_response, redirect, url_for
from config import FIREBASE_CREDENTIALS,JWT_SECRET
from firebase_admin.exceptions import FirebaseError

# Initialize Firebase app (only once)
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS)
    firebase_admin.initialize_app(cred)


def register_user_with_name(email, password, name):
    try:
        user = auth.create_user(
            email=email,
            password=password,
            display_name=name
        )
        return {"success": True, "uid": user.uid}
    except auth.EmailAlreadyExistsError:
        return {"success": False, "error": "Email already registered"}
    except FirebaseError as e:
        return {"success": False, "error": str(e)}


def login_user(email, password):
    try:
        # Firebase authentication logic here (for example, sign in the user)
        user = auth.get_user_by_email(email)
        if user:
            # Assuming you are checking password manually or through a token
            return {"success": True, "uid": user.uid}
        else:
            return {"success": False, "error": "User not found"}
    except FirebaseError as e:
        return {"success": False, "error": str(e)}


def handle_user_response(email, user_role):
    from itsdangerous import TimedJSONWebSignatureSerializer as Serializer

    def generate_token(data, secret_key='secret', expires_in=3600):
        s = Serializer(secret_key, expires_in=expires_in)
        return s.dumps(data).decode('utf-8')

    token = generate_token({"email": email, "role": user_role})
    response = make_response(redirect(url_for("home")))
    response.set_cookie("token", token)
    return response

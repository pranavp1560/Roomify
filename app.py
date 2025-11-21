from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from flask_bcrypt import Bcrypt
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from routes import room_bp
from routes.mess import mess
from routes.student import student
from db import students, room_owners, mess_owners, rooms_collection, mess_collection


app = Flask(__name__)
app.secret_key = "supersecretkey"  
bcrypt = Bcrypt(app)

# ===========================
# Mail Configuration
# ===========================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'pranavpp1560@gmail.com'
app.config['MAIL_PASSWORD'] = 'hyzsttraqojntydd'
mail = Mail(app)

s = URLSafeTimedSerializer(app.secret_key)

# ===========================
# MongoDB Connections
# ===========================
# client = MongoClient("mongodb+srv://Roomify:Iwp9NrwIej23KCdw@cluster0.91rfyx0.mongodb.net/")
# db = client["roomify_db"]
# students = db["students"]
# room_owners = db["room_owners"]
# mess_owners = db["mess_owners"]

# # Room & Mess Collections
# room_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
# room_db = room_client["room_db"]
# rooms_collection = room_db["rooms"]

# mess_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
# mess_db = mess_client["mess_db"]
# mess_collection = mess_db["messes"]



# ===========================
# Role-based mappings
# ===========================
role_collections = {
    "student": students,
    "room_owner": room_owners,
    "mess_owner": mess_owners
}

role_pages = {
    "student": "student_page.html",
    "room_owner": "room_page.html",
    "mess_owner": "mess_page.html",
}

# ===========================
# Routes
# ===========================
@app.route('/')
def first():
    return render_template('select_role.html')

# ✅ STUDENT DASHBOARD
@app.route("/student_page")
def student_page():
    user = session.get("user")
    if not user or user.get("role") != "student":
        flash("Please log in as a student first.", "warning")
        return redirect(url_for("login", role="student"))

    rooms = list(rooms_collection.find())
    messes = list(mess_collection.find())
    return render_template("student_page.html", user=user, rooms=rooms, messes=messes)

# ✅ ROOM DETAILS PAGE
@app.route("/room/<room_id>")
def room_details(room_id):
    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        flash("Room not found!", "danger")
        return redirect(url_for("student_page"))
    return render_template("room_details.html", room=room)

# ✅ MESS DETAILS PAGE
@app.route("/mess/<mess_id>")
def mess_details(mess_id):
    m = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not m:
        flash("Mess not found!", "danger")
        return redirect(url_for("student_page"))
    return render_template("mess_details.html", mess=m)

# ===========================
# LOGIN ROUTE
# # ===========================
# @app.route('/login/<role>', methods=['GET', 'POST'])
# def login(role):
#     if role not in role_collections:
#         return "Invalid role", 404

#     collection = role_collections[role]

#     if request.method == "POST":
#         mobile = request.form.get("mobile")
#         password = request.form.get("password")

#         user = collection.find_one({"mobile": mobile})

#         if user and bcrypt.check_password_hash(user["password"], password):
#             session["user"] = {"name": user["name"], "role": role}
#             session["user_id"] = str(user["_id"])
#             session["role"] = role

#             # Redirect to correct dashboard
#             if role == "room_owner":
#                 return redirect(url_for("room.profile"))
#             elif role == "mess_owner":
#                 return redirect(url_for("mess.profile"))
#             elif role == "student":
#                 return redirect(url_for("student_page"))

#     return render_template("login.html", role=role)
@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if role not in role_collections:
        return "Invalid role", 404

    collection = role_collections[role]

    if request.method == "POST":
        mobile = request.form.get("mobile")
        password = request.form.get("password")

        user = collection.find_one({"mobile": mobile})

        if user and bcrypt.check_password_hash(user["password"], password):

            # Complete session data
            session["user"] = {
                "name": user.get("name"),
                "email": user.get("email"),
                "mobile": user.get("mobile"),
                "role": role,
                "student_info": user.get("student_info", {}),
                "verification_status": user.get("verification_status", "not_submitted")
            }

            session["user_id"] = str(user["_id"])
            session["role"] = role

            if role == "room_owner":
                return redirect(url_for("room.profile"))
            elif role == "mess_owner":
                return redirect(url_for("mess.profile"))
            elif role == "student":
                return redirect(url_for("student_page"))

    return render_template("login.html", role=role)


# ===========================
# REGISTER ROUTE
# ===========================
@app.route('/register/<role>', methods=['GET', 'POST'])
def register(role):
    if role not in role_collections:
        return "Invalid role", 404

    collection = role_collections[role]

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        mobile = request.form.get("mobile")
        password = request.form.get("password")

        if collection.find_one({"mobile": mobile}):
            flash("User with this mobile already exists!", "danger")
            return redirect(url_for("register", role=role))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        collection.insert_one({
            "name": name,
            "email": email,
            "mobile": mobile,
            "password": hashed_password
        })

        flash(f"{role.capitalize()} registered successfully! Please log in.", "success")
        return redirect(url_for("login", role=role))

    return render_template("register.html", role=role)

# ===========================
# FORGOT PASSWORD
# ===========================
@app.route('/forgot-password/<role>', methods=['GET', 'POST'])
def forgot_password(role):
    if role not in role_collections:
        return "Invalid role", 404

    collection = role_collections[role]

    if request.method == "POST":
        mobile = request.form.get("mobile")
        user = collection.find_one({"mobile": mobile})

        if user:
            token = s.dumps({"mobile": mobile, "role": role}, salt="password-reset")
            reset_url = url_for('reset_password', token=token, _external=True)

            msg = Message("Roomify Password Reset", sender="your_email@gmail.com", recipients=[user['email']])
            msg.body = f"Click the link to reset your password:\n{reset_url}"
            mail.send(msg)
            flash("Password reset link sent to your registered email.", "success")
        else:
            flash("Mobile number not found.", "danger")

    return render_template("forgot_password.html", role=role)

# ===========================
# RESET PASSWORD
# ===========================
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        data = s.loads(token, salt="password-reset", max_age=3600)
        mobile = data['mobile']
        role = data['role']
    except:
        flash("Invalid or expired token", "danger")
        return redirect(url_for('login', role='student'))

    collection = role_collections.get(role)
    user = collection.find_one({"mobile": mobile})

    if request.method == "POST":
        new_password = request.form.get("password")
        hashed_pw = bcrypt.generate_password_hash(new_password).decode('utf-8')
        collection.update_one({"mobile": mobile}, {"$set": {"password": hashed_pw}})
        flash("Password updated successfully!", "success")
        return redirect(url_for('login', role=role))

    return render_template("reset_password.html", role=role)

# ===========================
# LOGOUT
# ===========================
@app.route('/logout')
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("first"))

# ===========================
# TEST ROUTE
# ===========================
@app.route('/test')
def test_page():
    return render_template("base.html")

# Register Blueprints
app.register_blueprint(room_bp)
app.register_blueprint(mess)
app.register_blueprint(student)

@app.route('/dashboard/<role>')
def dashboard_redirect(role):
    if role == "student":
        return redirect(url_for("student.dashboard"))
    elif role == "room_owner":
        return redirect(url_for("room.profile"))
    elif role == "mess_owner":
        return redirect(url_for("mess.profile"))
    else:
        flash("Invalid role!", "danger")
        return redirect(url_for("first"))


if __name__ == '__main__':
    app.run(debug=True)

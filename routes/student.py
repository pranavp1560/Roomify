from flask import Blueprint, render_template, request, session, flash, redirect, url_for, jsonify
from bson.objectid import ObjectId
from pymongo import MongoClient
from pyzbar.pyzbar import decode
from PIL import Image
from io import BytesIO
import requests
from datetime import datetime
import cloudinary
import cloudinary.uploader
from pdf2image import convert_from_bytes
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from db import room_owners

# Cloudinary config (use your real keys or rely on existing app-wide config)
cloudinary.config(
    cloud_name="dzqe0yfzf",
    api_key="335187996581477",
    api_secret="4XwZEkqJo0XIeakpf2_dBaCvIuI"
)


from db import students, rooms_collection, mess_collection

student = Blueprint("student", __name__, url_prefix="/student")


sia = SentimentIntensityAnalyzer()


@student.route("/dashboard")
def dashboard():
    if "user_id" not in session or session.get("role") != "student":
        flash("Please login as student first.", "warning")
        return redirect(url_for("login", role="student"))

    # Fetch all rooms and messes
    rooms = list(rooms_collection.find())
    messes = list(mess_collection.find())

    return render_template(
        "student_page.html",
        user=session["user"],
        rooms=rooms,
        messes=messes
    )




@student.route("/search")
def search():
    user = session.get("user")
    if not user or user.get("role") != "student":
        flash("Please log in as a student first.", "warning")
        return redirect(url_for("login", role="student"))

    query = request.args.get("q", "").lower()
    selected_types = request.args.getlist("type")
    price_filters = request.args.getlist("price")

    room_query = {}
    mess_query = {}

    # === TEXT SEARCH ===
    if query:
        room_query["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"address": {"$regex": query, "$options": "i"}},
        ]
        mess_query["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"type": {"$regex": query, "$options": "i"}},
        ]

    # === FILTERS: Room / Mess Type ===
    include_rooms = not selected_types or "room" in selected_types
    include_messes = not selected_types or "mess" in selected_types

    # === FILTERS: Price ===
    if "below2000" in price_filters and "above2000" not in price_filters:
        room_query["rent"] = {"$lt": 2000}
        mess_query["monthly_charge"] = {"$lt": 2000}
    elif "above2000" in price_filters and "below2000" not in price_filters:
        room_query["rent"] = {"$gte": 2000}
        mess_query["monthly_charge"] = {"$gte": 2000}

    rooms = list(rooms_collection.find(room_query)) if include_rooms else []
    messes = list(mess_collection.find(mess_query)) if include_messes else []

    return render_template("student_page.html", user=user, rooms=rooms, messes=messes)




# @student.route("/room/<room_id>")
# def room_details(room_id):
#     room = rooms_collection.find_one({"_id": ObjectId(room_id)})
#     if not room:
#         flash("Room not found!", "danger")
#         return redirect(url_for("student.dashboard"))
#     return render_template("room_details.html", room=room)


@student.route("/room/<room_id>")
def room_details(room_id):
    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        flash("Room not found!", "danger")
        return redirect(url_for("student.dashboard"))

    # Correct owner lookup
    owner = room_owners.find_one({"_id": ObjectId(room["owner_id"])})

    owner_mobile = owner["mobile"] if owner else None

    # Ratings
    reviews = room.get("reviews", [])
    avg_rating = round(sum(int(r["rating"]) for r in reviews) / len(reviews), 1) if reviews else None

    return render_template(
        "room_details.html",
        room=room,
        avg_rating=avg_rating,
        owner_mobile=owner_mobile
    )



@student.route("/mess/<mess_id>")
def mess_details(mess_id):
    m = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not m:
        flash("Mess not found!", "danger")
        return redirect(url_for("student.dashboard"))
    return render_template("mess_details.html", mess=m)


@student.route("/profile")
def profile():
    if "user_id" not in session or session.get("role") != "student":
        flash("Login required.", "warning")
        return redirect(url_for("login", role="student"))

    db_user = students.find_one({"_id": ObjectId(session["user_id"])})

    return render_template("student_profile.html", user=db_user)


@student.route("/update_profile", methods=["POST"])
def update_profile():
    if "user_id" not in session:
        flash("Login required.", "warning")
        return redirect(url_for("login", role="student"))

    user_id = session["user_id"]
    old = students.find_one({"_id": ObjectId(user_id)})
    old_info = old.get("student_info", {}) if old else {}

    # form fields
    name = request.form.get("name")
    mobile = request.form.get("mobile")
    address = request.form.get("address")
    college = request.form.get("college")

    # Aadhaar Upload
    aadhaar_url = old_info.get("aadhaar_file", "")
    aadhaar_file = request.files.get("aadhaar")

    if aadhaar_file and aadhaar_file.filename != "":
        upload = cloudinary.uploader.upload(aadhaar_file, resource_type="auto")
        aadhaar_url = upload.get("secure_url")

    # College ID Upload
    college_url = old_info.get("college_id_file", "")
    college_id_file = request.files.get("college_id")

    if college_id_file and college_id_file.filename != "":
        upload = cloudinary.uploader.upload(college_id_file, resource_type="auto")
        college_url = upload.get("secure_url")

    # Save updated data
    students.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "verification_status": "pending",  
            "student_info": {
                "name": name,
                "mobile": mobile,
                "address": address,
                "college": college,
                "aadhaar_file": aadhaar_url,
                "college_id_file": college_url
            },
            "updated_on": datetime.now().strftime("%Y-%m-%d %H:%M")
        }}
    )

    flash("Applied Successfully! Your documents are submitted.", "success")
    return redirect(url_for("student.dashboard"))   # redirect to student_page


@student.route("/sentiment/view/<item_type>/<item_id>")
def view_sentiment_student(item_type, item_id):

    if "user_id" not in session or session.get("role") != "student":
        flash("Please login as student first.", "warning")
        return redirect(url_for("login", role="student"))

    if item_type == "room":
        item = rooms_collection.find_one({"_id": ObjectId(item_id)})
        if not item:
            flash("Room not found!", "danger")
            return redirect(url_for("student.dashboard"))

        reviews = item.get("reviews", [])
        chart_url = url_for("room.sentiment_chart", room_id=item_id)

    elif item_type == "mess":
        item = mess_collection.find_one({"_id": ObjectId(item_id)})
        if not item:
            flash("Mess not found!", "danger")
            return redirect(url_for("student.dashboard"))

        reviews = item.get("reviews", [])
        chart_url = url_for("mess.mess_sentiment_chart", mess_id=item_id)

    else:
        flash("Invalid selection.", "danger")
        return redirect(url_for("student.dashboard"))

    # Calculate sentiment
    positive = neutral = negative = total_rating = 0
    for r in reviews:
        score = sia.polarity_scores(r["comment"])["compound"]
        if score >= 0.05:
            positive += 1
        elif score <= -0.05:
            negative += 1
        else:
            neutral += 1
        total_rating += int(r["rating"])

    total_reviews = len(reviews)
    avg_rating = round(total_rating / total_reviews, 2) if total_reviews else 0

    return render_template(
        "view_sentiment_student.html",
        item=item,
        item_type=item_type,
        positive=positive,
        negative=negative,
        neutral=neutral,
        avg_rating=avg_rating,
        total=total_reviews,
        chart_url=chart_url
    )

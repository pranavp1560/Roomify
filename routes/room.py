from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
import cloudinary
import cloudinary.uploader
import cloudinary.api
from utils.sentiment import analyze_sentiment
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
from flask import Response

from db import students, rooms_collection, mess_collection


cloudinary.config(
    cloud_name="dzqe0yfzf",
    api_key="335187996581477",
    api_secret="4XwZEkqJo0XIeakpf2_dBaCvIuI"
)


# ===========================
# MongoDB Connection (Rooms DB)
# ===========================
room_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
room_db = room_client["room_db"]
rooms_collection = room_db["rooms"]

room_bp = Blueprint("room", __name__, url_prefix="/rooms")

# ===========================
# USERS COLLECTION (for fetching student details)
# ===========================
user_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
user_db = user_client["users_db"]   # ✅ Use your actual DB name
users_collection = user_db["users"]  


# Profile / Dashboard page for Room Owner
@room_bp.route("/profile")
def profile():
    # ✅ Ensure user is logged in
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id or role != "room_owner":
        flash("Please login as Room Owner first", "warning")
        return redirect(url_for("login", role="room_owner"))

    # ✅ Always store/compare owner_id as string
    user_id = str(session.get("user_id"))

    # ✅ Check if this user already created a room
    existing_room = rooms_collection.find_one({"owner_id": user_id})

    if existing_room:
    # 🧮 Dynamically calculate available rooms
        total = int(existing_room.get("total_rooms", 0))
        hosted_count = len(existing_room.get("hosted_students", []))
        available = max(total - hosted_count, 0)

        # ✅ Update only if needed (optional)
        rooms_collection.update_one(
            {"_id": existing_room["_id"]},
            {"$set": {"available_rooms": available}}
        )

        # Reflect updated value in the displayed object
        existing_room["available_rooms"] = available

        return render_template(
            "room_profile.html",
            room=existing_room,
            owner={
                "name": session["user"]["name"],
                "photo": "/static/img/owner.png"
            }
        )

    else:
        # ❌ No room yet → show Add Room dashboard
        return render_template(
            "room_page.html",
            user=session["user"],
            existing_room=None
        )



# Add Room
@room_bp.route("/add", methods=["POST"])
def add_room():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please login first", "warning")
        return redirect(url_for("login", role="room_owner"))

    # Prevent duplicate room creation
    existing_room = rooms_collection.find_one({"owner_id": user_id})
    if existing_room:
        flash("You already created a room. Please edit it instead.", "warning")
        return redirect(url_for("room.profile"))

    room_data = {
        "owner_id": str(user_id),
        "name": request.form.get("name"),
        "rent": int(request.form.get("rent")),
        "total_rooms": request.form.get("total_rooms"),
        "available_rooms": request.form.get("available_rooms"),
        "address": request.form.get("address"),
        "room_type": request.form.get("room_type"),
        "for_gender": request.form.get("for_gender"),
        "features": request.form.getlist("features"),
        "feature_other": request.form.get("feature_other"),
        "rules": request.form.getlist("rules"),
        "rule_other": request.form.get("rule_other"),
        "images": []
    }

    rooms_collection.insert_one(room_data)
    flash(f"Room '{room_data['name']}' added successfully!", "success")
    return redirect(url_for("room.profile"))


# Edit Room
@room_bp.route("/edit/<room_id>", methods=["GET", "POST"])
def edit_room(room_id):
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id or role != "room_owner":
        flash("Please login as Room Owner first", "warning")
        return redirect(url_for("login", role="room_owner"))

    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        flash("Room not found!", "danger")
        return redirect(url_for("room.profile"))

    if request.method == "POST":
        updated_data = {
            "name": request.form.get("name"),
            "rent": int(request.form.get("rent")),
            "total_rooms": request.form.get("total_rooms"),
            "available_rooms": request.form.get("available_rooms"),
            "address": request.form.get("address"),
            "room_type": request.form.get("room_type"),
            "for_gender": request.form.get("for_gender"),
            "features": request.form.getlist("features"),
            "feature_other": request.form.get("feature_other"),
            "rules": request.form.getlist("rules"),
            "rule_other": request.form.get("rule_other"),
        }

        # Clean empty optional fields
        if not updated_data["feature_other"]:
            updated_data.pop("feature_other")
        if not updated_data["rule_other"]:
            updated_data.pop("rule_other")

        rooms_collection.update_one({"_id": ObjectId(room_id)}, {"$set": updated_data})
        flash("Room updated successfully!", "success")
        return redirect(url_for("room.profile"))

    return render_template("edit_room.html", room=room)



@room_bp.route("/upload_image/<room_id>", methods=["POST"])
def upload_room_image(room_id):
    if "image" not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for("room.profile"))

    image = request.files["image"]
    if image.filename == "":
        flash("No selected file", "warning")
        return redirect(url_for("room.profile"))

    # Upload to Cloudinary
    upload_result = cloudinary.uploader.upload(image)
    image_url = upload_result.get("secure_url")

    # Save image URL to MongoDB
    rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$push": {"images": image_url}}
    )

    flash("Image uploaded successfully!", "success")
    return redirect(url_for("room.profile"))

@room_bp.route("/delete_image/<room_id>", methods=["POST"])
def delete_room_image(room_id):
    image_url = request.form.get("image_url")

    if not image_url:
        flash("Image not found!", "danger")
        return redirect(url_for("room.profile", room_id=room_id))

    # Delete image from Cloudinary (optional but good)
    try:
        public_id = image_url.split("/")[-1].split(".")[0]  # Extract public ID
        cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print("Cloudinary deletion error:", e)

    # Remove image URL from MongoDB
    rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$pull": {"images": image_url}}
    )

    flash("Image deleted successfully!", "success")
    return redirect(url_for("room.profile", room_id=room_id))

@room_bp.route("/upload_3d_view/<room_id>", methods=["POST"])
def upload_3d_view(room_id):
    import base64, io, os
    from PIL import Image
    import numpy as np, cv2
    from bson import ObjectId
    from app import mongo  # adjust if different

    data = request.json.get("frames", [])
    images = []
    for frame in data:
        img_data = base64.b64decode(frame.split(",")[1])
        img = Image.open(io.BytesIO(img_data))
        images.append(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))

    stitcher = cv2.Stitcher_create()
    (status, pano) = stitcher.stitch(images)
    if status == cv2.STITCHER_OK:
        os.makedirs("static/uploads", exist_ok=True)
        filename = f"static/uploads/pano_{room_id}.jpg"
        cv2.imwrite(filename, pano)
        url = url_for("static", filename=f"uploads/pano_{room_id}.jpg")

        # Save in DB
        mongo.db.rooms.update_one({"_id": ObjectId(room_id)}, {"$set": {"three_d_view": url}})

        return {"url": url}
    else:
        return {"error": f"Stitching failed with status {status}"}, 500



@room_bp.route("/apply/<room_id>", methods=["POST"])
def apply_room(room_id):
    if "user_id" not in session or session.get("role") != "student":
        flash("Please login as student first.", "warning")
        return redirect(url_for("login", role="student"))

    student_id = str(session["user_id"])

    # Fetch student from session first
    student = session.get("user")
    if not student:
        flash("Student info not found in session!", "danger")
        return redirect(url_for("student.dashboard"))

    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        flash("Room not found!", "danger")
        return redirect(url_for("student.dashboard"))

    # Prepare request entry
    request_entry = {
        "_id": ObjectId(),
        "student_id": student_id,
        "student_name": student.get("name", "Unknown"),
        "student_mobile": student.get("mobile", "Unknown"),
        "status": "pending"
    }

    result = rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$push": {"requests": request_entry}}
    )

    user = session["user"]
    if user.get("verification_status") != "verified":
        flash("Please verify your documents before applying.", "danger")
        return redirect(url_for("student.profile"))

    print("UPDATE RESULT:", result.modified_count)  # DEBUG LOG

    flash("Room request submitted!", "success")
    return redirect(url_for("student.room_details", room_id=room_id))



# @room_bp.route("/requests")
# def view_requests():
#     if "user_id" not in session or session.get("role") != "room_owner":
#         flash("Please login as Room Owner first", "warning")
#         return redirect(url_for("login", role="room_owner"))

#     owner_id = str(session["user_id"])
#     room = rooms_collection.find_one({"owner_id": owner_id})
#     requests_list = room.get("requests", [])


#     if not room:
#         flash("No room found.", "warning")
#         return redirect(url_for("room.profile"))

#     requests_list = room.get("requests", [])

#     return render_template("room_requests.html", room=room, requests=requests_list)

# @room_bp.route("/requests")
# def view_requests():
#     if "user_id" not in session or session.get("role") != "room_owner":
#         flash("Login as Room Owner first!", "warning")
#         return redirect(url_for("login", role="room_owner"))

#     owner_id = str(session["user_id"])
#     room_data = rooms_collection.find_one({"owner_id": owner_id})

#     if not room_data:
#         flash("No room found.", "warning")
#         return redirect(url_for("room.profile"))

#     requests_list = room_data.get("requests", [])
#     enriched_requests = []

#     for req in requests_list:
#         student = students.find_one({"_id": ObjectId(req["student_id"])})
#         student_info = student.get("student_info", {}) if student else {}

#         enriched_requests.append({
#             "_id": req["_id"],
#             "status": req.get("status", "pending"),
#             "student_info": {
#                 "name": student_info.get("name", "Unknown"),
#                 "mobile": student_info.get("mobile", "Unknown"),
#                 "address": student_info.get("address", "Unknown"),
#                 "college": student_info.get("college", "Unknown"),
#                 "aadhaar_file": student_info.get("aadhaar_file", "#"),
#                 "college_id_file": student_info.get("college_id_file", "#"),
#             }
#         })

#     return render_template("room_requests.html", room=room_data, requests=enriched_requests)





@room_bp.route("/requests")
def view_requests():
    if "user_id" not in session or session.get("role") != "room_owner":
        flash("Please login as Room Owner first", "warning")
        return redirect(url_for("login", role="room_owner"))

    owner_id = str(session["user_id"])
    room = rooms_collection.find_one({"owner_id": owner_id})

    if not room:
        flash("No room found.", "warning")
        return redirect(url_for("room.profile"))

    requests_list = room.get("requests", [])

    enriched_requests = []
    for req in requests_list:
        student_obj = students.find_one({"_id": ObjectId(req["student_id"])})

        enriched_requests.append({
            "_id": req["_id"],                      # IMPORTANT — SAME AS MESS
            "student_info": student_obj.get("student_info", {}) if student_obj else {}
        })

    return render_template(
        "room_requests.html",
        room=room,
        requests=enriched_requests
    )

@room_bp.route("/requests/accept/<room_id>/<request_id>", methods=["POST"])
def accept_request(room_id, request_id):

    room_obj = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room_obj:
        flash("Room not found!", "danger")
        return redirect(url_for("room.view_requests"))

    req = next((r for r in room_obj.get("requests", []) if str(r["_id"]) == request_id), None)
    if not req:
        flash("Request not found!", "danger")
        return redirect(url_for("room.view_requests"))

    student_obj = students.find_one({"_id": ObjectId(req["student_id"])})
    student_info = student_obj.get("student_info", {}) if student_obj else {}

    hosted_entry = {
        "student_id": req["student_id"],
        "name": student_info.get("name", ""),
        "mobile": student_info.get("mobile", ""),
        "address": student_info.get("address", ""),
        "college": student_info.get("college", ""),
        "aadhaar_file": student_info.get("aadhaar_file", "#"),
        "college_id_file": student_info.get("college_id_file", "#")
    }

    # Prevent duplicates
    already_hosted = any(h["student_id"] == hosted_entry["student_id"] for h in room_obj.get("hosted_students", []))
    if not already_hosted:
        rooms_collection.update_one(
            {"_id": ObjectId(room_id)},
            {"$push": {"hosted_students": hosted_entry}}
        )

    # Remove request
    rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$pull": {"requests": {"_id": ObjectId(request_id)}}}
    )

    flash("Request accepted!", "success")
    return redirect(url_for("room.view_requests"))



@room_bp.route("/requests/reject/<room_id>/<request_id>", methods=["POST"])
def reject_request(room_id, request_id):
    rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$pull": {"requests": {"_id": ObjectId(request_id)}}}
    )
    flash("Request rejected!", "info")
    return redirect(url_for("room.view_requests"))




# @room_bp.route("/hosted")
# def hosted_students():
#     room = rooms_collection.find_one({"owner_id": str(session.get("user_id"))})
#     return render_template("hosted_students.html", room=room)


@room_bp.route("/hosted")
def hosted_students():
    if "user_id" not in session or session.get("role") != "room_owner":
        flash("Please login as Room Owner first", "warning")
        return redirect(url_for("login", role="room_owner"))

    room = rooms_collection.find_one({"owner_id": str(session.get("user_id"))})

    hosted_list = room.get("hosted_students", [])

    return render_template(
        "hosted_students.html",
        room=room,
        hosted_students=hosted_list
    )


from datetime import datetime


sia = SentimentIntensityAnalyzer()

@room_bp.route("/review/<room_id>", methods=["POST"])
def add_review(room_id):
    # Check login
    if "user_id" not in session or session.get("role") != "student":
        flash("Please log in as a student to review.", "warning")
        return redirect(url_for("login", role="student"))

    student_id = str(session["user_id"])
    student_name = session["user"].get("name", "Anonymous")

    rating = int(request.form.get("rating", 0))
    comment = request.form.get("comment", "").strip()

    # Validate
    if rating < 1 or rating > 5 or not comment:
        flash("Please provide a valid rating and comment.", "danger")
        return redirect(url_for("student.room_details", room_id=room_id))

    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        flash("Room not found.", "danger")
        return redirect(url_for("student.dashboard"))

    # Check if hosted
    hosted = room.get("hosted_students", [])
    is_hosted = any(h["student_id"] == student_id for h in hosted)

    if not is_hosted:
        flash("Only hosted students can review this room.", "warning")
        return redirect(url_for("student.room_details", room_id=room_id))

    # Prevent duplicate
    for r in room.get("reviews", []):
        if r["student_id"] == student_id:
            flash("You have already reviewed this room.", "info")
            return redirect(url_for("student.room_details", room_id=room_id))

    # 🔥 Sentiment Analysis
    sentiment_data = analyze_sentiment(comment, rating)

    review = {
        "_id": ObjectId(),
        "student_id": student_id,
        "student_name": student_name,
        "rating": rating,
        "comment": comment,
        "sentiment": sentiment_data["sentiment"],
        "sentiment_score": sentiment_data["final_score"],
        "date": datetime.now().strftime("%Y-%m-%d")
    }

    rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$push": {"reviews": review}}
    )

    flash("Thank you for your review!", "success")
    return redirect(url_for("student.room_details", room_id=room_id))



@room_bp.route("/sentiment/<room_id>")
def room_sentiment(room_id):

    if "user_id" not in session or session.get("role") != "room_owner":
        flash("Please login as Room Owner first", "warning")
        return redirect(url_for("login", role="room_owner"))

    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        flash("Room not found", "danger")
        return redirect(url_for("room.profile"))

    reviews = room.get("reviews", [])

    total_reviews = len(reviews)
    positive = negative = neutral = 0
    total_rating = 0

    for r in reviews:
        score = sia.polarity_scores(r["comment"])["compound"]

        if score >= 0.05:
            positive += 1
        elif score <= -0.05:
            negative += 1
        else:
            neutral += 1

        total_rating += int(r["rating"])

    avg_rating = round(total_rating / total_reviews, 2) if total_reviews else 0
    
   
    
    room = rooms_collection.find_one({"_id": ObjectId(room_id)})



    return render_template(
        "room_sentiment.html",
        room=room,
        total=total_reviews,
        positive=positive,
        negative=negative,
        neutral=neutral,
        avg_rating=avg_rating
    )

@room_bp.route("/sentiment_chart/<room_id>")
def sentiment_chart(room_id):

    room = rooms_collection.find_one({"_id": ObjectId(room_id)})
    if not room:
        return "Room not found", 404

    reviews = room.get("reviews", [])
    positive = negative = neutral = 0

    for r in reviews:
        score = sia.polarity_scores(r["comment"])["compound"]
        if score >= 0.05:
            positive += 1
        elif score <= -0.05:
            negative += 1
        else:
            neutral += 1

    labels = ["Positive", "Neutral", "Negative"]
    sizes = [positive, neutral, negative]
    colors = ["#4caf50", "#ffc107", "#f44336"]

    # Create plot
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors)
    ax.set_title("Sentiment Distribution")

    # Save into memory
    buffer = BytesIO()
    plt.savefig(buffer, format="png", bbox_inches='tight')
    buffer.seek(0)
    plt.close()

    return Response(buffer.getvalue(), mimetype='image/png')

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
import cloudinary
import cloudinary.uploader
import cloudinary.api
from datetime import datetime
from utils.sentiment import analyze_sentiment
from datetime import datetime
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from db import students, rooms_collection, mess_collection
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
from flask import Response

sia = SentimentIntensityAnalyzer()


# ===========================
# Cloudinary Config
# ===========================
cloudinary.config(
    cloud_name="dzqe0yfzf",
    api_key="335187996581477",
    api_secret="4XwZEkqJo0XIeakpf2_dBaCvIuI"
)

# ===========================
# MongoDB Connection (Mess DB)
# ===========================
mess_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
mess_db = mess_client["mess_db"]
mess_collection = mess_db["messes"]

# ===========================
# Flask Blueprint
# ===========================
mess = Blueprint("mess", __name__, url_prefix="/mess")

# ===========================
# Profile / Dashboard for Mess Owner
# ===========================
@mess.route("/profile")
def profile():
    user_id = session.get("user_id")
    role = session.get("role")

    # Must be logged in as mess_owner
    if not user_id or role != "mess_owner":
        flash("Please login as Mess Owner first", "warning")
        return redirect(url_for("login", role="mess_owner"))

    user_id = str(user_id)
    existing_mess = mess_collection.find_one({"owner_id": user_id})

    # ✅ If mess exists → show profile
    if existing_mess:
        return render_template(
            "mess_profile.html",
            mess=existing_mess,
            owner={
                "name": session["user"]["name"],
                "photo": "/static/img/owner.png"
            }
        )

    # ❌ No mess yet → show Add Mess page
    return render_template(
        "mess_page.html",
        user=session["user"],
        existing_mess=None
    )

# ===========================
# Add Mess
# ===========================
@mess.route("/add", methods=["POST"])
def add_mess():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please login first", "warning")
        return redirect(url_for("login", role="mess_owner"))

    user_id = str(user_id)

    # Prevent duplicate creation
    existing_mess = mess_collection.find_one({"owner_id": user_id})
    if existing_mess:
        flash("You already created a mess. Redirecting to your profile.", "info")
        return redirect(url_for("mess.profile"))

    # Insert new mess
    mess_data = {
        "owner_id": user_id,
        "name": request.form.get("name"),
        "type": request.form.get("type"),
        "monthly_charge": int(request.form.get("monthly_charge")),
        "address": request.form.get("address"),
        "food_type": request.form.get("food_type"),
        "for_gender": request.form.get("for_gender"),
        "features": request.form.getlist("features"),
        "feature_other": request.form.get("feature_other"),
        "rules": request.form.getlist("rules"),
        "rule_other": request.form.get("rule_other"),
        "images": []
    }

    mess_collection.insert_one(mess_data)
    flash(f"Mess '{mess_data['name']}' added successfully!", "success")

    # ✅ Redirect directly to profile after adding
    return redirect(url_for("mess.profile"))

# ===========================
# Edit Mess
# ===========================
@mess.route("/edit/<mess_id>", methods=["GET", "POST"])
def edit_mess(mess_id):
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id or role != "mess_owner":
        flash("Please login as Mess Owner first", "warning")
        return redirect(url_for("login", role="mess_owner"))

    mess = mess_collection.find_one({"_id": ObjectId(mess_id)})

    if not mess:
        flash("Mess not found!", "danger")
        return redirect(url_for("mess.profile"))

    if request.method == "POST":
        updated_data = {
            "name": request.form.get("name"),
            "type": request.form.get("type"),
            "monthly_charge": int(request.form.get("monthly_charge")),
            "address": request.form.get("address"),
            "food_type": request.form.get("food_type"),
            "for_gender": request.form.get("for_gender"),
            "features": request.form.getlist("features"),
            "feature_other": request.form.get("feature_other"),
            "rules": request.form.getlist("rules"),
            "rule_other": request.form.get("rule_other"),
        }

        # Clean optional empty fields
        if not updated_data["feature_other"]:
            updated_data.pop("feature_other")
        if not updated_data["rule_other"]:
            updated_data.pop("rule_other")

        mess_collection.update_one({"_id": ObjectId(mess_id)}, {"$set": updated_data})
        flash("Mess updated successfully!", "success")
        return redirect(url_for("mess.profile"))

    return render_template("edit_mess.html", mess=mess)


# ===========================
# Upload Image
# ===========================
@mess.route("/upload_image/<mess_id>", methods=["POST"])
def upload_mess_image(mess_id):
    if "image" not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for("mess.profile"))

    image = request.files["image"]
    if image.filename == "":
        flash("No selected file", "warning")
        return redirect(url_for("mess.profile"))

    upload_result = cloudinary.uploader.upload(image)
    image_url = upload_result.get("secure_url")

    mess_collection.update_one(
        {"_id": ObjectId(mess_id)},
        {"$push": {"images": image_url}}
    )

    flash("Image uploaded successfully!", "success")
    return redirect(url_for("mess.profile"))

# ===========================
# Delete Image
# ===========================
@mess.route("/delete_image/<mess_id>", methods=["POST"])
def delete_mess_image(mess_id):
    image_url = request.form.get("image_url")

    if not image_url:
        flash("Image not found!", "danger")
        return redirect(url_for("mess.profile", mess_id=mess_id))

    try:
        public_id = image_url.split("/")[-1].split(".")[0]
        cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print("Cloudinary deletion error:", e)

    mess_collection.update_one(
        {"_id": ObjectId(mess_id)},
        {"$pull": {"images": image_url}}
    )

    flash("Image deleted successfully!", "success")
    return redirect(url_for("mess.profile", mess_id=mess_id))



@mess.route("/apply/<mess_id>", methods=["POST"])
def apply_mess(mess_id):

    if "user_id" not in session or session.get("role") != "student":
        flash("Please login as a student first.", "warning")
        return redirect(url_for("login", role="student"))

    student_id = str(session["user_id"])
    student = session.get("user")

    mess_data = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not mess_data:
        flash("Mess not found!", "danger")
        return redirect(url_for("student_page"))

    # Prevent duplicate apply
    for req in mess_data.get("requests", []):
        if req["student_id"] == student_id and req["status"] == "pending":
            flash("You already applied for this mess!", "info")
            return redirect(url_for("student.mess_details", mess_id=mess_id))

    # Prevent if already hosted
    for h in mess_data.get("hosted_students", []):
        if h["student_id"] == student_id:
            flash("You are already hosted here!", "info")
            return redirect(url_for("student.mess_details", mess_id=mess_id))

    # Create request entry
    request_entry = {
        "_id": ObjectId(),
        "student_id": student_id,
        "student_name": student.get("name", "Unknown"),
        "student_mobile": student.get("mobile", "Unknown"),
        "status": "pending"
    }

    mess_collection.update_one(
        {"_id": ObjectId(mess_id)},
        {"$push": {"requests": request_entry}}
    )

    user = session["user"]
    if user.get("verification_status") != "verified":
        flash("Please verify your documents before applying.", "danger")
        return redirect(url_for("student.profile"))


    flash("Mess application sent successfully!", "success")
    return redirect(url_for("student.mess_details", mess_id=mess_id))



# @mess.route("/requests")
# def view_requests():
#     if "user_id" not in session or session.get("role") != "mess_owner":
#         flash("Login as Mess Owner first!", "warning")
#         return redirect(url_for("login", role="mess_owner"))

#     owner_id = str(session["user_id"])
#     mess_data = mess_collection.find_one({"owner_id": owner_id})

#     if not mess_data:
#         flash("No mess found.", "warning")
#         return redirect(url_for("mess.profile"))

#     requests_list = mess_data.get("requests", [])

#     return render_template("mess_requests.html", mess=mess_data, requests=requests_list)


@mess.route("/requests")
def view_requests():
    if "user_id" not in session or session.get("role") != "mess_owner":
        flash("Login as Mess Owner first!", "warning")
        return redirect(url_for("login", role="mess_owner"))

    owner_id = str(session["user_id"])
    mess_data = mess_collection.find_one({"owner_id": owner_id})

    if not mess_data:
        flash("No mess found.", "warning")
        return redirect(url_for("mess.profile"))

    requests_list = mess_data.get("requests", [])
    enriched_requests = []

    for req in requests_list:
        student = students.find_one({"_id": ObjectId(req["student_id"])})
        student_info = student.get("student_info", {}) if student else {}

        enriched_requests.append({
            "_id": req["_id"],
            "status": req.get("status", "pending"),
            "student_info": {
                "name": student_info.get("name", "Unknown"),
                "mobile": student_info.get("mobile", "Unknown"),
                "address": student_info.get("address", "Unknown"),
                "college": student_info.get("college", "Unknown"),
                "aadhaar_file": student_info.get("aadhaar_file", "#"),
                "college_id_file": student_info.get("college_id_file", "#"),
            }
        })

    return render_template("mess_requests.html", mess=mess_data, requests=enriched_requests)




@mess.route("/requests/accept/<mess_id>/<request_id>", methods=["POST"])
def accept_mess_request(mess_id, request_id):

    mess_obj = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not mess_obj:
        flash("Mess not found!", "danger")
        return redirect(url_for("mess.view_requests"))

    # Find request
    req = next((r for r in mess_obj.get("requests", []) if str(r["_id"]) == request_id), None)
    if not req:
        flash("Request not found!", "danger")
        return redirect(url_for("mess.view_requests"))

    student_id = req["student_id"]

    # --- 🚫 PREVENT DUPLICATE HOSTED STUDENTS ---
    already_hosted = any(h["student_id"] == student_id for h in mess_obj.get("hosted_students", []))
    if not already_hosted:
        mess_collection.update_one(
            {"_id": ObjectId(mess_id)},
            {"$push": {
                "hosted_students": {
                    "student_id": student_id,
                    "name": req["student_name"],
                    "mobile": req["student_mobile"]
                }
            }}
        )

    # --- ❌ Remove request once accepted ---
    mess_collection.update_one(
        {"_id": ObjectId(mess_id)},
        {"$pull": {"requests": {"_id": ObjectId(request_id)}}}
    )

    flash("Request accepted!", "success")
    return redirect(url_for("mess.view_requests"))



@mess.route("/requests/reject/<mess_id>/<request_id>", methods=["POST"])
def reject_mess_request(mess_id, request_id):
    mess_collection.update_one(
        {"_id": ObjectId(mess_id)},
        {"$pull": {"requests": {"_id": ObjectId(request_id)}}}
    )

    flash("Request rejected!", "info")
    return redirect(url_for("mess.view_requests"))

# @mess.route("/hosted")
# def hosted_students():
#     if "user_id" not in session or session.get("role") != "mess_owner":
#         flash("Please login as Mess Owner", "warning")
#         return redirect(url_for("login", role="mess_owner"))

#     owner_id = str(session.get("user_id"))
#     mess_obj = mess_collection.find_one({"owner_id": owner_id})

#     if not mess_obj:
#         flash("No mess found!", "warning")
#         return redirect(url_for("mess.profile"))

#     hosted = mess_obj.get("hosted_students", [])

#     # IMPORTANT: we are passing mess=mess_obj
#     return render_template("mess_hosted.html", mess=mess_obj, hosted=hosted)


@mess.route("/hosted")
def hosted_students():
    if "user_id" not in session or session.get("role") != "mess_owner":
        flash("Please login as Mess Owner", "warning")
        return redirect(url_for("login", role="mess_owner"))

    owner_id = str(session.get("user_id"))
    mess_obj = mess_collection.find_one({"owner_id": owner_id})

    if not mess_obj:
        flash("No mess found!", "warning")
        return redirect(url_for("mess.profile"))

    hosted = mess_obj.get("hosted_students", [])
    hosted_full = []

    for h in hosted:
        student_doc = students.find_one({"_id": ObjectId(h["student_id"])})
        sinfo = student_doc.get("student_info", {}) if student_doc else {}

        hosted_full.append({
            "student_info": {
                "name": sinfo.get("name", "Unknown"),
                "mobile": sinfo.get("mobile", "Unknown"),
                "address": sinfo.get("address", "Unknown"),
                "college": sinfo.get("college", "Unknown"),
                "aadhaar_file": sinfo.get("aadhaar_file", "#"),
                "college_id_file": sinfo.get("college_id_file", "#"),
            }
        })

    return render_template("mess_hosted.html", mess=mess_obj, hosted=hosted_full)



@mess.route("/<mess_id>")
def details(mess_id):
    m = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not m:
        flash("Mess not found!", "danger")
        return redirect(url_for("student.dashboard"))
    return render_template("mess_details.html", mess=m)



@mess.route("/review/<mess_id>", methods=["POST"])
def add_review(mess_id):

    if "user_id" not in session or session.get("role") != "student":
        flash("Please log in as a student to review.", "warning")
        return redirect(url_for("login", role="student"))

    student_id = str(session["user_id"])
    student_name = session["user"].get("name", "Anonymous")

    rating = int(request.form.get("rating", 0))
    comment = request.form.get("comment", "").strip()

    if rating < 1 or rating > 5 or not comment:
        flash("Please provide a valid rating and comment.", "danger")
        return redirect(url_for("mess_details", mess_id=mess_id))

    mess_obj = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not mess_obj:
        flash("Mess not found.", "danger")
        return redirect(url_for("student_page"))

    # Check if student is hosted
    hosted_list = mess_obj.get("hosted_students", [])
    is_hosted = any(h["student_id"] == student_id for h in hosted_list)

    if not is_hosted:
        flash("Only hosted students can review this mess.", "warning")
        return redirect(url_for("mess.details", mess_id=mess_id))

    # Prevent duplicate
    for r in mess_obj.get("reviews", []):
        if r.get("student_id") == student_id:
            flash("You have already reviewed this mess.", "info")
            return redirect(url_for("mess.details", mess_id=mess_id))

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

    mess_collection.update_one(
        {"_id": ObjectId(mess_id)},
        {"$push": {"reviews": review}}
    )

    flash("Review added successfully!", "success")
    return redirect(url_for("mess.details", mess_id=mess_id))





@mess.route("/sentiment/<mess_id>")
def mess_sentiment(mess_id):

    if "user_id" not in session or session.get("role") != "mess_owner":
        flash("Please login as Mess Owner first", "warning")
        return redirect(url_for("login", role="mess_owner"))

    mess_data = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not mess_data:
        flash("Mess not found", "danger")
        return redirect(url_for("mess.profile"))

    reviews = mess_data.get("reviews", [])

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

    return render_template(
        "mess_sentiment.html",
        mess=mess_data,
        total=total_reviews,
        positive=positive,
        negative=negative,
        neutral=neutral,
        avg_rating=avg_rating
    )


@mess.route("/sentiment_chart/<mess_id>")
def mess_sentiment_chart(mess_id):
    mess = mess_collection.find_one({"_id": ObjectId(mess_id)})
    if not mess:
        return "Mess not found", 404

    reviews = mess.get("reviews", [])
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

from pymongo import MongoClient

client = MongoClient("mongodb+srv://Roomify:Iwp9NrwIej23KCdw@cluster0.91rfyx0.mongodb.net/")
db = client["roomify_db"]

students = db["students"]
room_owners = db["room_owners"]
mess_owners = db["mess_owners"]

# Room & Mess databases
room_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
room_db = room_client["room_db"]
rooms_collection = room_db["rooms"]

mess_client = MongoClient("mongodb+srv://room:zmB5wOhMootISriJ@cluster0.avgqtty.mongodb.net/")
mess_db = mess_client["mess_db"]
mess_collection = mess_db["messes"]



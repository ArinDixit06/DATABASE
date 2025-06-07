# config.py
from pymongo import MongoClient

MONGO_URI = "mongodb+srv://shlok:xa0wqvAwSzrjSox9@developmentcluster.6slxuhw.mongodb.net/"
DATABASE_NAME = "cgf"

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

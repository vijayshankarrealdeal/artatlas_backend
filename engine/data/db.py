from pymongo import MongoClient
from pymongo.database import Database
from pymongo import TEXT



def get_db() -> Database:
    client = MongoClient("mongodb://localhost:27017/")
    db = client["artatlas"]
    return db
from pymongo import MongoClient
from datetime import datetime
from typing import AsyncGenerator
from pymongo.database import Database
import pandas as pd

def test_get_db():
    client = MongoClient("mongodb://localhost:27017/")
    db = client["artatlas"]
    return db
from fastapi import requests
from pymongo.database import Database
from pymongo import TEXT 
from PIL import Image
from io import BytesIO

def parse_result(cursor):
    results = []
    if isinstance(cursor, list) and len(cursor) > 0:
        for doc in cursor:
            doc["db_id"] = str(doc["_id"])
            del doc["_id"]
            results.append(doc)
        return results
    cursor['db_id'] = str(cursor['_id'])
    del cursor['_id']
    return cursor


def ensure_text_index(db: Database):
    """Ensures the text index exists on the 'artworks' collection."""
    try:
        db["artworks"].create_index(
            [("artwork_title", TEXT), ("artist_name", TEXT), ("category", TEXT)],
            name="ArtworkTextIndex",
            default_language="english",
            weights={"artwork_title": 10, "artist_name": 5, "category": 2},
        )
        print("Text index on 'artworks' collection ensured.")
    except Exception as e:
        print(f"Error creating text index: {e}")



def download_image(url):
    """Download an image synchronously from URL"""
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    return img
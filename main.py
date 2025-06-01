from typing import List
from bson import ObjectId
from fastapi import Depends, FastAPI, Query
from pymongo.database import Database
from engine.data.db import get_db
from pymongo import TEXT
from fastapi.middleware.cors import CORSMiddleware
from engine.llm.g_llm import llm_generate_artwork_metadata
from engine.models.artworks_model import LLMInputPayload
from engine.models.artworks_model import ArtworkData
from engine.utils import parse_result


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:59329/"],  # or ["http://127.0.0.1:8000"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def ensure_text_index(db):
    # This will create the index if it does not yet exist.
    # If it already exists, this is a no-op (i.e. it won’t recreate it).
    db["artworks"].create_index(
        [("artwork_title", TEXT), ("artist_name", TEXT), ("category", TEXT)],
        name="ArtworkTextIndex",
        default_language="english",
        weights={"artwork_title": 10, "artist_name": 5, "category": 2},
    )


@app.on_event("startup")
async def on_startup():
    db = get_db()
    ensure_text_index(db)


@app.get("/picture_of_the_day")
def get_picture_of_the_day(db: Database = Depends(get_db)) -> ArtworkData:
    artwork_of_the_day = db["artworks"].find_one()
    details_in_image = artwork_of_the_day.get("details_in_image", None)
    if not details_in_image:
        payload = LLMInputPayload(payload=artwork_of_the_day)
        res = llm_generate_artwork_metadata(payload)
        db["artworks"].update_one(
            {"_id": res.id},
            {"$set": res.model_dump()},
        )
        return res
    return ArtworkData(**artwork_of_the_day)


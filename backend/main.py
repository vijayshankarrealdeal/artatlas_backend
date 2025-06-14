# hack_back/main.py
from typing import List, Optional
from bson import ObjectId
from fastapi import Depends, FastAPI, Query, HTTPException
from pymongo.database import Database
from pymongo import TEXT # For text index
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
import httpx
from fastapi.responses import StreamingResponse

# Project specific imports
from engine.data.db import get_db, connect_to_mongo, close_mongo_connection
from engine.llm.g_llm import llm_generate_artwork_metadata
from engine.models.artworks_model import LLMInputPayload, ArtworkData
from engine.models.gallery_model import GalleryData # New model for galleries

app = FastAPI(title="ArtAtlas API", version="1.0.0")

# CORS Middleware Configuration
# For development, ["*"] is often used. For production, specify allowed origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Simplified for now, adjust for production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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
        # Depending on policy, you might want to raise this error
        # if the index is critical for application functionality.

@app.on_event("startup")
async def on_startup():
    """Application startup event: connect to DB and ensure indexes."""
    print("Application starting up...")
    try:
        connect_to_mongo()
        db = get_db()
        ensure_text_index(db)
    except Exception as e:
        print(f"Critical error during startup: {e}")
        # Optionally, exit or prevent app from fully starting if DB connection is essential
        raise

@app.on_event("shutdown")
async def on_shutdown():
    """Application shutdown event: close DB connection."""
    print("Application shutting down...")
    close_mongo_connection()



# /workspaces/hack_back/main.py

# ... (other imports and code) ...

@app.get("/get_picture_details", response_model=ArtworkData, summary="Get Picture Details by ID or Random") # Updated summary
async def get_picture_of_the_day( # Function name kept for consistency with your snippet
    id: Optional[str] = Query(None, description="Optional ID of the artwork to fetch. If not provided, a random artwork is fetched."), # Make id a Query param
    db: Database = Depends(get_db)
) -> ArtworkData:
    """
    Retrieves a specific artwork by ID or a random one if no ID is provided.
    If details are missing for the fetched artwork, they are generated using an LLM.
    """
    artwork_doc: Optional[dict] = None # Use type hint for clarity

    if id:
        if not ObjectId.is_valid(id):
            raise HTTPException(status_code=400, detail="Invalid artwork ID format.")
        artwork_doc = db["artworks"].find_one({"_id": ObjectId(id)})
    else:
        # Fetch a random document if no ID is provided (as per original logic's fallback)
        # Using $sample for randomness is better than find_one() which just gets the "first"
        pipeline = [{"$sample": {"size": 1}}]
        random_artworks = list(db["artworks"].aggregate(pipeline))
        if random_artworks:
            artwork_doc = random_artworks[0]
        
    if not artwork_doc:
        detail_msg = f"Artwork with ID '{id}' not found." if id else "No artworks found."
        raise HTTPException(status_code=404, detail=detail_msg)

    # Check if essential LLM-generated field 'details_in_image' is missing
    if not artwork_doc.get("details_in_image"):
        print(f"Details missing for artwork {artwork_doc['_id']}. Generating with LLM...")
        
        # Ensure payload passed to LLMInputPayload is a dictionary copy
        llm_input = LLMInputPayload(payload=dict(artwork_doc)) 
        
        try:
            res_artwork_data = llm_generate_artwork_metadata(llm_input)
            # print(f"LLM generated data for artwork {artwork_doc['_id']}: {res_artwork_data.model_dump_json(indent=2)}") # For debugging
        except RuntimeError as e:
            print(f"LLM generation failed for {artwork_doc['_id']}: {e}")
            return ArtworkData(**artwork_doc) # Return original if LLM fails
        except Exception as e: # Catch any other unexpected errors
            print(f"Unexpected error during LLM enrichment for {artwork_doc['_id']}: {e}")
            return ArtworkData(**artwork_doc)


        # --- Critical Change Here ---
        # Ensure we are using the Pydantic model's field name 'id' for exclusion
        # if `by_alias=False` or `_id` if `by_alias=True`
        update_payload = res_artwork_data.model_dump(
            exclude_none=True, 
            by_alias=False, # Use actual field names from the model for exclusion keys
            exclude={"id"}  # Exclude the 'id' field from the Pydantic model
        )
        
        # If you prefer to work with aliases in the update_payload (e.g. if your DB expects '_id')
        # And then remove '_id' from that aliased dict:
        # update_payload_aliased = res_artwork_data.model_dump(
        #     exclude_none=True,
        #     by_alias=True
        # )
        # if "_id" in update_payload_aliased:
        #    del update_payload_aliased["_id"]
        # update_payload = update_payload_aliased # Use this for the $set

        # The initial approach with by_alias=True and exclude={"_id"} should work too.
        # Let's stick to your original exclude={"_id"} with by_alias=True and ensure it's not a typo.
        # It's possible the ArtworkData model itself had an _id field at some point.

        # Safest bet: dump with by_alias=True, then explicitly delete '_id' if present.
        update_payload_for_db = res_artwork_data.model_dump(
            exclude_none=True, 
            by_alias=True # This will produce keys like '_id', 'artwork_title'
        )
        
        # Explicitly remove '_id' from the dictionary to be used in $set
        if "_id" in update_payload_for_db:
            del update_payload_for_db["_id"]
        
        if update_payload_for_db: # Only update if there are fields to set
            result = db["artworks"].update_one(
                {"_id": artwork_doc["_id"]}, # Query by the original ObjectId (artwork_doc['_id'] is already ObjectId)
                {"$set": update_payload_for_db}
            )
            if result.modified_count > 0:
                print(f"Artwork {artwork_doc['_id']} updated with LLM generated data.")
            else:
                print(f"Artwork {artwork_doc['_id']} - No update performed (data might be identical or write concern issue). Matched: {result.matched_count}")

        # The res_artwork_data already contains the 'id' field correctly populated (as string of ObjectId)
        # because the ArtworkData model handles the _id -> id conversion.
        return res_artwork_data 

    # If details were already present, return the document parsed as ArtworkData
    return ArtworkData(**artwork_doc)

# ... (rest of your main.py file) ...

@app.get("/search", response_model=List[ArtworkData], summary="Search Artworks")
async def search_artworks(
    q: str = Query(
        ..., min_length=1, description="Search query for artworks (keywords)"
    ),
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of results to return"),
    skip: int = Query(0, ge=0, description="Number of results to skip for pagination"),
) -> List[ArtworkData]:
    """
    Performs a full-text search on artworks based on keywords.
    Searches across 'artwork_title', 'artist_name', and 'category'.
    Results are sorted by relevance (text search score).
    """
    search_query = {"$text": {"$search": q}}
    projection = {"score": {"$meta": "textScore"}} # To sort by relevance

    cursor = (
        db["artworks"]
        .find(search_query, projection)
        .sort([("score", {"$meta": "textScore"})])
        .skip(skip)
        .limit(limit) # .limit() also returns a cursor, it doesn't execute the query yet
    )
    docs = list(cursor) # This synchronously fetches all matching documents up to 'limit'
    results = [ArtworkData(**doc) for doc in docs]
    
    return results

@app.get("/collections", response_model=List[ArtworkData], summary="Get Artworks (Collections View)")
async def get_collections( # Changed to async
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of artworks to return"),
    skip: int = Query(0, ge=0, description="Number of artworks to skip for pagination"),
) -> List[ArtworkData]:
    """
    Retrieves a paginated list of all artworks.
    Consider renaming if "collections" has a more specific meaning.
    """
    cursor = db["artworks"].find().skip(skip).limit(limit)
    docs = list(cursor) # Materialize cursor for sync pymongo in threadpool
    results = [ArtworkData(**doc) for doc in docs]
    return results


@app.get("/galleries", response_model=List[GalleryData], summary="Get Galleries")
async def get_galleries( # Changed to async and added response_model
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of galleries to return"),
    skip: int = Query(0, ge=0, description="Number of galleries to skip for pagination"),
) -> List[GalleryData]:
    """
    Retrieves a paginated list of galleries.
    """
    cursor = db["galleries"].find().skip(skip).limit(limit)
    docs = list(cursor) # Materialize for sync pymongo
    # GalleryData model handles _id to id conversion and validation
    results = [GalleryData(**doc) for doc in docs]
    return results


@app.get("/artworks_by_gallery", response_model=List[ArtworkData], summary="Get Artworks by Gallery ID")
async def get_artworks_by_gallery_id( # Changed to async, renamed for clarity
    gallery_id: str = Query(..., description="The ID of the gallery"),
    db: Database = Depends(get_db),
    limit: int = Query(15, gt=0, le=100, description="Number of artworks to return"),
    skip: int = Query(0, ge=0, description="Number of artworks to skip for pagination"),
) -> List[ArtworkData]:
    """
    Retrieves artworks linked to a specific gallery.
    The link is established via a shared 'artworks_id' field present in both
    the gallery document and the associated artwork documents.
    """
    if not ObjectId.is_valid(gallery_id):
        raise HTTPException(status_code=400, detail="Invalid gallery ID format. Must be a 24-character hex string.")

    gallery_object_id = ObjectId(gallery_id)
    gallery = db["galleries"].find_one({"_id": gallery_object_id})

    if not gallery:
        raise HTTPException(status_code=404, detail=f"Gallery with ID '{gallery_id}' not found.")

    # The gallery document is expected to have an 'artworks_id' field
    # which is a common identifier for a group/collection of artworks.
    shared_artworks_id = gallery.get("artworks_id")
    if not shared_artworks_id:
        raise HTTPException(
            status_code=404, 
            detail=f"Gallery '{gallery.get('name', gallery_id)}' does not have an 'artworks_id' to link artworks."
        )

    # Fetch artworks that share this 'artworks_id'
    artwork_cursor = (
        db["artworks"]
        .find({"artworks_id": shared_artworks_id})
        .skip(skip)
        .limit(limit)
    )
    docs = list(artwork_cursor) # Materialize for sync pymongo
    results = [ArtworkData(**doc) for doc in docs]
    
    if not results:
        # This is not an error, but might be useful information.
        # You could return an empty list or a 200 with a message if preferred.
        print(f"No artworks found with artworks_id '{shared_artworks_id}' for gallery '{gallery_id}'.")
        
    return results


@app.get("/proxy-image", summary="Proxy External Image")
async def proxy_image(url: str = Query(..., description="URL of the external image to proxy")):
    """
    Proxies an external image URL. Useful for bypassing CORS issues in web clients.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Must be HTTP or HTTPS.")

    # Use a new AsyncClient for each request or a shared one managed by lifespan events for high load
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0, follow_redirects=True)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request to external image source timed out.")
        except httpx.RequestError as e: # Catches connection errors, DNS failures, etc.
            raise HTTPException(status_code=502, detail=f"Failed to retrieve image from external source: {e}")
        except httpx.HTTPStatusError as e: # Handles 4xx/5xx from the remote server
             raise HTTPException(status_code=e.response.status_code, detail=f"External image source returned error: {e.response.status_code}")


        content_type = response.headers.get("content-type")
        if not content_type or not content_type.startswith("image/"):
            await response.aclose() # Ensure the response is closed
            raise HTTPException(status_code=415, detail="Proxied content is not a supported image type.")

        # StreamingResponse will handle closing the httpx response stream via BackgroundTask
        return StreamingResponse(
            response.aiter_bytes(), # Stream the content
            media_type=content_type,
            background=BackgroundTask(response.aclose) # Ensure client resources are released
        )

# Remove the unused import if engine.utils.parse_result is indeed no longer needed
# from engine.utils import parse_result 

@app.get("/", summary="Health Check")
async def health_check():
    """
    Simple health check endpoint to verify the API is running.
    """
    return {"status": "ok", "message": "ArtAtlas API is running. deplpyed to vm...."}
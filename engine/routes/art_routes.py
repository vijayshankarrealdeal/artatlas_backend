from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from typing import Annotated, List, Optional
from bson import ObjectId
from pydantic import TypeAdapter
from pymongo.database import Database
from engine.art_managers.services import ArtManagerService
from engine.data.db import get_db
from engine.llm.audio_generate import text_to_wav
from engine.llm.g_llm import llm_generate_artwork_metadata, llm_generate_audio_to_text
from engine.models.artworks_model import ArtworkData
from engine.models.gallery_model import GalleryData
from engine.models.artworks_model import LLMInputPayload, ArtworkData


art_router = APIRouter(tags=["art"])


@art_router.get("/search", response_model=List[ArtworkData], summary="Search Artworks")
async def search(
    q: str = Query(
        ..., min_length=1, description="Search query for artworks (keywords)"
    ),
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of results to return"),
    skip: int = Query(0, ge=0, description="Number of results to skip for pagination"),
):
    return await ArtManagerService.search_artworks(q=q, db=db, limit=limit, skip=skip)


@art_router.get(
    "/collections",
    response_model=List[ArtworkData],
    summary="Get Artworks (Collections View)",
)
async def get_artworks_collections(
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of artworks to return"),
    skip: int = Query(0, ge=0, description="Number of artworks to skip for pagination"),
):
    return await ArtManagerService.get_collections(db=db, limit=limit, skip=skip)


@art_router.get("/galleries", response_model=List[GalleryData], summary="Get Galleries")
async def galleries(
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of galleries to return"),
    skip: int = Query(
        0, ge=0, description="Number of galleries to skip for pagination"
    ),
):
    return await ArtManagerService.get_galleries(db=db, limit=limit, skip=skip)


@art_router.get(
    "/get_picture_details",
    response_model=ArtworkData,
    summary="Get Picture Details by ID or Random",
)  # Updated summary
async def get_picture_of_the_day(  # Function name kept for consistency with your snippet
    id: Optional[str] = Query(
        None,
        description="Optional ID of the artwork to fetch. If not provided, a random artwork is fetched.",
    ),  # Make id a Query param
    db: Database = Depends(get_db),
) -> ArtworkData:
    """
    Retrieves a specific artwork by ID or a random one if no ID is provided.
    If details are missing for the fetched artwork, they are generated using an LLM.
    """
    artwork_doc: Optional[dict] = None  # Use type hint for clarity

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
        detail_msg = (
            f"Artwork with ID '{id}' not found." if id else "No artworks found."
        )
        raise HTTPException(status_code=404, detail=detail_msg)

    # Check if essential LLM-generated field 'details_in_image' is missing
    if not artwork_doc.get("details_in_image"):
        print(
            f"Details missing for artwork {artwork_doc['_id']}. Generating with LLM..."
        )

        # Ensure payload passed to LLMInputPayload is a dictionary copy
        llm_input = LLMInputPayload(payload=dict(artwork_doc))

        try:
            res_artwork_data = llm_generate_artwork_metadata(llm_input)
            # print(f"LLM generated data for artwork {artwork_doc['_id']}: {res_artwork_data.model_dump_json(indent=2)}") # For debugging
        except RuntimeError as e:
            print(f"LLM generation failed for {artwork_doc['_id']}: {e}")
            return ArtworkData(**artwork_doc)  # Return original if LLM fails
        except Exception as e:  # Catch any other unexpected errors
            print(
                f"Unexpected error during LLM enrichment for {artwork_doc['_id']}: {e}"
            )
            return ArtworkData(**artwork_doc)

        update_payload = res_artwork_data.model_dump(
            exclude_none=True,
            by_alias=False,  # Use actual field names from the model for exclusion keys
            exclude={"id"},  # Exclude the 'id' field from the Pydantic model
        )
        update_payload_for_db = res_artwork_data.model_dump(
            exclude_none=True,
            by_alias=True,  # This will produce keys like '_id', 'artwork_title'
        )

        # Explicitly remove '_id' from the dictionary to be used in $set
        if "_id" in update_payload_for_db:
            del update_payload_for_db["_id"]

        if update_payload_for_db:  # Only update if there are fields to set
            result = db["artworks"].update_one(
                {
                    "_id": artwork_doc["_id"]
                },  # Query by the original ObjectId (artwork_doc['_id'] is already ObjectId)
                {"$set": update_payload_for_db},
            )
            if result.modified_count > 0:
                print(f"Artwork {artwork_doc['_id']} updated with LLM generated data.")
            else:
                print(
                    f"Artwork {artwork_doc['_id']} - No update performed (data might be identical or write concern issue). Matched: {result.matched_count}"
                )

        # The res_artwork_data already contains the 'id' field correctly populated (as string of ObjectId)
        # because the ArtworkData model handles the _id -> id conversion.
        return res_artwork_data

    # If details were already present, return the document parsed as ArtworkData
    return ArtworkData(**artwork_doc)


@art_router.get(
    "/artworks_by_gallery",
    response_model=List[ArtworkData],
    summary="Get Artworks by Gallery ID",
)
async def get_artworks_by_gallery_id(  # Changed to async, renamed for clarity
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
        raise HTTPException(
            status_code=400,
            detail="Invalid gallery ID format. Must be a 24-character hex string.",
        )

    gallery_object_id = ObjectId(gallery_id)
    gallery = db["galleries"].find_one({"_id": gallery_object_id})

    if not gallery:
        raise HTTPException(
            status_code=404, detail=f"Gallery with ID '{gallery_id}' not found."
        )

    shared_artworks_id = gallery.get("artworks_id")
    if not shared_artworks_id:
        raise HTTPException(
            status_code=404,
            detail=f"Gallery '{gallery.get('name', gallery_id)}' does not have an 'artworks_id' to link artworks.",
        )

    # Fetch artworks that share this 'artworks_id'
    artwork_cursor = (
        db["artworks"].find({"artworks_id": shared_artworks_id}).skip(skip).limit(limit)
    )
    docs = list(artwork_cursor)  # Materialize for sync pymongo
    results = [ArtworkData(**doc) for doc in docs]

    if not results:
        print(
            f"No artworks found with artworks_id '{shared_artworks_id}' for gallery '{gallery_id}'."
        )

    return results


@art_router.post("/askai")
async def ask_ai(
    artwork_data: Annotated[str, Form(...)],
    audio_file: Annotated[UploadFile, File(...)],
):
    try:
        # 
        adapter = TypeAdapter(ArtworkData)
        artwork_data: ArtworkData = adapter.validate_json(artwork_data)
        audio_bytes = await audio_file.read()
        print(f"🔥 convert JSON string to Pydantic model manually, and Received file: {audio_file.filename} ({len(audio_bytes)} bytes)")
        print("🔥 Artwork data Prev:", artwork_data.model_dump_json(indent=2))

        artwork_data = await get_picture_of_the_day(artwork_data.model_dump()['id'])
        print("🔥 Artwork data After:", artwork_data.model_dump_json(indent=2))
        llm_text = llm_generate_audio_to_text(audio_bytes, artwork_data.model_dump())
        print(llm_text)
        response_bytes = text_to_wav(llm_text)
        return Response(content=response_bytes, media_type="application/octet-stream")
    except Exception as e:
        print(f"Error in ask_ai: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

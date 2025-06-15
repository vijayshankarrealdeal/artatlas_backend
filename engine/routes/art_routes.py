from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from typing import Annotated, List, Optional
from bson import ObjectId
from pydantic import TypeAdapter
from pymongo.database import Database
from engine.art_managers.art_services import ArtManagerService
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
async def get_picture_details(
    id: Optional[str] = Query(
        None, description="ID of the artwork to retrieve. If not provided, a random artwork is returned."
    ),
    db: Database = Depends(get_db),
):
    return await ArtManagerService.get_picture_of_the_day(id=id, db=db)


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
    db: Database = Depends(get_db)
):
    try:
        # 
        adapter = TypeAdapter(ArtworkData)
        artwork_data: ArtworkData = adapter.validate_json(artwork_data)
        audio_bytes = await audio_file.read()
        print(f"🔥 convert JSON string to Pydantic model manually, and Received file: {audio_file.filename} ({len(audio_bytes)} bytes)")
        print("🔥 Artwork data Prev:", artwork_data.model_dump_json(indent=2))

        artwork_data = await ArtManagerService.get_picture_of_the_day(artwork_data.model_dump()['id'], db=db)
        print("🔥 Artwork data After:", artwork_data.model_dump_json(indent=2))
        llm_text = llm_generate_audio_to_text(audio_bytes, artwork_data.model_dump())
        print(llm_text)
        response_bytes = text_to_wav(llm_text)
        return Response(content=response_bytes, media_type="application/octet-stream")
    except Exception as e:
        print(f"Error in ask_ai: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

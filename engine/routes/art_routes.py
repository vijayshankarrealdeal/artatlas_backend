from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
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
from engine.fb.firebase import oauth2_scheme

art_router = APIRouter(tags=["art"])


@art_router.get(
    "/search",
    response_model=List[ArtworkData],
    summary="Search Artworks",
    dependencies=[Depends(oauth2_scheme)],
)
async def search(
    request: Request,
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
    dependencies=[Depends(oauth2_scheme)],
)
async def get_artworks_collections(
    request: Request,
    db: Database = Depends(get_db),
    limit: int = Query(10, gt=0, le=100, description="Number of artworks to return"),
    skip: int = Query(0, ge=0, description="Number of artworks to skip for pagination"),
):
    return await ArtManagerService.get_collections(db=db, limit=limit, skip=skip)


@art_router.get(
    "/galleries",
    response_model=List[GalleryData],
    dependencies=[Depends(oauth2_scheme)],
    summary="Get Galleries",
)
async def galleries(
    request: Request,
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
    dependencies=[Depends(oauth2_scheme)],
)  # Updated summary
async def get_picture_details(
    request: Request,
    id: Optional[str] = Query(
        None,
        description="ID of the artwork to retrieve. If not provided, a random artwork is returned.",
    ),
    db: Database = Depends(get_db),
):
    return await ArtManagerService.get_picture_of_the_day(id=id, db=db)


@art_router.get(
    "/artworks_by_gallery",
    response_model=List[ArtworkData],
    summary="Get Artworks by Gallery ID",
    dependencies=[Depends(oauth2_scheme)],
)
async def get_artworks_by_gallery_id(
    request: Request,
    gallery_id: str = Query(..., description="The ID of the gallery"),
    db: Database = Depends(get_db),
    limit: int = Query(15, gt=0, le=100, description="Number of artworks to return"),
    skip: int = Query(0, ge=0, description="Number of artworks to skip for pagination"),
) -> List[ArtworkData]:
    return await ArtManagerService.get_artworks_by_gallery_id(
        gallery_id=gallery_id, db=db, limit=limit, skip=skip
    )


@art_router.post("/askai", dependencies=[Depends(oauth2_scheme)])
async def ask_ai(
    request: Request,
    artwork_data: Annotated[str, Form(...)],
    audio_file: Annotated[UploadFile, File(...)],
    db: Database = Depends(get_db),
):
    try:
        #
        adapter = TypeAdapter(ArtworkData)
        artwork_data: ArtworkData = adapter.validate_json(artwork_data)
        audio_bytes = await audio_file.read()
        artwork_data = await ArtManagerService.get_picture_of_the_day(
            artwork_data.model_dump()["id"], db=db
        )
        llm_text = llm_generate_audio_to_text(audio_bytes, artwork_data.model_dump())
        response_bytes = text_to_wav(llm_text)
        return Response(content=response_bytes, media_type="application/octet-stream")
    except Exception as e:
        print(f"Error in ask_ai: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

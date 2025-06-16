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
    status,
)
from typing import Annotated, List, Optional
from bson import ObjectId
from pydantic import TypeAdapter
from pymongo.database import Database
from engine.art_managers.art_services import ArtManagerService
from engine.art_managers.user_manager import UserManager
from engine.data.db import get_db
from engine.llm.audio_generate import text_to_wav
from engine.llm.llm_workers import llm_generate_audio_to_text, search_similar
from engine.models.artworks_model import ArtworkData, AudioQuery
from engine.models.gallery_model import GalleryData
from engine.models.artworks_model import ArtworkData
from engine.fb.firebase import oauth2_scheme
from pydantic import TypeAdapter
from datetime import datetime, date, timezone

from engine.models.user_model import ChatHistory, ChatMessage, ChatMessageRole, User


FREE_TIER_DAILY_LIMIT = 5


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
    uesr_uid = request.state.user["uid"]
    email = request.state.user["email"]
    return await ArtManagerService.get_picture_of_the_day(
        user_uid=uesr_uid, user_email=email, id=id, db=db
    )


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
    """
    Handles a user's audio query about a specific artwork, providing a stateful,
    context-aware conversation with rate limiting for free users.
    """
    user_id = request.state.user["uid"]
    email = request.state.user["email"]
    current_date = date.today()

    user = UserManager.check_user(db=db, user_id=user_id, email=email)
    if user.subscription_status != "active":
        if user.last_interaction_date and user.last_interaction_date < current_date:
            user.daily_interaction_count = 0
            db["users"].update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "daily_interaction_count": 0,
                        "last_interaction_date": current_date.isoformat(),
                    }
                },
            )

        if user.daily_interaction_count >= FREE_TIER_DAILY_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily interaction limit of {FREE_TIER_DAILY_LIMIT} reached. Please subscribe or try again tomorrow.",
            )

    adapter = TypeAdapter(ArtworkData)
    artwork: ArtworkData = adapter.validate_json(artwork_data)
    artwork_id = artwork.id

    artwork_details: ArtworkData = await ArtManagerService.get_picture_of_the_day(
        user_email=email,
        user_uid=user_id,
        artwork_id=artwork_id,
        db=db
    )
    audio_bytes = await audio_file.read()

    history_collection = db["chat_histories"]
    existing_history_doc = history_collection.find_one(
        {"user_id": user_id, "artwork_id": artwork_id}
    )

    previous_dialogue: List[ChatMessage] = []
    if existing_history_doc:
        chat_history = ChatHistory(**existing_history_doc)
        previous_dialogue = chat_history.messages

    llm_output: AudioQuery = llm_generate_audio_to_text(
        audio_bytes=audio_bytes,
        artwork_info=artwork_details.model_dump(),
        conversation_history=previous_dialogue,
    )

    user_message = ChatMessage(role=ChatMessageRole.USER, content=llm_output.audio_text)
    assistant_message = ChatMessage(
        role=ChatMessageRole.ASSISTANT, content=llm_output.response
    )

    history_collection.update_one(
        {"user_id": user_id, "artwork_id": artwork_id},
        {
            "$push": {
                "messages": {
                    "$each": [user_message.model_dump(), assistant_message.model_dump()]
                }
            },
            "$set": {"updated_at": datetime.now()},
            "$setOnInsert": {
                "created_at": datetime.now(),
                "user_id": user_id,
                "artwork_id": artwork_id,
            },
        },
        upsert=True,
    )

    if user.subscription_status != "active":
        user_collection.update_one(
            {"_id": user_id},
            {
                "$inc": {"daily_interaction_count": 1},
                "$set": {"last_interaction_date": current_date.isoformat()},
            },
        )

    # 8. --- Generate Final Audio Response ---
    response_bytes = text_to_wav(llm_output.response)
    return Response(content=response_bytes, media_type="application/octet-stream")


@art_router.get(
    "/get_similar_artworks",
    response_model=List[ArtworkData],
    dependencies=[Depends(oauth2_scheme)],
)
async def get_similar_artworks(
    request: Request,
    artwork_id: str = Query(
        ..., description="ID of the artwork to find similar artworks"
    ),
    db: Database = Depends(get_db),
    limit: int = Query(
        10, gt=0, le=100, description="Number of similar artworks to return"
    ),
):
    """
    Get artworks similar to the specified artwork ID.
    """
    try:
        if not ObjectId.is_valid(artwork_id):
            raise HTTPException(status_code=400, detail="Invalid artwork ID format")
        collections = db["art_embeddings"]
        similar_ids = search_similar(
            query=artwork_id, collection=collections, top_k=limit
        )
        return await ArtManagerService.fetch_artworks_by_ids(similar_ids, db=db)
    except Exception as e:
        print(f"Error in get_similar_artworks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

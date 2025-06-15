from fastapi import APIRouter
from backend.engine.routes.image_routes import image_router
from backend.engine.routes.art_routes import art_router



router = APIRouter()
router.include_router(art_router, prefix="/art", tags=["art"])
router.include_router(image_router, prefix="/image", tags=["image"])


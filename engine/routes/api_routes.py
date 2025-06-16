from fastapi import APIRouter
from engine.routes.image_routes import image_router
from engine.routes.art_routes import art_router
from engine.routes.user_route import user_route



router = APIRouter()
router.include_router(art_router, prefix="/art", tags=["art"])
router.include_router(image_router, prefix="/image", tags=["image"])
router.include_router(user_route, prefix="/user", tags=["user"])


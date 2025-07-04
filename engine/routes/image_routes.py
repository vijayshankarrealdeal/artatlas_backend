from fastapi import APIRouter, Query
from engine.managers.images import ProcessImages


image_router = APIRouter(tags=["image"])


@image_router.get("/proxy-image", summary="Proxy External Image")
async def refactor_proxy_image(url: str):
    """
    Proxies an external image URL. Useful for bypassing CORS issues in web clients.
    """

    return await ProcessImages.proxy_image(url=url)

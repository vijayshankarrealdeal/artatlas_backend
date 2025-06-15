from fastapi import APIRouter, Query
from engine.art_managers.images import ProcessImages


image_router = APIRouter(tags=["image"])


@image_router.get("/proxy-image", summary="Proxy External Image")
async def refactor_proxy_image(
    url: str = Query(..., description="URL of the external image to proxy")
):
    """
    Proxies an external image URL. Useful for bypassing CORS issues in web clients.
    """

    return await ProcessImages.proxy_image(url=url)
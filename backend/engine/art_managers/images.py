import httpx
from fastapi import HTTPException, Query
from starlette.background import BackgroundTask

from fastapi.responses import StreamingResponse

class ProcessImages:

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
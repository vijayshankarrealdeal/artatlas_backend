# hack_back/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.engine.utils import ensure_text_index
from backend.engine.routes.api_routes import router
from backend.engine.data.db import get_db, connect_to_mongo, close_mongo_connection


app = FastAPI(title="ArtAtlas API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(router)


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
        raise


@app.on_event("shutdown")
async def on_shutdown():
    """Application shutdown event: close DB connection."""
    print("Application shutting down...")
    close_mongo_connection()


@app.get("/", summary="Health Check")
async def health_check():
    """
    Simple health check endpoint to verify the API is running.
    """
    return {"status": "ok", "message": "ArtAtlas API is running. deplpyed to vm...."}

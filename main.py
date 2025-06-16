# hack_back/main.py
import firebase_admin, json, os, base64
from firebase_admin import credentials
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from engine.utils import ensure_text_index
from engine.routes.api_routes import router
from engine.data.db import get_db, connect_to_mongo, close_mongo_connection
from engine.fb.firebase import oauth2_scheme

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
        firebase_creds_base64 = os.getenv("FIREBASE_CREDENTIALS")
        if not firebase_creds_base64:
            raise ValueError("FIREBASE_CREDENTIALS environment variable not set.")
        decoded_creds_json = base64.b64decode(firebase_creds_base64).decode("utf-8")
        creds_dict = json.loads(decoded_creds_json)
        cred = credentials.Certificate(creds_dict) # Make sure the path is correct
        firebase_admin.initialize_app(cred)
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


@app.get("/", dependencies=[Depends(oauth2_scheme)], summary="Health Check")
async def health_check(
    request: Request,
):
    print(request.state.user['email'])
    """
    Simple health check endpoint to verify the API is running.
    """
    return {"status": "ok", "message": "ArtAtlas API is running. deplpyed to vm...."}

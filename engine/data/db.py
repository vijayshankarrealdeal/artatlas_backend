# engine/data/db.py
from pymongo import MongoClient
from pymongo.database import Database
from typing import Optional
import os # For environment variables for connection string

# Global variable for the MongoDB client and database instance
_mongo_client: Optional[MongoClient] = None
_db: Optional[Database] = None

def connect_to_mongo():
    """Initializes the MongoDB client and database instance."""
    global _mongo_client, _db
    if _mongo_client is None: # Ensure client is initialized only once
        mongo_uri = os.getenv("MONGO_URI", "mongodb://34.123.93.95:27017")
        print(f"Connecting to MongoDB at {mongo_uri}...")
        _mongo_client = MongoClient(mongo_uri)
        _db = _mongo_client["artatlas"] # Replace "artatlas" with your actual DB name if different
        try:
            # Ping the server to verify connection
            _mongo_client.admin.command('ping')
            print("Successfully connected to MongoDB and 'artatlas' database.")
        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}")
            _mongo_client = None # Reset client on failure
            _db = None
            raise # Reraise exception to halt startup if DB connection fails

def close_mongo_connection():
    """Closes the MongoDB client connection."""
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None # Clear the client
        _db = None # Clear the db instance
        print("MongoDB connection closed.")

def get_db() -> Database:
    """
    Returns the MongoDB database instance.
    Ensures that connect_to_mongo() has been called, typically during app startup.
    """
    if _db is None:
        # This path is problematic if connect_to_mongo wasn't called on startup.
        # It's better to rely on startup lifecycle.
        # For robustness during development or testing outside app context, you could call connect_to_mongo() here,
        # but it's less clean.
        raise RuntimeError("Database not initialized. Call connect_to_mongo() on application startup.")
    return _db
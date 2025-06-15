from typing import List
from pymongo.database import Database
from engine.models.artworks_model import ArtworkData
from engine.models.gallery_model import GalleryData


class ArtManagerService:

    async def search_artworks(q, db: Database, limit, skip) -> List[ArtworkData]:
        """
        Performs a full-text search on artworks based on keywords.
        Searches across 'artwork_title', 'artist_name', and 'category'.
        Results are sorted by relevance (text search score).
        """
        search_query = {"$text": {"$search": q}}
        projection = {"score": {"$meta": "textScore"}}  # To sort by relevance
        cursor = (
            db["artworks"]
            .find(search_query, projection)
            .sort([("score", {"$meta": "textScore"})])
            .skip(skip)
            .limit(
                limit
            )  # .limit() also returns a cursor, it doesn't execute the query yet
        )
        docs = list(
            cursor
        )  # This synchronously fetches all matching documents up to 'limit'
        results = [ArtworkData(**doc) for doc in docs]

        return results

    async def get_collections(db: Database, limit: int, skip: int) -> List[ArtworkData]:
        """
        Retrieves a paginated list of all artworks.
        Consider renaming if "collections" has a more specific meaning.
        """
        cursor = db["artworks"].find().skip(skip).limit(limit)
        docs = list(cursor)  # Materialize cursor for sync pymongo in threadpool
        results = [ArtworkData(**doc) for doc in docs]
        return results

    async def get_galleries(db: Database, limit: int, skip: int) -> List[GalleryData]:
        """
        Retrieves a paginated list of galleries.
        """
        cursor = db["galleries"].find().skip(skip).limit(limit)
        docs = list(cursor)  # Materialize for sync pymongo
        # GalleryData model handles _id to id conversion and validation
        results = [GalleryData(**doc) for doc in docs]
        return results

from typing import List, Optional
from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database
from engine.llm.g_llm import llm_generate_artwork_metadata
from engine.models.artworks_model import ArtworkData, LLMInputPayload
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

    async def get_picture_of_the_day(id: str, db: Database) -> ArtworkData:
        """
        Retrieves a specific artwork by ID or a random one if no ID is provided.
        If details are missing for the fetched artwork, they are generated using an LLM.
        """
        artwork_doc: Optional[dict] = None  # Use type hint for clarity

        if id:
            if not ObjectId.is_valid(id):
                raise HTTPException(
                    status_code=400, detail="Invalid artwork ID format."
                )
            artwork_doc = db["artworks"].find_one({"_id": ObjectId(id)})
        else:
            # Fetch a random document if no ID is provided (as per original logic's fallback)
            # Using $sample for randomness is better than find_one() which just gets the "first"
            pipeline = [{"$sample": {"size": 1}}]
            random_artworks = list(db["artworks"].aggregate(pipeline))
            if random_artworks:
                artwork_doc = random_artworks[0]

        if not artwork_doc:
            detail_msg = (
                f"Artwork with ID '{id}' not found." if id else "No artworks found."
            )
            raise HTTPException(status_code=404, detail=detail_msg)

        # Check if essential LLM-generated field 'details_in_image' is missing
        if not artwork_doc.get("details_in_image"):
            print(
                f"Details missing for artwork {artwork_doc['_id']}. Generating with LLM..."
            )

            # Ensure payload passed to LLMInputPayload is a dictionary copy
            llm_input = LLMInputPayload(payload=dict(artwork_doc))

            try:
                res_artwork_data = llm_generate_artwork_metadata(llm_input)
                # print(f"LLM generated data for artwork {artwork_doc['_id']}: {res_artwork_data.model_dump_json(indent=2)}") # For debugging
            except RuntimeError as e:
                print(f"LLM generation failed for {artwork_doc['_id']}: {e}")
                return ArtworkData(**artwork_doc)  # Return original if LLM fails
            except Exception as e:  # Catch any other unexpected errors
                print(
                    f"Unexpected error during LLM enrichment for {artwork_doc['_id']}: {e}"
                )
                return ArtworkData(**artwork_doc)
            res_artwork_data = res_artwork_data.model_dump()
            for k, v in artwork_doc.model_dump():
                res_artwork_data[k] = v
            res_artwork_data = ArtworkData(**res_artwork_data)
            update_payload_for_db = res_artwork_data.model_dump(
                exclude_none=True,
                by_alias=True,  # This will produce keys like '_id', 'artwork_title'
            )

            # Explicitly remove '_id' from the dictionary to be used in $set
            if "_id" in update_payload_for_db:
                del update_payload_for_db["_id"]

            if update_payload_for_db:  # Only update if there are fields to set
                result = db["artworks"].update_one(
                    {
                        "_id": artwork_doc["_id"]
                    },  # Query by the original ObjectId (artwork_doc['_id'] is already ObjectId)
                    {"$set": update_payload_for_db},
                )
                if result.modified_count > 0:
                    print(
                        f"Artwork {artwork_doc['_id']} updated with LLM generated data."
                    )
                else:
                    print(
                        f"Artwork {artwork_doc['_id']} - No update performed (data might be identical or write concern issue). Matched: {result.matched_count}"
                    )

            # The res_artwork_data already contains the 'id' field correctly populated (as string of ObjectId)
            # because the ArtworkData model handles the _id -> id conversion.
            return res_artwork_data

        # If details were already present, return the document parsed as ArtworkData
        return ArtworkData(**artwork_doc)

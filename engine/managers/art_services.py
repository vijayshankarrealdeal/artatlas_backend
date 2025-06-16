from datetime import date
from typing import List, Optional, Union
from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database
from engine.managers.user_manager import UserManager
from engine.llm.llm_workers import llm_generate_artwork_metadata
from engine.models.artworks_model import ArtworkData, LLMInputPayload
from engine.models.gallery_model import GalleryData
from engine.models.user_model import UserApp


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

    async def get_picture_of_the_day(
        user_uid, user_email, id: str, db: Database
    ) -> ArtworkData:
        """
        Retrieves a specific artwork by ID or a random one if no ID is provided.
        If details are missing for the fetched artwork, they are generated using an LLM.
        """
        RANDOM_ART_DAILY_LIMIT = 5
        artwork_doc: Optional[dict] = None  # Use type hint for clarity

        if id:
            if not ObjectId.is_valid(id):
                raise HTTPException(
                    status_code=400, detail="Invalid artwork ID format."
                )
            artwork_doc = db["artworks"].find_one({"_id": ObjectId(id)})
        else:
            user: UserApp = UserManager.check_user(db=db, user_id=user_uid, email=user_email)
            current_date = date.today()
            last_date_str = user.last_random_art_date
            last_date = date.fromisoformat(last_date_str) if last_date_str else None

            if not last_date or last_date < current_date:
                db["users"].update_one(
                    {"_id": user_uid},
                    {
                        "$set": {
                            "daily_random_art_count_img": 0,
                            "last_random_art_date": current_date.isoformat(),
                        }
                    },
                )
                user["daily_random_art_count_img"] = 0 
            if user.daily_random_art_count_img < RANDOM_ART_DAILY_LIMIT:
                print(
                    f"User {user_uid} has random picks left. Fetching from 'artworks'."
                )
                pipeline = [{"$sample": {"size": 1}}]
                random_artworks = list(db["artworks"].aggregate(pipeline))
                if not random_artworks:
                    raise HTTPException(
                        status_code=404, detail="No artworks available to choose from."
                    )

                artwork_doc = random_artworks[0]
                db["users"].update_one(
                    {"_id": user_uid}, {"$inc": {"daily_random_art_count_img": 1}}
                )
            else:
                print(
                    f"User {user_uid} limit reached. Fetching from 'daily_art_for_user'."
                )

                daily_art_cursor = (
                    db["daily_art_for_user"].find({}).sort("display_order", 1)
                )  # Optional sort
                daily_artworks = [ArtworkData(**doc) for doc in daily_art_cursor]

                if not daily_artworks:
                    raise HTTPException(
                        status_code=404,
                        detail="Daily artworks are not configured yet. Please check back later.",
                    )
                return daily_artworks[0]
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
            for k, v in artwork_doc.items():
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
            return res_artwork_data
        return ArtworkData(**artwork_doc)

    async def get_artworks_by_gallery_id(
        gallery_id: str,
        db: Database,
        limit: int = 15,
        skip: int = 0,
    ):
        """
        Retrieves artworks linked to a specific gallery.
        The link is established via a shared 'artworks_id' field present in both
        the gallery document and the associated artwork documents.
        """
        if not ObjectId.is_valid(gallery_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid gallery ID format. Must be a 24-character hex string.",
            )

        gallery_object_id = ObjectId(gallery_id)
        gallery = db["galleries"].find_one({"_id": gallery_object_id})

        if not gallery:
            raise HTTPException(
                status_code=404, detail=f"Gallery with ID '{gallery_id}' not found."
            )

        shared_artworks_id = gallery.get("artworks_id")
        if not shared_artworks_id:
            raise HTTPException(
                status_code=404,
                detail=f"Gallery '{gallery.get('name', gallery_id)}' does not have an 'artworks_id' to link artworks.",
            )

        # Fetch artworks that share this 'artworks_id'
        artwork_cursor = (
            db["artworks"]
            .find({"artworks_id": shared_artworks_id})
            .skip(skip)
            .limit(limit)
        )
        docs = list(artwork_cursor)  # Materialize for sync pymongo
        results = [ArtworkData(**doc) for doc in docs]

        if not results:
            print(
                f"No artworks found with artworks_id '{shared_artworks_id}' for gallery '{gallery_id}'."
            )

        return results

    async def fetch_artworks_by_ids(
        ids: Union[str, List[str]], db: Database
    ) -> List[ArtworkData]:
        if isinstance(ids, str):
            id_list = [ids]
        else:
            id_list = ids
        if not id_list:
            return []

        # 2. Convert string IDs to MongoDB ObjectId, raising an error on failure
        try:
            object_ids = [ObjectId(id_str) for id_str in id_list]
        except Exception as e:
            raise ValueError(f"One or more IDs are invalid: {e}")

        # 3. Build the efficient '$in' query
        query = {"_id": {"$in": object_ids}}
        cursor = db["artworks"].find(query)
        results = cursor.to_list(length=len(object_ids))
        results = [ArtworkData(**doc) for doc in results]
        return results

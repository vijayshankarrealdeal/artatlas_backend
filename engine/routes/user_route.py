
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo.collection import ReturnDocument
from datetime import datetime, timezone
from pymongo.database import Database
from engine.data.db import get_db
from engine.models.user_model import SubscriptionStatus, UserSubscriptionPayload
from engine.fb.firebase import oauth2_scheme

user_route = APIRouter(tags=["user"])


@user_route.post(
    "/subscription",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(oauth2_scheme)] # SECURE THE ENDPOINT
)
async def update_own_subscription(
    request: Request,
    payload: UserSubscriptionPayload,
    db: Database = Depends(get_db)
):
    user_id = request.state.user['uid']
    email_from_token = request.state.user['email']
    
    user_collection = db["users"]
    
    # 2. Define the fields to update
    update_fields = {
        "subscription_status": payload.new_status.value,
        "subscription_provider_id": payload.subscription_provider_id,
        "updated_at": datetime.now(timezone.utc)
    }
    update_fields = {k: v for k, v in update_fields.items() if v is not None}

    # 3. Perform the atomic "find and upsert" operation using the user's ID
    updated_user = user_collection.find_one_and_update(
        # The filter now uses the immutable user ID
        {"_id": user_id},
        {
            # These fields are applied on both update and insert
            "$set": update_fields,
            # These fields are applied ONLY when a new user is created
            "$setOnInsert": { 
                "_id": user_id, # Set the ID from the token
                "email": email_from_token, # Set the email from the token
                "created_at": datetime.now(timezone.utc),
                "subscription_status": SubscriptionStatus.FREE_TIER.value # Default status
            }
        },
        upsert=True,  # This creates the document if `_id` is not found
        return_document=ReturnDocument.AFTER
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update or create user subscription."
        )

    return {
        "status": "success",
        "message": f"User {updated_user['email']} subscription status updated to {updated_user['subscription_status']}.",
        "user_id": updated_user["_id"]
    }
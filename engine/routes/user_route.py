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
    dependencies=[Depends(oauth2_scheme)],  # SECURE THE ENDPOINT
)
async def update_own_subscription(
    request: Request, payload: UserSubscriptionPayload, db: Database = Depends(get_db)
):
    user_id = request.state.user["uid"]
    email_from_token = request.state.user["email"]

    user_collection = db["users"]

    # 2. Define the fields to update
    update_fields = {
        "subscription_provider_id": payload.subscription_provider_id,
        "updated_at": datetime.now(timezone.utc),
    }
    if payload.new_status is not None:
        update_fields["subscription_status"] = payload.new_status.value

    updated_user = user_collection.find_one_and_update(
        {"_id": user_id},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "_id": user_id,
                "email": email_from_token,
                "created_at": datetime.now(timezone.utc),
                # only set a default if the client didn't send any status
                **(
                    {}
                    if payload.new_status is not None
                    else {"subscription_status": SubscriptionStatus.FREE_TIER.value}
                ),
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update or create user subscription.",
        )

    return {
        "status": "success",
        "message": f"User {updated_user['email']} subscription status updated to {updated_user['subscription_status']}.",
        "user_id": updated_user["_id"],
    }

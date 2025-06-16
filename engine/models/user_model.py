from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field, field_validator



class ChatMessageRole(str, Enum):
    """Enum to distinguish between the user's message and the AI's response."""
    USER = "user"
    ASSISTANT = "assistant"

class ChatMessage(BaseModel):
    """Represents a single message turn in a conversation."""
    role: ChatMessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

class ChatHistory(BaseModel):
    """Represents the entire chat history for one user with one specific artwork."""
    user_id: str
    artwork_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class SubscriptionStatus(str, Enum):
    """Enum for defined user subscription statuses."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FREE_TIER = "free_tier"

from bson import ObjectId
from pydantic import field_validator

class UserApp(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    email: EmailStr
    subscription_status: SubscriptionStatus = SubscriptionStatus.FREE_TIER
    daily_interaction_count: int = 0
    daily_random_art_count_img: int = Field(
        default=0,
        description="Count of random artworks viewed today.",
    )
    last_interaction_date: Optional[date] = None
    last_random_art_date: Optional[date] = None
    daily_random_art_ids: List[str] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    @field_validator("daily_random_art_ids", mode="before")
    @classmethod
    def convert_daily_ids(cls, v):
        # v might be None, a list of ObjectId, or a list of str
        if isinstance(v, list):
            return [str(item) if isinstance(item, ObjectId) else item for item in v]
        return v

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = { ObjectId: str }


class UserSubscriptionPayload(BaseModel):
    """
    Payload for a logged-in user to update their own subscription status.
    """
    new_status: SubscriptionStatus = Field(..., description="The new subscription status to set.")
    subscription_provider_id: Optional[str] = Field(
        default=None, 
        description="Optional: The subscription ID from the payment provider (e.g., Stripe's 'sub_...')."
    )
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


class UserApp(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    email: EmailStr = Field(..., description="User's email address.")
    subscription_status: SubscriptionStatus = Field(default=SubscriptionStatus.FREE_TIER)
    daily_interaction_count: int = Field(default=0)
    daily_random_art_count_img: int = Field(default=0, description="Count of random artworks viewed today.")
    last_interaction_date: Optional[date] = Field(default=None)
    last_random_art_date: Optional[date] = Field(default=None, description="Date of the last random artwork viewed.")
    daily_random_art_ids: List[str] = Field(default_factory=list)
    
    @field_validator("id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, value):
        if isinstance(value, ObjectId):
            return str(value)
        return value

    class Config:
        populate_by_name = True  # Allows using alias "_id" for field "id" during initialization
        arbitrary_types_allowed = True # Good to keep if you might use other custom types directly
        json_encoders = {
            ObjectId: str  # Correctly serialize any ObjectId instances to str
                           # This is useful if other fields were to remain ObjectId type.
                           # For 'id', it's already str after the validator.
        }

class UserSubscriptionPayload(BaseModel):
    """
    Payload for a logged-in user to update their own subscription status.
    """
    new_status: SubscriptionStatus = Field(..., description="The new subscription status to set.")
    subscription_provider_id: Optional[str] = Field(
        default=None, 
        description="Optional: The subscription ID from the payment provider (e.g., Stripe's 'sub_...')."
    )
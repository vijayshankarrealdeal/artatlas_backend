from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from bson import ObjectId
from pydantic import BaseModel, Field, field_validator



class ChatMessageRole(str, Enum):
    """Enum to distinguish between the user's message and the AI's response."""
    USER = "user"
    ASSISTANT = "assistant"

class ChatMessage(BaseModel):
    """Represents a single message turn in a conversation."""
    role: ChatMessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatHistory(BaseModel):
    """Represents the entire chat history for one user with one specific artwork."""
    user_id: str
    artwork_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SubscriptionStatus(str, Enum):
    """Enum for defined user subscription statuses."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FREE_TIER = "free_tier"


class User(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    email: str = Field(..., description="User's email address.")
    subscription_status: SubscriptionStatus = Field(default=SubscriptionStatus.FREE_TIER)
    daily_interaction_count: int = Field(default=0)
    last_interaction_date: Optional[date] = Field(default=None)

    
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
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from bson import ObjectId  # Requires installation of 'bson', usually included with pymongo


class AudioQuery(BaseModel):
    response: str
    audio_text: str

class TourGuideSection(BaseModel):
    section: str
    text: str


class HistoricalContext(BaseModel):
    artist_history: str
    painting_history: str
    historical_significance: str


class ArtworkData(BaseModel):
    # Core metadata for the artwork
    artwork_title: Optional[str] = Field(None, alias="artwork_title")
    artist_name: Optional[str] = Field(None, alias="artist_name")
    year: Optional[str] = Field(None, alias="year")
    medium: Optional[str] = None
    dimensions: Optional[str] = None
    current_location: Optional[str] = None
    artwork_url: Optional[str] = None
    image_url: Optional[str] = None
    details_in_image: Optional[str] = Field(
        None,
        description="Describe the image’s contents by detailing what’s depicted—such as scenes, people, objects, and so on.",
    )
    description: Optional[str] = None
    interpretation: Optional[str] = None
    mood: Optional[str] = None
    keywords: Optional[List[str]] = None
    historical_context: Optional[HistoricalContext] = None
    artist_biography: Optional[str] = None
    tour_guide_explanation: Optional[List[TourGuideSection]] = None
    style: Optional[str] = None
    category: Optional[str] = None

    # Identifier fields
    # The 'id' field will store the string representation of MongoDB's ObjectId
    id: Optional[str] = Field(None, alias="_id")
    artworks_id: Optional[str] = None
    artist_url: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, value):
        if isinstance(value, ObjectId):
            return str(value)
        # If it's already a string (e.g., from JSON where it was pre-serialized)
        # or None, let it pass through. Pydantic will then validate if it's a
        # valid str or None against the type hint `Optional[str]`.
        return value

    class Config:
        populate_by_name = True  # Allows using alias "_id" for field "id" during initialization
        arbitrary_types_allowed = True # Good to keep if you might use other custom types directly
        json_encoders = {
            ObjectId: str  # Correctly serialize any ObjectId instances to str
                           # This is useful if other fields were to remain ObjectId type.
                           # For 'id', it's already str after the validator.
        }


class LLMInputPayload(BaseModel):
    # If payload is intended to be the dictionary representation of ArtworkData
    payload: dict

    # If payload is intended to be an ArtworkData instance, then:
    # payload: ArtworkData

    def generate_payload(self):
        # Assuming self.payload is a dictionary here based on current typing
        # If self.payload were ArtworkData, access would be self.payload.image_url etc.
        return {
            "image": self.payload.get("image_url"), # Use .get for safer access from dict
            "query": f"{self.payload.get('artwork_title', 'N/A')} by {self.payload.get('artist_name', 'N/A')}",
            "payload": self.payload,
        }

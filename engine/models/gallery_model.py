# engine/models/gallery_model.py
from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import Optional
from bson import ObjectId

class GalleryData(BaseModel):
    id: str = Field(alias="_id", description="The unique identifier of the gallery.")
    name: str = Field(..., description="Name of the gallery.")
    artworks_id: Optional[str] = Field(
        None, 
        description="Identifier linking this gallery to a specific collection/group of artworks (e.g., a UUID)."
    )
    collection_url: Optional[HttpUrl] = Field(None, description="URL to the collection page if available.") # Using HttpUrl for validation
    curator: Optional[str] = Field(None, description="Curator of the gallery.")
    title: Optional[str] = Field(None, description="Title of the gallery, can be same as name or more descriptive.")
    image_url: Optional[HttpUrl] = Field(None, description="URL of a representative image for the gallery.") # Using HttpUrl
    items_count_galleries_page: Optional[str] = Field(
        None, 
        description="String indicating the number of items in the gallery (e.g., '77 Items')."
    )
    description: Optional[str] = Field(None, description="A brief description of the gallery.") # Added as it was in the original template

    @field_validator("id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, value):
        if isinstance(value, ObjectId):
            return str(value)
        return value

    class Config:
        populate_by_name = True  # Allows using alias "_id" for field "id"
        arbitrary_types_allowed = True # Allow custom types like ObjectId if not fully converted by validators
        json_encoders = { 
            ObjectId: str # Ensure any remaining ObjectId fields are serialized to string
        }
        
        # Example for Pydantic v2 model_config
        # model_config = {
        #     "populate_by_name": True,
        #     "arbitrary_types_allowed": True,
        #     "json_encoders": {ObjectId: str}
        # }
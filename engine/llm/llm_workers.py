from typing import List
from google import genai
from PIL import Image
from google.genai import types
import requests
import io, os
import json
import numpy as np
from dotenv import load_dotenv
import torch
from transformers import CLIPModel, CLIPProcessor
from engine.models.artworks_model import (
    ArtworkData,
    AudioQuery,
    LLMInputPayload,
)  # Assuming these are defined elsewhere
from google.genai.types import HttpOptions
import logging

from engine.models.user_model import ChatMessage
from engine.utils import download_image


# Configure logging
# Basic configuration logs to console. You can customize it to log to a file, rotate logs, etc.
logging.basicConfig(
    level=logging.INFO,  # Set to logging.DEBUG for more verbose output
    format="%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    # handlers=[
    #     logging.FileHandler("app.log"), # Uncomment to log to a file
    #     logging.StreamHandler()
    # ]
)
logger = logging.getLogger(__name__)

load_dotenv()

ARCHIVE_DIR = "/app/engine/extras/archive"  # Default to a known model if not set
device = "cuda" if torch.cuda.is_available() else "cpu"
MODEL = CLIPModel.from_pretrained(
    ARCHIVE_DIR,
    local_files_only=True,
).to(device)
PROCESSOR = CLIPProcessor.from_pretrained(
    ARCHIVE_DIR,
    local_files_only=True,
)


def llm_generate_artwork_metadata(payload: LLMInputPayload) -> ArtworkData:
    logger.info("Starting llm_generate_artwork_metadata function.")
    logger.debug(f"Input payload object: {payload}")

    processed_payload = payload.generate_payload()
    logger.debug(f"Generated payload for LLM: {processed_payload}")

    image_url = processed_payload.get("image")
    query_text = processed_payload.get("query")

    if not image_url:
        logger.error("Image URL is missing in the payload.")
        raise ValueError("Image URL is required to generate artwork metadata.")

    logger.info(f"Fetching image from URL: {image_url}")
    pil_image = None
    try:
        response = requests.get(image_url)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        image_bytes = io.BytesIO(response.content)
        pil_image = Image.open(image_bytes)
        logger.info("Successfully fetched and opened image.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch image from {image_url}. Error: {e}")
        logger.exception("RequestException details:")
        raise
    except Image.UnidentifiedImageError as e:
        logger.error(
            f"Failed to open image from {image_url}. It might be corrupted or not a valid image format. Error: {e}"
        )
        logger.exception("UnidentifiedImageError details:")
        raise
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during image fetching or opening from {image_url}. Error: {e}"
        )
        logger.exception("Unexpected error details during image processing:")
        raise

    client = genai.Client(http_options=HttpOptions(api_version="v1"))
    model_name = "gemini-2.5-flash-preview-04-17"  # Changed from gemini-1.5-flash-latest to match original
    contents = [
        pil_image,
        query_text,
    ]  # Assuming query_text is the prompt/instruction for the LLM

    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
        ),
        response_mime_type="application/json",
        response_schema=ArtworkData,  # This suggests the client might return a parsed object or dict
        system_instruction=[
            types.Part.from_text(
                text=f"""Envision guiding an audience through a virtual gallery: when provided with an image (plus its title and artist), first describe everything visible—scenes,
                  figures, objects—then reveal the painting’s name and creator, outline its historical background, share essential biographical details about the artist,
                   and interpret the mood and emotions the work conveys. Be sure to populate every field in the schema.
        """
            ),
        ],
    )

    llm_output = None
    try:
        logger.info(
            f"Sending request to Gemini model: {model_name} for artwork metadata generation."
        )
        logger.debug(f"Contents being sent to LLM: [PIL Image, '{query_text}']")
        logger.debug(f"GenerateContentConfig: {generate_content_config}")

        llm_output = client.models.generate_content(
            model=model_name,  # Corrected to model_name
            contents=contents,
            config=generate_content_config,
        )
        logger.info("Successfully received response from Gemini model.")
        logger.debug(
            f"Raw LLM output text (first 500 chars): {llm_output.text[:500] if llm_output and hasattr(llm_output, 'text') else 'No text output'}"
        )
    except Exception as e:
        logger.error(f"Error calling Gemini API for artwork metadata. Error: {e}")
        logger.exception("Gemini API call exception details:")
        raise

    result_dict = None
    try:
        # If response_schema and response_mime_type are effective, llm_output might already be a dict or ArtworkData instance.
        # However, the original code uses json.loads(llm_output.text), so we follow that logic.
        if not llm_output or not hasattr(llm_output, "text") or not llm_output.text:
            logger.error("LLM output is empty or does not contain text.")
            raise ValueError("LLM response is empty or invalid.")

        logger.info("Parsing LLM JSON response.")
        result_dict = json.loads(llm_output.text)
        logger.info("Successfully parsed JSON response from LLM.")
        logger.debug(f"Parsed LLM result dictionary: {result_dict}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from LLM response. Error: {e}")
        logger.debug(
            f"LLM response text that failed parsing: {llm_output.text if llm_output else 'No LLM output'}"
        )
        logger.exception("JSONDecodeError details:")
        raise
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during LLM response parsing. Error: {e}"
        )
        logger.exception("Unexpected error during response parsing:")
        raise

    # Merging original payload data into the LLM result
    logger.info("Merging original payload data with LLM results.")
    original_data_payload = processed_payload.get(
        "payload", {}
    )  # Assuming "payload" key holds the original data dict
    for k, v in original_data_payload.items():
        if k == "_id" and v is not None:  # Ensure _id is not None before str()
            result_dict[k] = str(v)
            logger.debug(f"Set _id from original payload: {result_dict[k]}")
        elif (
            k not in result_dict or result_dict[k] is None
        ):  # Prioritize LLM results unless they are None
            result_dict[k] = v
            logger.debug(f"Merged key '{k}' from original payload.")
        else:
            logger.debug(
                f"Key '{k}' already present in LLM result or LLM result is not None, not overwriting from original payload."
            )

    artwork_data_instance = None
    try:
        logger.info("Validating and creating ArtworkData object from merged results.")
        artwork_data_instance = ArtworkData(**result_dict)
        logger.info("Successfully created ArtworkData object.")
        logger.debug(f"Final ArtworkData object: {artwork_data_instance}")
    except (
        Exception
    ) as e:  # Catch Pydantic ValidationError or other model instantiation errors
        logger.error(f"Failed to create ArtworkData object from dictionary. Error: {e}")
        logger.debug(f"Dictionary used for ArtworkData instantiation: {result_dict}")
        logger.exception("ArtworkData instantiation error details:")
        raise

    return artwork_data_instance


def llm_generate_audio_to_text(
    audio_bytes: bytes, artwork_json: dict, conversation_history: List[ChatMessage]
) -> str:
    logger.info("Starting llm_generate_audio_to_text function.")
    logger.debug(
        f"Received audio bytes (length: {len(audio_bytes) if audio_bytes else 0}). Artwork JSON: {artwork_json}"
    )
    message_context = []
    for message_ctx in conversation_history:
        message_context.append(
            {"role": message_ctx.role.value, "content": message_ctx.content}
        )

    if not audio_bytes:
        logger.error("Audio bytes are empty.")
        raise ValueError("Audio bytes cannot be empty for transcription.")

    client = genai.Client(http_options=HttpOptions(api_version="v1"))
    model_name = "gemini-2.5-pro-preview-06-05"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(
                    mime_type="audio/wav",  # Assuming WAV, adjust if different
                    data=audio_bytes,
                ),
                types.Part.from_text(
                    text=f"Given the information about the artwork: {json.dumps(artwork_json)} and previous user interaction/question answer to you {message_context}, use these information to reply to the user's query from the audio which contains his/her query. Keep the reply informative and under 10 seconds, strictly based on the surrounding artwork data."
                ),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="application/json",  # Expecting JSON output
        response_schema=AudioQuery,  # Schema for the JSON output
        system_instruction=[
            types.Part.from_text(
                text="You are an AI assistant. Transcribe the audio query and then answer it. Your answer must be based *only* around the artwork and information provided in the user's message context you can search you knowledge for any information regarding to it. If the query is unrelated to the artwork, state that you cannot answer. The response should be in JSON format matching the AudioQuery schema, with a 'response' field containing your textual answer, and `audio_text` with user input query in audio."
            ),
        ],
    )
    try:
        logger.info(
            f"Sending request to Gemini model: {model_name} for audio-to-text and query answering."
        )
        logger.debug(f"GenerateContentConfig for audio: {generate_content_config}")
        # Note: artwork_json is now part of the `contents` for the LLM to use as context.
        llm_output = client.models.generate_content(
            model=model_name,  # Corrected to model_name
            contents=contents,
            config=generate_content_config,
        )

        logger.info(
            f"Successfully received response from Gemini model for audio processing., 🔥 response {llm_output}"
        )
        return llm_output.parsed

    except Exception as e:
        logger.error(f"Error calling Gemini API for audio-to-text. Error: {e}")
        logger.exception("Gemini API call exception details (audio):")
        raise


def search_similar(
    query,
    collection,
    top_k=5,
):
    """
    Search for images similar to the query using the $search stage with knnBeta.
    - If query starts with 'http', download & embed on the fly.
    - Else treat query as stored image ID and fetch embedding.
    Returns a list of (image_id, score) tuples.
    """
    # # Create query embedding
    if isinstance(query, str) and query.startswith("http"):
        img = download_image(query)
        inputs = PROCESSOR(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            emb = MODEL.get_image_features(**inputs)
        query_emb = emb.cpu().numpy()[0]
        # Normalization is often done before storing, but good to ensure here too
        query_emb = query_emb / np.linalg.norm(query_emb)
    else:
        doc = collection.find_one({"_id": query})
        if not doc:
            raise ValueError(f"No embedding found for ID '{query}'")
        query_emb = np.array(doc["embedding"])

    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_emb.tolist(),
                "numCandidates": top_k * 10,
                "limit": top_k,
            }
        },
        {
            "$project": {
                "_id": 1,
                "plot": 1,
                "title": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    result = collection.aggregate(pipeline)
    return [i["_id"] for i in result]

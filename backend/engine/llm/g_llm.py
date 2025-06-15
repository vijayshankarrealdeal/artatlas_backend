from google import genai
from PIL import Image
from google.genai import types
import requests, io, json, os
from dotenv import load_dotenv
from engine.models.artworks_model import ArtworkData, LLMInputPayload

load_dotenv()


def llm_generate_artwork_metadata(payload: LLMInputPayload):
    payload = payload.generate_payload()
    image = payload.get("image")
    query = payload.get("query")

    response = requests.get(image)
    response.raise_for_status()
    image_bytes = io.BytesIO(response.content)
    image = Image.open(image_bytes)
    client = genai.Client(
        api_key="AIzaSyC6cggUnSifC0GhyJ6pAyd9CidngT2j8x4"
    )
    model = "gemini-2.5-flash-preview-04-17"
    contents = [image, query]
    # tools = [
    #     types.Tool(google_search=types.GoogleSearch()),
    # ]
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
        ),
        # tools=tools,
        response_mime_type="application/json",
        response_schema=ArtworkData,
        system_instruction=[
            types.Part.from_text(
                text=f"""Envision guiding an audience through a virtual gallery: when provided with an image (plus its title and artist), first describe everything visible—scenes,
                  figures, objects—then reveal the painting’s name and creator, outline its historical background, share essential biographical details about the artist,
                   and interpret the mood and emotions the work conveys. Be sure to populate every field in the schema.
        """
            ),
        ],
    )

    output = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    result = json.loads(output.text)
    for k, v in payload["payload"].items():
        if k == "_id":
            result[k] = str(v)
        else:
            result[k] = v
    result = ArtworkData(**result)
    return result

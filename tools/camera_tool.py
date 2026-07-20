"""
tools/camera_tool.py — Sadaf V4 Camera Tool

V4 changes:
  - Uses groq_proxy for all API calls (key rotation, rate management)
  - Removed direct AsyncGroq client and GROQ_API_KEY dependency
"""
import cv2
import asyncio
import tempfile
import base64
from pathlib import Path
import time

from groq_proxy import groq_proxy
from config import VISION_MODEL


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 for LLM input."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def capture_image(camera_index: int = 0) -> str:
    """Capture a single image using webcam and save to a temp file."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Camera not available at index {camera_index}. Check macOS Privacy settings.")

    time.sleep(0.5)

    ret = False
    frame = None
    for _ in range(5):
        ret, frame = cap.read()
        if ret and frame is not None and frame.mean() > 10:
            break
        time.sleep(0.1)

    cap.release()

    if not ret or frame is None or frame.mean() <= 10:
        raise RuntimeError("Failed to capture image or image is black.")

    tmp_file = Path(tempfile.gettempdir()) / "captured_image.jpg"
    cv2.imwrite(str(tmp_file), frame)
    return str(tmp_file)


async def analyze_image_with_groq(image_path: str, query: str) -> str:
    """Send the captured image and query to Groq Vision LLM via proxy."""
    image_base64 = encode_image_to_base64(image_path)

    result = await groq_proxy.call(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ],
        temperature=0.3,
        max_tokens=500,
    )
    return result or "I couldn't analyze the image."


async def camera_tool(user_query: str) -> str:
    """Capture an image and return the LLM's response."""
    try:
        image_path = await asyncio.to_thread(capture_image)
        vision_response = await analyze_image_with_groq(image_path, user_query)
        return vision_response
    except Exception as e:
        return f"Error while using camera: {e}"

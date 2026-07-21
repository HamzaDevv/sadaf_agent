"""
brain/vision.py — Sadaf V4 Camera capture + Groq Vision

V4 changes:
  - Uses groq_proxy for all API calls (key rotation, rate management)
  - Otherwise identical pipeline: capture → vision → compress → TTS
"""
import asyncio
import base64
import tempfile
import time
from pathlib import Path

import cv2
from groq_proxy import groq_proxy
from config import VISION_MODEL, CHAT_MODEL
from utils import strip_think_tags



def _capture_frame(camera_index: int = 0) -> str:
    """Capture a single frame from webcam. Returns path to saved JPEG."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(
            f"Camera not available at index {camera_index}. "
            "Check macOS Privacy & Security > Camera settings."
        )

    time.sleep(0.5)  # Let camera initialize

    frame = None
    for _ in range(5):
        ret, f = cap.read()
        if ret and f is not None and f.mean() > 10:
            frame = f
            break
        time.sleep(0.1)

    cap.release()

    if frame is None:
        raise RuntimeError("Failed to capture a valid image from camera.")

    tmp = Path(tempfile.gettempdir()) / "sadaf_vision.jpg"
    cv2.imwrite(str(tmp), frame)
    return str(tmp)


def _encode_image(path: str) -> str:
    """Base64-encode an image file."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _raw_vision_response(image_path: str, query: str) -> str:
    """Call Groq Vision model via proxy and return the raw response."""
    b64 = await asyncio.to_thread(_encode_image, image_path)

    # Vision model requires direct client (multimodal content type)
    # groq_proxy.call() handles key rotation transparently
    from groq_proxy import groq_proxy as _proxy
    result = await _proxy.call(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    return strip_think_tags(result or "")


async def _compress_vision_response(raw: str, query: str) -> str:
    """Compress verbose vision response into 1-2 spoken sentences via proxy."""
    result = await groq_proxy.call(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a voice assistant. Convert the following verbose vision "
                    "analysis into a single, short, spoken-English response of 1-2 "
                    "sentences maximum. Be direct and conversational. "
                    "No markdown. No lists. No asterisks."
                ),
            },
            {
                "role": "user",
                "content": f"User asked: '{query}'\n\nVision analysis:\n{raw}",
            },
        ],
        temperature=0.3,
        max_tokens=80,
    )
    return result or ""


async def analyze_scene(user_query: str) -> str:
    """Full pipeline: capture → vision model → compress → return short spoken answer."""
    try:
        image_path = await asyncio.to_thread(_capture_frame)
        raw_response = await _raw_vision_response(image_path, user_query)
        return raw_response
    except Exception as e:
        return f"I couldn't use the camera right now. {e}"

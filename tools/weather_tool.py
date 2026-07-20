"""
tools/weather_tool.py — Sadaf Jarvis Weather Tool

100% free, no API key required.
Uses ip-api.com for auto-location + Open-Meteo for weather.
"""
import asyncio
import requests

IP_API = "http://ip-api.com/json/"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

# WMO weather code → human readable
WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "icy fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "heavy drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "slight showers", 81: "moderate showers", 82: "violent showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def _get_location() -> dict:
    """Auto-detect city/lat/lon via IP geolocation."""
    try:
        resp = requests.get(IP_API, timeout=4).json()
        if resp.get("status") == "success":
            return {
                "city": resp.get("city", "your city"),
                "lat": resp.get("lat"),
                "lon": resp.get("lon"),
            }
    except Exception:
        pass
    return {"city": "your location", "lat": None, "lon": None}


def _get_weather(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo."""
    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weathercode,wind_speed_10m",
            "wind_speed_unit": "kmh",
            "temperature_unit": "celsius",
            "timezone": "auto",
        }
        resp = requests.get(OPEN_METEO, params=params, timeout=5).json()
        current = resp.get("current", {})
        return {
            "temp": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "code": current.get("weathercode"),
        }
    except Exception:
        return {}


async def get_weather(query: str = "") -> str:
    """Return spoken-English current weather for the user's location."""
    loc = await asyncio.to_thread(_get_location)
    if loc["lat"] is None:
        return "I couldn't detect your location to check the weather."

    weather = await asyncio.to_thread(_get_weather, loc["lat"], loc["lon"])
    if not weather:
        return "I couldn't fetch the weather right now."

    temp = weather.get("temp")
    code = weather.get("code", 0)
    humidity = weather.get("humidity")
    wind = weather.get("wind_speed")
    description = WMO_CODES.get(code, "conditions unknown")

    city = loc["city"]
    parts = [f"It's {temp}°C with {description} in {city}."]
    if humidity is not None:
        parts.append(f"Humidity is at {humidity}%")
    if wind is not None:
        parts.append(f"and wind is {wind} km/h.")

    return " ".join(parts)

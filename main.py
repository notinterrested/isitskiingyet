from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

# щоб фронтенд зі Static Web App міг викликати API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BUKOVEL_LAT = 48.356
BUKOVEL_LON = 24.421

@app.get("/api/weather")
def weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={BUKOVEL_LAT}&longitude={BUKOVEL_LON}"
        "&current=temperature_2m"
    )
    data = requests.get(url, timeout=10).json()
    temp = data.get("current", {}).get("temperature_2m")
    season_possible = (temp is not None) and (temp <= 0)
    return {"temperature_c": temp, "season_possible": season_possible}

@app.get("/api/health")
def health():
    return {"status": "ok"}

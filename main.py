import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Cosmos (optional)
COSMOS_ENABLED = False
container = None

try:
    from azure.cosmos import CosmosClient, PartitionKey  # type: ignore
except Exception:
    CosmosClient = None  # noqa


app = FastAPI(title="Is it skiing yet? API")

# Для простоти дозволяємо всі origins (для навчального проєкту ок)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bukovel approx coordinates
BUKOVEL_LAT = 48.356
BUKOVEL_LON = 24.421


def init_cosmos() -> None:
    """
    Ініціалізує Cosmos DB, якщо задані env vars.
    Створює database+container, якщо їх немає.
    """
    global COSMOS_ENABLED, container

    endpoint = os.getenv("COSMOS_ENDPOINT")
    key = os.getenv("COSMOS_KEY")
    db_name = os.getenv("COSMOS_DATABASE", "weatherdb")
    cont_name = os.getenv("COSMOS_CONTAINER", "requests")

    if not endpoint or not key or CosmosClient is None:
        COSMOS_ENABLED = False
        return

    client = CosmosClient(endpoint, credential=key)
    db = client.create_database_if_not_exists(id=db_name)
    container = db.create_container_if_not_exists(
        id=cont_name,
        partition_key=PartitionKey(path="/pk"),
        offer_throughput=400,  # мінімально; з Free Tier не критично
    )
    COSMOS_ENABLED = True


@app.on_event("startup")
def on_startup():
    init_cosmos()


@app.get("/api/health")
def health():
    return {"status": "ok", "cosmos_enabled": COSMOS_ENABLED}


def fetch_bukovel_14d_forecast() -> Dict[str, Any]:
    """
    Беремо daily forecast на 14 днів з Open-Meteo.
    Беремо, наприклад, максимальну температуру (можна min/mean — як захочеш).
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={BUKOVEL_LAT}&longitude={BUKOVEL_LON}"
        "&daily=temperature_2m_max"
        "&forecast_days=14"
        "&timezone=auto"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()

    daily = data.get("daily", {})
    dates: List[str] = daily.get("time", [])
    temps: List[float] = daily.get("temperature_2m_max", [])

    items = [{"date": d, "temp_c": t} for d, t in zip(dates, temps)]
    return {
        "source": "open-meteo",
        "lat": BUKOVEL_LAT,
        "lon": BUKOVEL_LON,
        "items": items,
    }


@app.post("/api/update-forecast")
def update_forecast():
    """
    1) Тягнемо прогноз на 14 днів
    2) Пишемо в Cosmos DB (якщо є)
    3) Повертаємо items на фронт
    """
    forecast = fetch_bukovel_14d_forecast()
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "id": str(uuid.uuid4()),
        "pk": "bukovel",  # partition key
        "created_at": now,
        "forecast_days": 14,
        "forecast": forecast,
    }

    saved = False
    if COSMOS_ENABLED and container is not None:
        container.upsert_item(record)
        saved = True

    return {
        "saved_to_db": saved,
        "created_at": now,
        "items": forecast["items"],
    }


@app.get("/api/history")
def history(limit: int = 10):
    """
    Повертаємо останні N запитів (для демо/звіту).
    """
    if not (COSMOS_ENABLED and container is not None):
        return {"items": [], "note": "Cosmos DB is not configured"}

    # Cosmos SQL: беремо останні записи по bukovel
    q = (
        "SELECT TOP @limit c.id, c.created_at, c.forecast "
        "FROM c WHERE c.pk = 'bukovel' ORDER BY c.created_at DESC"
    )
    params = [{"name": "@limit", "value": int(limit)}]

    rows = list(
        container.query_items(
            query=q,
            parameters=params,
            enable_cross_partition_query=True,
        )
    )

    # компактний формат для фронту/перевірки
    out = []
    for row in rows:
        out.append(
            {
                "id": row.get("id"),
                "created_at": row.get("created_at"),
                "items": (row.get("forecast") or {}).get("items", []),
            }
        )

    return {"items": out}

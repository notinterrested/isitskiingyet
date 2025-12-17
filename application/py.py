import os
import uvicorn

from main import app  # твій FastAPI() у main.py

if __name__ == "__main__":
    port = int(os.getenv("PORT") or os.getenv("WEBSITES_PORT") or 8000)
    uvicorn.run(app, host="0.0.0.0", port=port)

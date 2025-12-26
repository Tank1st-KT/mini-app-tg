from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes.main import router as main_router


app = FastAPI(title="Mini-App TG API")
app.include_router(main_router)

@app.get("/")
async def root():
    return {"ok": True, "service": "tg-miniapp-api", "docs": "/docs", "health": "/health"}

@app.get("/health")
def health():
    return {"status": "ok"}

DIST_DIR = Path(__file__).resolve().parents[1] / "webapp" / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
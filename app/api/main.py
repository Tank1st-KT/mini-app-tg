from fastapi import FastAPI
from app.api.main import router as main_router

app = FastAPI(title="Mini-App TG API")

app.include_router(main_router)

@app.get("/health")
def health():
    return {"status": "ok"}
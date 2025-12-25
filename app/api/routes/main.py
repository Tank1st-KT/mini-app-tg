# =========================
#! Imports
# =========================
import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator, Annotated, TypeAlias

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, Message


# =========================
#! Settings
# =========================
@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "8450501582:AAFkS0e5dEtT_KZA9ZlXV77EaX1QTLv2QOY")
    app_secret: str = os.getenv("APP_SECRET", "dev-secret-change-me")
    miniapp_url: str = os.getenv("MINIAPP_URL", "https://mini-app-tg-bot.netlify.app/")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://mini_app_tg_bot_user:h6vWkyIbR6XjbGg2Qt6egOYCYAjMAL9k@dpg-d56jsjp5pdvs738eckk0-a.frankfurt-postgres.render.com/mini_app_tg_bot")

    cors_allow_origins: List[str] = None

    def __post_init__(self):
        object.__setattr__(self, "cors_allow_origins", ["*"])


settings = Settings()


# =========================
#! Helpers: Database URL normalize
# =========================
def normalize_database_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# =========================
#! Database: SQLAlchemy Async
# =========================
class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    prompt: Mapped[str] = mapped_column(Text)
    result_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


engine: Optional[AsyncEngine] = None
SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

db_url = normalize_database_url(settings.database_url)
if db_url:
    engine = create_async_engine(db_url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if not SessionLocal:
        raise HTTPException(status_code=500, detail="DATABASE_URL не настроен (Postgres не подключён).")
    async with SessionLocal() as session:
        yield session


DBSession: TypeAlias = Annotated[AsyncSession, Depends(get_db)]


# =========================
#! Auth: Telegram initData verify + our token
# =========================
def _parse_qs(init_data: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in init_data.split("&"):
        if not part:
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k] = v
    return out


def verify_telegram_init_data(init_data: str, bot_token: str) -> bool:
    if not init_data or not bot_token:
        return False

    params = _parse_qs(init_data)
    received_hash = params.get("hash", "")
    if not received_hash:
        return False

    data_pairs = []
    for k, v in params.items():
        if k == "hash":
            continue
        data_pairs.append(f"{k}={v}")
    data_check_string = "\n".join(sorted(data_pairs))

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    return hmac.compare_digest(calculated_hash, received_hash)


def extract_telegram_user_id(init_data: str) -> Optional[int]:
    params = _parse_qs(init_data)
    user_raw = params.get("user")
    if not user_raw:
        return None
    try:
        user_obj = json.loads(user_raw)
        return int(user_obj.get("id"))
    except Exception:
        return None


def make_bearer_token(telegram_id: int) -> str:
    ts = str(int(time.time()))
    payload = f"{telegram_id}.{ts}"
    sig = hmac.new(settings.app_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_bearer_token(token: str) -> Optional[int]:
    try:
        telegram_id_s, ts_s, sig = token.split(".", 2)
        payload = f"{telegram_id_s}.{ts_s}"
        expected = hmac.new(settings.app_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return int(telegram_id_s)
    except Exception:
        return None


def get_current_user_id(authorization: str = Header(default="")) -> int:
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    uid = verify_bearer_token(token)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token")
    return uid

CurrentUserId = Annotated[int, Depends(get_current_user_id)]

# =========================
#! API: schemas
# =========================
class AuthTelegramIn(BaseModel):
    initData: str


class AuthTelegramOut(BaseModel):
    ok: bool
    token: str
    user: Dict[str, int]


class GenerateIn(BaseModel):
    prompt: str


class GenerateOut(BaseModel):
    job_id: str
    status: str
    echo_prompt: Optional[str] = None
    result_text: Optional[str] = None


class PaymentIn(BaseModel):
    productId: str


# =========================
#! FastAPI app
# =========================
app = FastAPI(title="TG MiniApp API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    # 1) DB migrate-lite (create tables)
    if engine:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # 2) start bot polling (если BOT_TOKEN задан)
    if settings.bot_token:
        app.state.bot_task = asyncio.create_task(start_bot_polling())
    else:
        app.state.bot_task = None


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "bot_task", None)
    if task:
        task.cancel()


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True}


@app.post("/auth/telegram", response_model=AuthTelegramOut)
async def auth_telegram(payload: AuthTelegramIn) -> AuthTelegramOut:
    if not settings.bot_token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не задан")

    if not verify_telegram_init_data(payload.initData, settings.bot_token):
        raise HTTPException(status_code=401, detail="Bad initData signature")

    tg_id = extract_telegram_user_id(payload.initData)
    if not tg_id:
        raise HTTPException(status_code=400, detail="Cannot extract telegram user id")

    token = make_bearer_token(tg_id)
    return AuthTelegramOut(ok=True, token=token, user={"telegram_id": tg_id})


@app.post("/generate", response_model=GenerateOut)
async def generate(
    body: GenerateIn,
    telegram_id: CurrentUserId,
    db: DBSession,
) -> GenerateOut:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    job = Job(
        id=job_id,
        telegram_id=str(telegram_id),
        status="queued",
        prompt=body.prompt,
        result_text=None,
        created_at=now,
    )
    db.add(job)
    await db.commit()

    return GenerateOut(job_id=job_id, status="queued", echo_prompt=body.prompt)


@app.get("/jobs")
async def list_jobs(
    telegram_id: CurrentUserId,
    db: DBSession,
) -> List[Dict[str, Any]]:
    q = (
        select(Job)
        .where(Job.telegram_id == str(telegram_id))
        .order_by(Job.created_at.desc())
        .limit(50)
    )
    res = await db.execute(q)
    jobs = res.scalars().all()

    return [
        {
            "id": j.id,
            "status": j.status,
            "prompt": j.prompt,
            "created_at": j.created_at.isoformat(),
            "result_text": j.result_text,
        }
        for j in jobs
    ]


@app.post("/payments/create")
async def payments_create(
    body: PaymentIn,
    telegram_id: CurrentUserId,
) -> Dict[str, str]:
    return {"url": f"https://example.com/pay?product={body.productId}&user={telegram_id}"}


# =========================
#! Bot: aiogram (polling)
# =========================
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not settings.miniapp_url:
        await message.answer("MINIAPP_URL не задан. Укажи ссылку на фронт Mini App в переменных окружения.")
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть Mini App", web_app=WebAppInfo(url=settings.miniapp_url))]
        ],
        resize_keyboard=True,
    )
    await message.answer("Ок. Открывай приложение кнопкой ниже.", reply_markup=kb)


async def start_bot_polling() -> None:
    bot = Bot(token=settings.bot_token)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


# =========================
#! Local run
# =========================
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
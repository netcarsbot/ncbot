import logging
import os
import asyncio
import json
import uuid
import pytz
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")
UPLOAD_DIR = Path("uploads")
SCHEDULE_FILE = Path("schedule.json")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

UPLOAD_DIR.mkdir(exist_ok=True)
if not SCHEDULE_FILE.exists():
    SCHEDULE_FILE.write_text("[]")

def get_next_schedule_time():
    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)
    today_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)
    total_slots = int((today_end - today_start).total_seconds() // 60)
    scheduled = json.loads(SCHEDULE_FILE.read_text())
    used_slots = [datetime.fromisoformat(p["publish_at"]) for p in scheduled]
    for i in range(total_slots):
        candidate = today_start + timedelta(minutes=i)
        if all(abs((candidate - u).total_seconds()) >= 60 for u in used_slots):
            return candidate
    return today_end

def save_to_schedule(post):
    posts = json.loads(SCHEDULE_FILE.read_text())
    posts.append(post)
    SCHEDULE_FILE.write_text(json.dumps(posts, ensure_ascii=False, indent=2))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Добро пожаловать! Пришли 9 фото, видео и описание.")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.message.media_group_id or str(uuid.uuid4())
    group_path = UPLOAD_DIR / group_id
    group_path.mkdir(exist_ok=True)

    # Сохраняем фото
    for item in update.message.photo or []:
        file = await context.bot.get_file(item.file_id)
        await file.download_to_drive(group_path / f"{uuid.uuid4()}.jpg")

    # Сохраняем видео
    if update.message.video:
        file = await context.bot.get_file(update.message.video.file_id)
        await file.download_to_drive(group_path / "video.mp4")

    # Сохраняем описание и запланировать
    if update.message.caption:
        post = {

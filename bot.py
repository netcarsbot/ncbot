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

# Загрузка токена и канала
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")

# Пути
UPLOAD_DIR = Path("uploads")
SCHEDULE_FILE = Path("schedule.json")

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Подготовка директорий и файлов
UPLOAD_DIR.mkdir(exist_ok=True)
if not SCHEDULE_FILE.exists():
    SCHEDULE_FILE.write_text("[]")

# Получить следующее свободное время публикации
def get_next_schedule_time():
    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)
    start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    end = now.replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)
    total_minutes = int((end - start).total_seconds() // 60)
    scheduled = json.loads(SCHEDULE_FILE.read_text())
    used = [datetime.fromisoformat(p["publish_at"]) for p in scheduled]

    for i in range(total_minutes):
        candidate = start + timedelta(minutes=i)
        if all(abs((candidate - u).total_seconds()) >= 60 for u in used):
            return candidate
    return end

# Сохранение поста в файл расписания
def save_to_schedule(post):
    data = json.loads(SCHEDULE_FILE.read_text())
    data.append(post)
    SCHEDULE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Добро пожаловать! Пришли 9 фото, видео и описание.")

# Обработка медиа
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.message.media_group_id or str(uuid.uuid4())
    group_path = UPLOAD_DIR / group_id
    group_path.mkdir(exist_ok=True)

    for photo in update.message.photo or []:
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(group_path / f"{uuid.uuid4()}.jpg")

    if update.message.video:
        file = await context.bot.get_file(update.message.video.file_id)
        await file.download_to_drive(group_path / "video.mp4")

    if update.message.caption:
        post = {
            "text": update.message.caption,
            "photos": [str(p) for p in sorted(group_path.glob("*.jpg"))],
            "video": str(group_path / "video.mp4") if (group_path / "video.mp4").exists() else None,
            "publish_at": get_next_schedule_time().isoformat()
        }
        save_to_schedule(post)
        await update.message.reply_text("Объявление получено и запланировано.")

# Планировщик публикаций
async def scheduler(app):
    while True:
        try:
            posts = json.loads(SCHEDULE_FILE.read_text())
            now = datetime.now(pytz.timezone("Asia/Shanghai"))
            ready = [p for p in posts if datetime.fromisoformat(p["publish_at"]) <= now]
            pending = [p for p in posts if p not in ready]

            for post in ready:
                media = [InputMediaPhoto(open(photo, "rb")) for photo in post["photos"]]
                if post.get("video"):
                    await app.bot.send_message(chat_id=CHANNEL, text=post["text"])
                    await app.bot.send_video(chat_id=CHANNEL, video=open(post["video"], "rb"))
                else:
                    await app.bot.send_media_group(chat_id=CHANNEL, media=media)
                    await app.bot.send_message(chat_id=CHANNEL, text=post["text"])

            SCHEDULE_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2))
        except Exception as e:
            logging.exception("Ошибка в планировщике")

        await asyncio.sleep(60)

# Инициализация бота
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ALL, handle_media))
app.job_queue.run_once(lambda *_: asyncio.create_task(scheduler(app)), 0)

if __name__ == "__main__":
    app.run_polling()

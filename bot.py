import logging
import os
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz, json, uuid, shutil, asyncio
from pathlib import Path

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")
UPLOAD_DIR = Path("uploads")
SCHEDULE_FILE = Path("schedule.json")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

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

    for item in update.message.photo or []:
        file = await context.bot.get_file(item.file_id)
        await file.download_to_drive(group_path / f"{uuid.uuid4()}.jpg")

    if update.message.video:
        file = await context.bot.get_file(update.message.video.file_id)
        await file.download_to_drive(group_path / "video.mp4")

    if update.message.caption:
        post = {
            "text": update.message.caption,
            "photos": [str(p) for p in group_path.glob("*.jpg")],
            "video": str(group_path / "video.mp4") if (group_path / "video.mp4").exists() else None,
            "publish_at": get_next_schedule_time().isoformat()
        }
        save_to_schedule(post)
        await update.message.reply_text("Объявление получено и запланировано.")

async def scheduler(app):
    while True:
        try:
            posts = json.loads(SCHEDULE_FILE.read_text())
            now = datetime.now(pytz.timezone("Asia/Shanghai"))
            to_publish = [p for p in posts if datetime.fromisoformat(p["publish_at"]) <= now]
            remaining = [p for p in posts if p not in to_publish]
            for post in to_publish:
                media = [InputMediaPhoto(open(photo, "rb")) for photo in post["photos"]]
                if post.get("video"):
                    await app.bot.send_message(chat_id=CHANNEL, text=post["text"])
                    await app.bot.send_video(chat_id=CHANNEL, video=open(post["video"], "rb"))
                else:
                    await app.bot.send_media_group(chat_id=CHANNEL, media=media)
                    await app.bot.send_message(chat_id=CHANNEL, text=post["text"])
            SCHEDULE_FILE.write_text(json.dumps(remaining, ensure_ascii=False, indent=2))
        except Exception as e:
            logging.exception("Scheduler error")
        await asyncio.sleep(60)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ALL, handle_media))
app.job_queue.run_once(lambda *_: asyncio.create_task(scheduler(app)), 0)

if __name__ == "__main__":
    app.run_polling()

import asyncio
import logging
import os
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler

from yt_dlp import YoutubeDL
from telegram import Update, BotCommand
from telegram.constants import ChatAction
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest


# BOT token is read from environment for deployments
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Channel/admin config will be validated in main() and set globally.
CHANNEL_ID: int | None = None
SEND_TO_CHANNEL = os.environ.get("SEND_TO_CHANNEL", "true").lower() in {"1", "true", "yes", "on"}
ADMIN_IDS: set[int] = set()

# Directories
BASE_DIR = Path(__file__).resolve().parent
# Download into Bot API shared dir so file:// works inside the container
DOWNLOAD_DIR = Path("/var/lib/telegram-bot-api/uploads")
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "bot.log"


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)


def extract_first_url(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"(https?://\S+)", text, flags=re.IGNORECASE)
    if m:
        url = m.group(1)
    else:
        m2 = re.search(
            r"(?:(?:^|\s))((?:www\.)?(?:[a-z0-9-]+\.)?pornhub(?:premium)?\.com/\S+)",
            text,
            flags=re.IGNORECASE,
        )
        url = f"https://{m2.group(1)}" if m2 else None
    if not url:
        return None
    url = url.rstrip(").,;:!?\"]'>")
    return url


def is_pornhub_url(url: str | None) -> bool:
    if not url:
        return False
    return any(domain in url.lower() for domain in ["pornhub.com", "pornhubpremium.com"]) 


def _ydl_opts(tmp_dir: Path) -> dict:
    return {
        "outtmpl": str(tmp_dir / "%(title).80s-%(id)s.%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "format": (
            "b[ext=mp4]/b/"
            "bv*+ba/bv*[ext=mp4]+ba[ext=m4a]"
        ),
    }


def download_video_sync(url: str) -> tuple[str, dict]:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    opts = _ydl_opts(DOWNLOAD_DIR)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = None
        if isinstance(info, dict):
            if "requested_downloads" in info and info["requested_downloads"]:
                filepath = info["requested_downloads"][0].get("filepath")
            if not filepath:
                filepath = ydl.prepare_filename(info)
        if not filepath or not os.path.exists(filepath):
            raise FileNotFoundError("Failed to determine downloaded file path")
        return filepath, info


async def download_video(url: str) -> tuple[str, dict]:
    return await asyncio.to_thread(download_video_sync, url)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat = update.effective_chat
        logging.info("/start from uid=%s chat_id=%s type=%s", getattr(user, 'id', None), getattr(chat, 'id', None), getattr(chat, 'type', None))
        try:
            context.chat_data['handled_start_update_id'] = update.update_id
        except Exception:
            pass
        await update.effective_message.reply_text(
            "发送一个 Pornhub 视频链接给我，我会帮你下载。Github地址：https://github.com/Sapphirecho8/awesome_pornhub_download_bot"
        )
    except Exception as e:
        logging.exception("Error handling /start: %s", e)


async def _debug_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = update.effective_chat
        msg = update.effective_message
        logging.info(
            "debug update: chat_id=%s type=%s text=%s has_entities=%s",
            getattr(chat, "id", None), getattr(chat, "type", None), getattr(msg, "text", None),
            bool(getattr(msg, "entities", None)) if msg else None,
        )
        if msg and isinstance(msg.text, str):
            t = msg.text.strip()
            handled_sid = context.chat_data.get('handled_start_update_id') if hasattr(context, 'chat_data') else None
            if re.match(r"^(/|／)start(?:@\S+)?(?:\s|$)", t, re.IGNORECASE) and handled_sid != update.update_id:
                logging.info("debug fallback: sending start help to chat_id=%s", getattr(chat, "id", None))
                await context.bot.send_message(
                    chat_id=getattr(chat, "id", None),
                    text=(
                        "发送一个 Pornhub 视频链接给我，我会帮你下载。Github地址：https://github.com/Sapphirecho8/awesome_pornhub_download_bot"
                    ),
                )
    except Exception as e:
        logging.warning("debug log error: %s", e)


async def set_channel_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SEND_TO_CHANNEL
    args = (context.args or [])
    logging.info("/sendtochannel invoked by uid=%s args=%s", getattr(update.effective_user, 'id', None), args)
    if not args:
        try:
            context.chat_data['handled_sendto_update_id'] = update.update_id
        except Exception:
            pass
        await update.effective_message.reply_text(
            f"当前频道模式: {'开启' if SEND_TO_CHANNEL else '关闭'}\n频道ID: {CHANNEL_ID}\n用法: /sendtochannel on|off"
        )
        return
    val = args[0].lower()
    if val in {"on", "true", "1", "yes"}:
        SEND_TO_CHANNEL = True
    elif val in {"off", "false", "0", "no"}:
        SEND_TO_CHANNEL = False
    else:
        await update.effective_message.reply_text("参数无效，用法: /sendtochannel on|off")
        return
    try:
        context.chat_data['handled_sendto_update_id'] = update.update_id
    except Exception:
        pass
    await update.effective_message.reply_text(f"已更新，频道模式: {'开启' if SEND_TO_CHANNEL else '关闭'}")


async def set_channel_mode_regex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SEND_TO_CHANNEL
    msg = update.effective_message
    text = (msg.text or "").strip()
    logging.info("/sendtochannel (regex) invoked by uid=%s text=%s", getattr(update.effective_user, 'id', None), text)
    m = re.match(r"^\s*(/|／)sendtochannel(?:@\S+)?(?:\s+(on|off))?\s*$", text, re.IGNORECASE)
    if not m:
        return
    val = (m.group(2) or "").lower()
    if not val:
        await msg.reply_text(
            f"当前频道模式: {'开启' if SEND_TO_CHANNEL else '关闭'}\n频道ID: {CHANNEL_ID}\n用法: /sendtochannel on|off"
        )
        return
    if val in {"on", "true", "1", "yes"}:
        SEND_TO_CHANNEL = True
    elif val in {"off", "false", "0", "no"}:
        SEND_TO_CHANNEL = False
    else:
        await msg.reply_text("参数无效，用法: /sendtochannel on|off")
        return
    try:
        context.chat_data['handled_sendto_update_id'] = update.update_id
    except Exception:
        pass
    await msg.reply_text(f"已更新，频道模式: {'开启' if SEND_TO_CHANNEL else '关闭'}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    text = msg.text or ""
    url = extract_first_url(text)

    if not is_pornhub_url(url):
        return

    if not user or user.id not in ADMIN_IDS:
        await msg.reply_text(
            "抱歉，这不是你的机器人，请向管理员申请权限或者自行部署机器人，Github地址：https://github.com/Sapphirecho8/awesome_pornhub_download_bot"
        )
        return

    logging.info("Request from uid=%s name=%s url=%s", user.id if user else None, user.full_name if user else None, url)

    file_to_cleanup: str | None = None
    sent_ok = False
    try:
        await msg.reply_chat_action(ChatAction.TYPING)
        notify = await msg.reply_text("开始下载，请稍候…")

        await msg.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
        filepath, info = await download_video(url)
        file_to_cleanup = filepath
        title = info.get("title") or Path(filepath).stem
        size = os.path.getsize(filepath)
        logging.info("Downloaded file: %s (%.2f MB)", filepath, size / (1024 * 1024))

        is_mp4 = filepath.lower().endswith(".mp4")
        caption = title or ""
        duration = None
        width = None
        height = None
        try:
            duration = int(info.get("duration")) if info.get("duration") else None
        except Exception:
            duration = None
        width = info.get("width") if isinstance(info, dict) else None
        height = info.get("height") if isinstance(info, dict) else None
        if (width is None or height is None) and isinstance(info, dict):
            rd = info.get("requested_downloads") or []
            if rd and isinstance(rd, list):
                w = rd[0].get("width")
                h = rd[0].get("height")
                width = width or w
                height = height or h

        await msg.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
        abs_path = str(Path(filepath).resolve())
        file_uri = Path(abs_path).as_uri()
        target_chat = CHANNEL_ID if SEND_TO_CHANNEL else msg.chat_id
        try:
            if is_mp4:
                logging.info(
                    "Sending via file URI as video to %s: %s (duration=%s w=%s h=%s)",
                    target_chat, file_uri, duration, width, height,
                )
                await context.bot.send_video(
                    chat_id=target_chat,
                    video=file_uri,
                    caption=caption,
                    supports_streaming=True,
                    duration=duration,
                    width=width,
                    height=height,
                )
            else:
                logging.info("Non-mp4; sending via file URI as document to %s: %s", target_chat, file_uri)
                await context.bot.send_document(chat_id=target_chat, document=file_uri, caption=caption)
            sent_ok = True
        except Exception as e:
            logging.warning("file URI send failed (%s); trying upload as video", e)
        if not sent_ok:
            with open(filepath, "rb") as f:
                try:
                    logging.info(
                        "Uploading as video (fallback) to %s: %s (duration=%s w=%s h=%s)",
                        target_chat, filepath, duration, width, height,
                    )
                    await context.bot.send_video(
                        chat_id=target_chat,
                        video=f,
                        caption=caption,
                        supports_streaming=True,
                        duration=duration,
                        width=width,
                        height=height,
                    )
                    sent_ok = True
                except Exception as e:
                    logging.warning("send_video upload failed (%s); falling back to document", e)
                    f.seek(0)
                    await context.bot.send_document(chat_id=target_chat, document=f, caption=caption)
                    sent_ok = True

        if sent_ok:
            if SEND_TO_CHANNEL:
                try:
                    await msg.reply_text("下载完成，已发送。")
                except Exception as de:
                    logging.warning("Failed to send completion DM: %s", de)
            else:
                try:
                    await notify.delete()
                except Exception as de:
                    logging.warning("Failed to delete notify message: %s", de)

        logging.info("Sent file to uid=%s and will delete local copy", user.id if user else None)

    except Exception as e:
        logging.exception("Error processing url=%s: %s", url, e)
        await msg.reply_text(f"抱歉，下载或发送失败：{e}")
    finally:
        try:
            if sent_ok and file_to_cleanup and os.path.exists(file_to_cleanup):
                os.remove(file_to_cleanup)
                logging.info("Deleted file: %s", file_to_cleanup)
            elif file_to_cleanup and os.path.exists(file_to_cleanup):
                logging.info("Keeping file due to send failure: %s", file_to_cleanup)
        except Exception as ce:
            logging.warning("Cleanup error: %s", ce)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled exception: %s", context.error)


def main() -> None:
    setup_logging()
    if not BOT_TOKEN:
        raise SystemExit("BOT token is missing (set env BOT_TOKEN)")
    channel_env = os.environ.get("CHANNEL_ID")
    admin_env = os.environ.get("ADMIN_IDS")
    if not channel_env:
        raise SystemExit("CHANNEL_ID is missing (set env CHANNEL_ID)")
    try:
        ch_id = int(channel_env)
    except Exception:
        raise SystemExit(f"CHANNEL_ID must be an integer, got: {channel_env!r}")
    if not admin_env:
        raise SystemExit("ADMIN_IDS is missing (set env ADMIN_IDS as comma-separated IDs)")
    try:
        parsed_admins = {int(x) for x in [s.strip() for s in admin_env.split(",") if s.strip()]}
    except Exception:
        raise SystemExit(f"ADMIN_IDS must be comma-separated integers, got: {admin_env!r}")
    if not parsed_admins:
        raise SystemExit("ADMIN_IDS is empty after parsing; provide at least one admin id")
    global CHANNEL_ID, ADMIN_IDS
    CHANNEL_ID = ch_id
    ADMIN_IDS = parsed_admins

    base_url = os.environ.get("BOT_API_BASE_URL", "http://127.0.0.1:8081/bot")
    request = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=30.0,
        read_timeout=3600.0,
        write_timeout=3600.0,
    )
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .base_url(base_url)
        .base_file_url(os.environ.get("BOT_API_FILE_URL", "http://127.0.0.1:8081/file/bot"))
        .local_mode(True)
        .request(request)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(MessageHandler(filters.ALL, _debug_log, block=False), group=2)
    app.add_handler(CommandHandler("start", start))
    import re as _re
    app.add_handler(MessageHandler(filters.Regex(_re.compile(r"^\s*(/|／)start(?:@\S+)?(?:\s|$)", _re.IGNORECASE)), start))
    async def _post_init(application):
        try:
            await application.bot.set_my_commands([
                BotCommand("sendtochannel", "调整是否推送到频道"),
            ])
        except Exception as e:
            logging.warning("Failed to set bot commands: %s", e)
    app.post_init = _post_init
    app.add_handler(CommandHandler("sendtochannel", set_channel_mode))
    app.add_handler(MessageHandler(~filters.COMMAND & filters.Regex(_re.compile(r"^\s*(/|／)sendtochannel(?:@\S+)?(?:\s+(on|off))?\s*$", _re.IGNORECASE)), set_channel_mode_regex), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text), group=1)
    app.add_error_handler(on_error)

    logging.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()


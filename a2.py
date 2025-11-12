#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import json
import logging
from datetime import datetime
import pytz

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# -------------------- Event loop fix for Windows --------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -------------------- Logging configuration --------------------
# Reduce noisy logs from underlying libraries
for logger_name in [
    "httpx",
    "telegram.vendor.ptb_urllib3.urllib3",
    "telegram.ext._application",
    "telegram.ext._updater",
    "telegram"
]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------- Configurable paths and IDs --------------------
CHAT_ID = os.getenv("BOT_ALLOWED_CHAT_ID", "320095564")  # chat id allowed (string)
USER_FILE = "user_choices_Macd_2.json"
CONFIG_FILE = "config_Macd_2.json"
SCREENSHOT_FOLDER = os.getenv("SCREENSHOT_FOLDER", r"C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\349E16B7920CFBBD33C6F7D281C20DB6\MQL5\Files\2")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8555301554:AAF75cVIcidE2DHhCw-PDVkGyh3jjky6mrI")

# -------------------- Default config values --------------------
DEFAULT_PAIRS = [
    "AUDUSD", "EURAUD", "EURGBP","EURJPY","EURUSD", "GBPUSD","GBPCHF",
    "USDCAD","USDCHF","USDJPY","XAUUSD", "AUDCAD", "AUDJPY", "NZDJPY" 
]
DEFAULT_TIMEFRAMES = [
    "M1", "M2", "M3", "M4", "M5", "M6",
    "M10", "M12", "M15", "M20", "M30", "H1",
    "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1"
]
DEFAULT_CONFIG = {
    "pairs": DEFAULT_PAIRS,
    "timeframes": DEFAULT_TIMEFRAMES,
    # caption_style can be: "simple", "fancy", "compact", or "custom"
    "caption_style": "simple",
    # if caption_style == "custom", use this template string (placeholders: {pair}, {timeframe}, {signal}, {datetime})
    "custom_caption_template": "📈 {pair} - {timeframe}\n{signal}\n📅 {datetime}"
}

# -------------------- Load or create config.json --------------------
def load_or_create_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        logger.info("🟢 config.json created with default pairs/timeframes.")

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("❌ config.json is invalid. Recreating default config. Error: %s", e)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        data = DEFAULT_CONFIG.copy()

    # Ensure keys exist
    pairs = data.get("pairs", DEFAULT_PAIRS)
    tfs = data.get("timeframes", DEFAULT_TIMEFRAMES)
    caption_style = data.get("caption_style", DEFAULT_CONFIG["caption_style"])
    custom_template = data.get("custom_caption_template", DEFAULT_CONFIG["custom_caption_template"])
    return pairs, tfs, caption_style, custom_template

PAIRS, TIMEFRAMES, CAPTION_STYLE, CUSTOM_CAPTION_TEMPLATE = load_or_create_config()

# -------------------- User choices load/save --------------------
def load_user_choices():
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("user_choices.json unreadable, starting empty. Error: %s", e)
            return {}
    return {}

def save_user_choices(data):
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_choices = load_user_choices()

# -------------------- Sync user_choices with config --------------------
def sync_user_choices_with_config():
    # remove pairs not in config
    removed_pairs = [p for p in list(user_choices.keys()) if p not in PAIRS]
    for p in removed_pairs:
        user_choices.pop(p, None)
        logger.info("Removed pair from user_choices (not in config): %s", p)

    # for each configured pair ensure we don't have timeframes not in config
    for pair in PAIRS:
        pair_data = user_choices.get(pair, {})
        removed_tfs = [tf for tf in list(pair_data.keys()) if tf not in TIMEFRAMES]
        for tf in removed_tfs:
            pair_data.pop(tf, None)
            logger.info("Removed timeframe %s for pair %s from user_choices (not in config).", tf, pair)
        user_choices[pair] = pair_data

    save_user_choices(user_choices)

# run initial sync
sync_user_choices_with_config()

# -------------------- Caption formatting --------------------
def format_caption(pair: str, timeframe: str, signal_code: str) -> str:
    # signal_code: "1" -> Buy, "2" -> Sell
    if signal_code == "1":
        signal_text = "🟢 Buy"
    elif signal_code == "2":
        signal_text = "🔴 Sell"
    else:
        signal_text = "⚪ Unknown"

    now_str = datetime.now(pytz.timezone("Etc/GMT-3")).strftime("%Y.%m.%d %H:%M:%S")

    if CAPTION_STYLE == "simple":
        return f"\n💹 {pair} - {timeframe}\n{signal_text}\n📅 {now_str}"
    elif CAPTION_STYLE == "fancy":
        return (
            "────────────────────\n"
            f"💱 Pair: {pair}\n"
            f"⏱ Timeframe: {timeframe}\n"
            f"📉 Signal: {signal_text}\n"
            f"🕒 Time: {now_str}"
        )
    elif CAPTION_STYLE == "compact":
        return f"{pair} {timeframe} | {signal_text} | {now_str}"
    elif CAPTION_STYLE == "custom":
        # allow placeholders {pair}, {timeframe}, {signal}, {datetime}
        tpl = CUSTOM_CAPTION_TEMPLATE or DEFAULT_CONFIG["custom_caption_template"]
        return tpl.format(pair=pair, timeframe=timeframe, signal=signal_text, datetime=now_str)
    else:
        # fallback to simple
        return f"\n{pair} - {timeframe}\n{signal_text}\n📅 {now_str}"

# -------------------- Bot command handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(CHAT_ID):
        await update.message.reply_text("❌ Access denied.")
        return

    if not PAIRS:
        await update.message.reply_text("❌ No pairs loaded from config.json.")
        return

    sync_user_choices_with_config()
    # keyboard rows of 3 pairs
    keyboard = [PAIRS[i:i+3] for i in range(0, len(PAIRS), 3)]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📊 Please select a pair:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()

    if chat_id != str(CHAT_ID):
        await update.message.reply_text("❌ You are not authorized.")
        return

    if text in PAIRS:
        selected_pair = text
        context.user_data["selected_pair"] = selected_pair

        sync_user_choices_with_config()
        pair_data = user_choices.get(selected_pair, {})
        # create inline buttons for timeframes (4 per row)
        tf_buttons = [
            InlineKeyboardButton(
                f"{'✅' if pair_data.get(tf, False) else '⬜'} {tf}",
                callback_data=f"tf_{selected_pair}_{tf}_toggle"
            )
            for tf in TIMEFRAMES
        ]
        rows = [tf_buttons[i:i+4] for i in range(0, len(tf_buttons), 4)]
        reply_markup = InlineKeyboardMarkup(rows)
        await update.message.reply_text(f"⌚ Select timeframes for {selected_pair}:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("📌 Please select a pair from the menu.")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith("tf_"):
        return

    # data format: tf_{pair}_{tf}_toggle
    try:
        _, pair, tf, _ = data.split("_", 3)
    except ValueError:
        return

    pair_data = user_choices.get(pair, {})
    pair_data[tf] = not pair_data.get(tf, False)
    user_choices[pair] = pair_data
    # sync and save
    sync_user_choices_with_config()

    # update buttons
    tf_buttons = [
        InlineKeyboardButton(
            f"{'✅' if pair_data.get(t, False) else '⬜'} {t}",
            callback_data=f"tf_{pair}_{t}_toggle"
        )
        for t in TIMEFRAMES
    ]
    rows = [tf_buttons[i:i+4] for i in range(0, len(tf_buttons), 4)]
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
# --- بررسی و ارسال تصاویر ---
async def check_and_send_screenshots(app):
    while True:
        try:
            if not os.path.exists(SCREENSHOT_FOLDER):
                await asyncio.sleep(5)
                continue

            files = [f for f in os.listdir(SCREENSHOT_FOLDER) if f.lower().endswith(".png")]

            for file in files:
                file_path = os.path.join(SCREENSHOT_FOLDER, file)
                filename = os.path.splitext(file)[0]
                parts = filename.split("_")

                # انتظار داریم: PAIR_TIMEFRAME_SIGNAL_FILENUM
                if len(parts) != 4:
                    os.remove(file_path)
                    logger.info(f"❌ حذف شد (ساختار اشتباه): {file}")
                    continue

                pair, timeframe, signal_code, file_num = parts

                # حذف اگر جفت ارز یا تایم فریم در config.json نباشه
                if pair not in PAIRS or timeframe not in TIMEFRAMES:
                    os.remove(file_path)
                    logger.info(f"❌ حذف شد (جفت‌ارز/تایم‌فریم نامعتبر): {file}")
                    continue

                # حذف اگر شماره فایل غیر از 2 باشه
                if file_num != "2":
                    os.remove(file_path)
                    logger.info(f"❌ حذف شد (شماره فایل ≠ 2): {file}")
                    continue

                # حذف اگر سیگنال غیر از 1 یا 2 باشه
                if signal_code not in ("1", "2"):
                    os.remove(file_path)
                    logger.info(f"❌ حذف شد (سیگنال نامعتبر): {file}")
                    continue

                # حذف اگر کاربر اون تایم‌فریم رو فعال نکرده
                pair_data = user_choices.get(pair, {})
                if not pair_data.get(timeframe, False):
                    os.remove(file_path)
                    logger.info(f"❌ حذف شد (کاربر {pair}-{timeframe} را فعال نکرده): {file}")
                    continue

                # اگر همه شرایط درست بود -> ارسال
                caption = format_caption(pair, timeframe, signal_code)
                try:
                    with open(file_path, "rb") as photo:
                        await app.bot.send_photo(chat_id=CHAT_ID, photo=photo, caption=caption)
                    logger.info(f"✅ ارسال شد: {file}")
                except Exception as e:
                    logger.error(f"❌ خطا در ارسال {file}: {e}")

                # حذف بعد از ارسال
                try:
                    os.remove(file_path)
                    logger.info(f"🗑️ حذف شد بعد از ارسال: {file}")
                except Exception as e:
                    logger.error(f"❌ خطا در حذف {file}: {e}")

        except Exception as e:
            logger.error(f"❌ خطا در حلقه بررسی: {e}")

        await asyncio.sleep(5)

# -------------------- Main --------------------
def main():
    # re-load config and choices on start
    global PAIRS, TIMEFRAMES, CAPTION_STYLE, CUSTOM_CAPTION_TEMPLATE, user_choices
    PAIRS, TIMEFRAMES, CAPTION_STYLE, CUSTOM_CAPTION_TEMPLATE = load_or_create_config()
    user_choices = load_user_choices()
    sync_user_choices_with_config()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_click))

    loop = asyncio.get_event_loop()
    loop.create_task(check_and_send_screenshots(app))

    logger.info("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()

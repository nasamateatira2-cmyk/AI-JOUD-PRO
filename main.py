import os
import logging
import urllib.parse
import asyncio
import requests
import httpx
from deep_translator import GoogleTranslator
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from groq import Groq

# ---------- الإعدادات والمتغيرات ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-120b"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# استخدام عميل httpx مستقل لتفادي تعارض متغيرات النظام القديمة
client = Groq(
    api_key=GROQ_API_KEY,
    http_client=httpx.Client()
)

# تعليمات النظام لتعريف هوية البوت
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "أنت مساعد ذكاء اصطناعي اسمك AI PRO JOUD. "
        "تم تطويرك وبرمجتك بواسطة أبو الجود. "
        "إذا سألك أحد من أنت أو من طورك، عرّف عن نفسك فوراً بأنك AI PRO JOUD الذي طوّره أبو الجود، "
        "ثم اشرح ميزاتك باختصار: مساعد ذكي للإجابة عن الاستفسارات، المحادثة وحفظ السياق، وتوليد الصور من الوصف النصي. "
        "لا تذكر أبداً أنك ChatGPT أو تابع لـ OpenAI."
    )
}

# ذاكرة بالـ RAM لحفظ سياق المحادثة لكل مستخدم
user_histories: dict[int, list[dict]] = {}
MAX_HISTORY_MESSAGES = 20

WELCOME_MESSAGE = (
    "🌟 أهلاً وسهلاً فيك! 🌟\n\n"
    "أنا بوت ذكاء صناعي AI PRO JOUD جاهز أساعدك وأحكي معك بأي موضوع.\n\n"
    "✨ مميزات البوت:\n"
    "• محادثة ذكية والرد على أسئلتك ورسائلك\n"
    "• توليد صور من وصف نصي مع ترجمة تلقائية\n"
    "• حفظ سياق المحادثة وإمكانية مسحها بأي وقت\n\n"
    "📌 الأوامر المتاحة:\n"
    "• اكتبلي أي رسالة وبرد عليك\n"
    "• /image وصف الصورة — لتوليد صورة\n"
    "• /reset — لمسح المحادثة والبدء من جديد\n\n"
    "— — — — — — — — — —\n"
    "تم تطوير هذا البوت بشكل رسمي بواسطة أبو الجود\n"
    "جميع الحقوق محفوظة © 2026 أبو الجود"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_chat.id] = []
    await update.message.reply_text(WELCOME_MESSAGE)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_chat.id] = []
    await update.message.reply_text("تم مسح المحادثة، بلاش من جديد 🔄")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text

    history = user_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    history = history[-MAX_HISTORY_MESSAGES:]

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        # إرسال تعليمات النظام مع سجل المحادثة دائماً
        messages_to_send = [SYSTEM_PROMPT] + history

        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=1000,
            messages=messages_to_send,
        )
        reply_text = response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        reply_text = "صار في مشكلة تقنية، جرب كمان شوي 🙏"

    history.append({"role": "assistant", "content": reply_text})
    user_histories[chat_id] = history[-MAX_HISTORY_MESSAGES:]

    await update.message.reply_text(reply_text)


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = " ".join(context.args)
    if not user_prompt:
        await update.message.reply_text(
            "اكتب وصف الصورة بعد الأمر، مثلاً:\n/image قطة تلبس نظارة شمس"
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="upload_photo"
    )

    # ترجمة الوصف العربي تلقائياً إلى الإنجليزية عبر Google Translate
    try:
        translated_prompt = GoogleTranslator(source="auto", target="en").translate(user_prompt)
        logger.info(f"Original prompt: {user_prompt} -> Translated: {translated_prompt}")
    except Exception as e:
        logger.error(f"Translation error: {e}")
        translated_prompt = user_prompt

    encoded_prompt = urllib.parse.quote(translated_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

    try:
        resp = requests.get(image_url, timeout=60)
        resp.raise_for_status()
        caption_text = f"🎨 الوصف: {user_prompt}\n🔤 الترجمة: {translated_prompt}"
        await update.message.reply_photo(photo=resp.content, caption=caption_text)
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await update.message.reply_text("ما قدرت أولد الصورة، جرب كمان مرة 🙏")


def main():
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        raise RuntimeError(
            "لازم تحدد TELEGRAM_TOKEN و GROQ_API_KEY كمتغيرات بيئة"
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("image", generate_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 8080))
    external_url = os.environ.get("RENDER_EXTERNAL_URL")

    if external_url:
        logger.info("Bot starting in webhook mode...")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{external_url}/{TELEGRAM_TOKEN}",
        )
    else:
        logger.info("Bot starting in polling mode (local)...")
        app.run_polling()


if __name__ == "__main__":
    main()

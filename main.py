import os
import re
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

# استخدام عميل httpx مستقل لتفادي تعارض متغيرات النظام
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

# الكلمات الدلالية لطلب الصور
IMAGE_KEYWORDS_PATTERN = (
    r"^(صمم لي صورة|صمملي صورة|صمم صورة|صمم لي|صمملي|"
    r"ارسم لي صورة|ارسملي صورة|ارسم صورة|ارسم لي|ارسملي|ارسم|"
    r"انشئ صورة|أنشئ صورة|انشئ لي صورة|أنشئ لي صورة|انشئ لي|أنشئ لي|"
    r"ولد صورة|ولّد صورة|ولد لي صورة|ولّد لي صورة|"
    r"اصنع لي صورة|اصنع صورة|اعملي صورة|اعمل لي صورة|سويلي صورة|ساوي صورة)"
)

WELCOME_MESSAGE = (
    "🌟 أهلاً وسهلاً فيك! 🌟\n\n"
    "أنا بوت ذكاء صناعي AI PRO JOUD جاهز أساعدك وأحكي معك بأي موضوع.\n\n"
    "✨ مميزات البوت:\n"
    "• محادثة ذكية والرد على أسئلتك ورسائلك\n"
    "• توليد صور مباشرة بمجرد كتابة (ارسم لي، صمم لي، انشئ صورة...)\n"
    "• حفظ سياق المحادثة وإمكانية مسحها بأي وقت\n\n"
    "📌 الأوامر المتاحة:\n"
    "• اكتبلي أي رسالة وبرد عليك\n"
    "• ارسم لي قطة تلبس نظارة — لتوليد صورة تلقائياً\n"
    "• /image وصف الصورة — الطريقة التقليدية لتوليد الصور\n"
    "• /reset — لمسح المحادثة والبدء من جديد\n\n"
    "— — — — — — — — — —\n"
    "تم تطوير هذا البوت بشكل رسمي بواسطة أبو الجود\n"
    "جميع الحقوق محفوظة © 2026 أبو الجود"
)


async def send_generated_image(chat_id: int, prompt_text: str, context: ContextTypes.DEFAULT_TYPE):
    """دالة مساعدة لمعالجة توليد الصورة وإرسالها"""
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")

    try:
        translated_prompt = GoogleTranslator(source="auto", target="en").translate(prompt_text)
        logger.info(f"Original: {prompt_text} -> Translated: {translated_prompt}")
    except Exception as e:
        logger.error(f"Translation error: {e}")
        translated_prompt = prompt_text

    encoded_prompt = urllib.parse.quote(translated_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

    try:
        resp = requests.get(image_url, timeout=60)
        resp.raise_for_status()
        caption_text = f"🎨 الوصف: {prompt_text}\n🔤 الترجمة: {translated_prompt}"
        await context.bot.send_photo(chat_id=chat_id, photo=resp.content, caption=caption_text)
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="ما قدرت أولد الصورة، جرب كمان مرة 🙏")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_chat.id] = []
    await update.message.reply_text(WELCOME_MESSAGE)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_chat.id] = []
    await update.message.reply_text("تم مسح المحادثة، بلاش من جديد 🔄")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()

    # فحص ما إذا كانت الرسالة تبدأ بكلمات طلب تصميم أو رسم صورة
    match = re.match(IMAGE_KEYWORDS_PATTERN, user_text, re.IGNORECASE)
    if match:
        extracted_prompt = user_text[match.end():].strip(" :,-")
        if extracted_prompt:
            await send_generated_image(chat_id, extracted_prompt, context)
            return
        else:
            await update.message.reply_text("حدد وصف الصورة بعد طلبك، مثلاً:\nارسم لي قطة في الفضاء")
            return

    # إذا لم تكن طلباً لتوليد صورة، تكمل المحادثة الذكية عبر Groq
    history = user_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    history = history[-MAX_HISTORY_MESSAGES:]

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
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

    await send_generated_image(update.effective_chat.id, user_prompt, context)


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

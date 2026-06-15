"""
Telegram Content Manager Bot v6.0
- Всё из v5.0 +
- 🤖 ИИ-генерация вакансий через OpenRouter
- Настройки вакансий (зарплата, график, тип)
- Предпросмотр перед публикацией
- Кнопки-ссылки для анкет (удалёнка и курьер)
"""

import asyncio
import html as html_module
import logging
import os
import json
import uuid
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN", "")
ADMIN_ID         = int(os.getenv("ADMIN_ID", "0"))
TARGET_CHANNEL   = os.getenv("TARGET_CHANNEL", "")
OPENROUTER_KEY   = os.getenv("OPENROUTER_KEY", "")
POSTS_FILE       = "posts.json"
VACANCY_CFG_FILE = "vacancy_config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Состояния ────────────────────────────────────────────────────────────────
(
    WAIT_TEXT, WAIT_MEDIA,
    WAIT_BUTTONS,
    WAIT_SCHEDULE, WAIT_DATE, WAIT_TIME, WAIT_REPEAT,
    WAIT_EDIT_TEXT, WAIT_EDIT_DATE,
    # ИИ-вакансии
    AI_WAIT_SALARY_MIN, AI_WAIT_SALARY_MAX,
    AI_WAIT_SCHEDULE_INFO, AI_WAIT_OFFER, AI_WAIT_REQUIREMENTS,
    AI_WAIT_EXTRA, AI_WAIT_PREVIEW_ACTION, AI_WAIT_EDIT_TEXT,
) = range(17)


# ── Конфиг вакансий ───────────────────────────────────────────────────────────

DEFAULT_VACANCY_CONFIG = {
    "remote": {
        "schedule": "Гибкий график, пн-пт или по договорённости",
        "company_info": "7 лет на рынке труда. Более 3 500 сотрудников по всей России. Официальное трудоустройство или самозанятость.",
        "salary_variants": [
            {"label": "от 35 000 ₽", "hours": "6 часов в день", "min": 35000},
            {"label": "от 50 000 ₽", "hours": "6 часов в день", "min": 50000},
            {"label": "от 70 000 ₽", "hours": "8 часов в день", "min": 70000},
        ],
        "offer": [
            "Полностью удалённая работа — из дома, кафе или любой точки мира",
            "Официальное оформление или договор с самозанятым",
            "Обучение с нуля — наставник на весь испытательный срок",
            "Еженедельные выплаты без задержек",
            "Карьерный рост: от специалиста до тимлида за 3-6 месяцев",
            "Корпоративная техника и ПО за счёт компании",
        ],
        "requirements": [
            "Возраст от 18 лет",
            "Смартфон или ноутбук со стабильным интернетом",
            "Грамотная письменная речь",
            "Ответственность и соблюдение дедлайнов",
            "Опыт не требуется — всему обучим",
        ],
        "links": [
            {"url": "http://work.job-voxys.ru/click?pid=318&offer_id=38", "label": "Voxys", "photo_dir": "photos/remote_voxys"},
            {"url": "https://clck.ru/3RghW9", "label": "Alt", "photo_dir": "photos/remote_alt"},
        ],
    },
    "courier": {
        "schedule": "Сменный график: 5/2, 2/2 или частичная занятость — на выбор",
        "company_info": "Один из крупнейших сервисов доставки России. Работаем в 50+ городах. Более 10 000 курьеров в команде.",
        "salary_variants": [
            {"label": "от 50 000 ₽", "hours": "неполный день", "min": 50000},
            {"label": "от 70 000 ₽", "hours": "полный день", "min": 70000},
            {"label": "от 90 000 ₽", "hours": "полный день + активные смены", "min": 90000},
        ],
        "offer": [
            "Официальное трудоустройство с первого дня",
            "Ежедневные или еженедельные выплаты — как удобно",
            "Бесплатная фирменная форма и термосумка",
            "Бонусы за выполнение плана и активные смены",
            "Возможность совмещения с учёбой",
            "Дружный коллектив и поддержка на старте",
        ],
        "requirements": [
            "Возраст от 18 лет",
            "Гражданство РФ или разрешение на работу",
            "Смартфон с доступом в интернет",
            "Физическая активность — заказы пешком, на велосипеде или авто",
            "Ответственность и пунктуальность",
        ],
        "links": [
            {"url": "http://work.eda-job-yandex.ru/EcPtoa", "label": "Яндекс.Еда", "photo_dir": "photos/courier_yandex"},
            {"url": "http://work.jobs-samokat.ru/click?pid=4161&offer_id=133", "label": "Самокат", "photo_dir": "photos/courier_samokat"},
        ],
    },
}
def load_vacancy_config() -> dict:
    try:
        with open(VACANCY_CFG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_VACANCY_CONFIG.copy()

def save_vacancy_config(cfg: dict):
    with open(VACANCY_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── Хранилище постов ──────────────────────────────────────────────────────────

def load_posts() -> list:
    try:
        with open(POSTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_posts(posts: list):
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

def get_post(post_id: str):
    return next((p for p in load_posts() if p["id"] == post_id), None)

def update_post(post_id: str, data: dict):
    posts = load_posts()
    for i, p in enumerate(posts):
        if p["id"] == post_id:
            posts[i].update(data)
    save_posts(posts)

def delete_post_by_id(post_id: str):
    save_posts([p for p in load_posts() if p["id"] != post_id])

def new_id() -> str:
    return str(uuid.uuid4())[:8]


# ── Проверка доступа ──────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == ADMIN_ID


# ── Главное меню ──────────────────────────────────────────────────────────────

def main_reply_kb():
    return ReplyKeyboardMarkup([
        ["✏️ Создать пост", "🤖 Сгенерировать пост"],
        ["📝 Мои посты", "⚙️ Настройки"],
        ["❓ Помощь"]
    ], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ Нет доступа.")
        return
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Я бот для управления постами в канале.\n\n"
        "📢 Канал: " + TARGET_CHANNEL + "\n\n"
        "🤖 Новинка: ИИ-генерация вакансий через OpenRouter!\n\n"
        "Выбери действие:",
        reply_markup=main_reply_kb()
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    context.user_data.clear()
    await update.message.reply_text("📌 Главное меню:", reply_markup=main_reply_kb())

async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    # Удаляем сообщение с inline-кнопками и присылаем новое с reply-клавиатурой
    try:
        await query.message.delete()
    except Exception:
        pass
    await context.bot.send_message(query.message.chat_id, "📌 Главное меню:", reply_markup=main_reply_kb())
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
#  🤖 ИИ-ВАКАНСИИ
# ══════════════════════════════════════════════════════════════════════════════

async def ai_vacancy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора типа ИИ-вакансии."""
    query = update.callback_query
    if query:
        await query.answer()
        send = query.edit_message_text
    else:
        send = update.message.reply_text

    await send(
        "🤖 *ИИ-генерация вакансии*\n\n"
        "Выбери тип вакансии — ИИ напишет текст, ты его одобришь перед публикацией:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Удалённая работа",     callback_data="ai_gen_remote")],
            [InlineKeyboardButton("🚴 Курьер / Доставщик",   callback_data="ai_gen_courier")],
            [InlineKeyboardButton("⚡ Быстрая генерация",     callback_data="ai_gen_quick_remote")],
            [InlineKeyboardButton("← Назад",                  callback_data="back_menu")],
        ])
    )

async def ai_gen_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Быстрая генерация — случайный тип вакансии."""
    import random as _rq
    query = update.callback_query
    await query.answer()
    cfg = load_vacancy_config()
    vac_type = _rq.choice(["remote", "courier"])
    context.user_data["ai_vac"] = {
        "type": vac_type,
        **cfg.get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    }
    await query.edit_message_text("⏳ Генерирую вакансию, подожди...")
    await _do_generate(query.message, context, edit=True)


async def ai_gen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало генерации — выбран конкретный тип (удалёнка или курьер)."""
    query = update.callback_query
    await query.answer()
    data = query.data  # ai_gen_remote / ai_gen_courier

    vac_type = "remote" if data == "ai_gen_remote" else "courier"
    cfg = load_vacancy_config()
    vac_cfg = cfg.get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    context.user_data["ai_vac"] = {"type": vac_type, **vac_cfg}

    await query.edit_message_text("⏳ Генерирую вакансию, подожди секунду...")
    await _do_generate(query.message, context, edit=True)

async def ai_got_salary_min(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "").replace(",", "")
    try:
        context.user_data["ai_vac"]["salary_min"] = int(text)
    except ValueError:
        await update.message.reply_text("❌ Введи число, например `60000`", parse_mode=ParseMode.MARKDOWN)
        return AI_WAIT_SALARY_MIN
    await _ask_salary_max(update.message, context)
    return AI_WAIT_SALARY_MAX

async def ai_skip_salary_min(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _ask_salary_max(query.message, context, edit=True)
    return AI_WAIT_SALARY_MAX

async def _ask_salary_max(msg, context, edit=False):
    cur = context.user_data["ai_vac"].get("salary_max", 110000)
    text = (
        f"💰 *Максимальная зарплата*\n\n"
        f"Текущее значение: `{cur:,} ₽`\n\n"
        "Введи новое значение или нажми «Оставить»:"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Оставить {cur:,} ₽", callback_data="ai_skip_salary_max")]])
    if edit:
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def ai_got_salary_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "").replace(",", "")
    try:
        context.user_data["ai_vac"]["salary_max"] = int(text)
    except ValueError:
        await update.message.reply_text("❌ Введи число, например `110000`", parse_mode=ParseMode.MARKDOWN)
        return AI_WAIT_SALARY_MAX
    await _ask_schedule(update.message, context)
    return AI_WAIT_SCHEDULE_INFO

async def ai_skip_salary_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _ask_schedule(query.message, context, edit=True)
    return AI_WAIT_SCHEDULE_INFO

async def _ask_schedule(msg, context, edit=False):
    cur = context.user_data["ai_vac"].get("schedule", "")
    text = (
        f"🕐 *График работы*\n\n"
        f"Текущий: `{cur}`\n\n"
        "Введи описание графика или нажми «Оставить»:"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Оставить текущий", callback_data="ai_skip_schedule")]])
    if edit:
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def ai_got_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ai_vac"]["schedule"] = update.message.text.strip()
    await _ask_generate(update.message, context)
    return AI_WAIT_EXTRA

async def ai_skip_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _ask_generate(query.message, context, edit=True)
    return AI_WAIT_EXTRA

async def _ask_generate(msg, context, edit=False):
    text = (
        "✍️ *Дополнительные пожелания*\n\n"
        "Напиши что-то особенное для этой вакансии или нажми «Генерировать сейчас»:\n\n"
        "Например: _Сделай акцент на быстром старте_ или _Упомяни бонусы за KPI_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Генерировать сейчас", callback_data="ai_generate_now")]])
    if edit:
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def ai_got_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ai_vac"]["extra"] = update.message.text.strip()
    await update.message.reply_text("⏳ Генерирую вакансию, подожди секунду...")
    await _do_generate(update.message, context)
    return ConversationHandler.END

async def ai_generate_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Генерирую вакансию, подожди секунду...")
    await _do_generate(query.message, context, edit=True)
    return ConversationHandler.END


async def _do_generate(msg, context: ContextTypes.DEFAULT_TYPE, edit=False):
    """Вызов OpenRouter API и показ предпросмотра."""
    vac = context.user_data.get("ai_vac", {})
    vac_type = vac.get("type", "remote")
    type_label = "удалённую работу" if vac_type == "remote" else "курьера/доставщика"

    offer_list = "\n".join(f"- {o}" for o in vac.get("offer", []))
    req_list   = "\n".join(f"- {r}" for r in vac.get("requirements", []))
    extra      = vac.get("extra", "")

    company_info = vac.get("company_info", "")

    # Случайный вариант зарплаты
    import random as _random
    salary_variants = vac.get("salary_variants", [{"label": "от 60 000 ₽", "hours": "полный день", "min": 60000}])
    chosen_salary = _random.choice(salary_variants)
    context.user_data["ai_chosen_salary"] = chosen_salary

    # Случайная ссылка
    links = vac.get("links", [])
    chosen_link = _random.choice(links) if links else {"url": "", "label": "", "photo_dir": ""}
    context.user_data["ai_chosen_link"] = chosen_link

    # Фото из папки выбранной ссылки
    import pathlib as _pl
    photo_path = None
    _pdir = chosen_link.get("photo_dir", "")
    if _pdir:
        _pd = _pl.Path(_pdir)
        if _pd.exists():
            _pfiles = [f for f in _pd.iterdir() if f.suffix.lower() in (".jpg",".jpeg",".png",".webp")]
            if _pfiles:
                photo_path = str(_random.choice(_pfiles))
    context.user_data["ai_photo_path"] = photo_path
    log.info(f"📸 Выбрано фото: {photo_path or 'нет'} (папка: {_pdir})")

    prompt = f"""Напиши реалистичный текст вакансии для Telegram-канала в стиле hh.ru и SuperJob. Тип: {type_label}.

ВАЖНЫЕ ПРАВИЛА:
- Используй HTML-теги: <b>жирный</b>, <i>курсив</i>
- Эмодзи в начале каждого раздела
- Название должно быть РЕАЛЬНЫМ и конкретным, как на hh.ru.
  Примеры для удалёнки: "Оператор колл-центра (удалённо)", "Менеджер по работе с клиентами / удалённо", "Специалист поддержки (home office)", "Контент-менеджер на удалёнку", "Оператор чата / дистанционно".
  Примеры для курьера: "Курьер-доставщик (пеший/вело)", "Водитель-курьер / доставка еды", "Курьер на личном авто — ежедневные выплаты", "Пеший курьер в службу доставки".
  НЕ ПРИДУМЫВАЙ фантазийных названий типа "Волшебник", "Герой", "Мечта" и т.п.
- Каждый раз пиши УНИКАЛЬНЫЙ текст — меняй формулировки, порядок акцентов, стиль призыва
- Смысл и факты остаются теми же, но слова, структура предложений и тон должны быть разными
- Варьируй: длину предложений, эмодзи (но не меняй сами разделы), порядок пунктов в списках
- Текст должен звучать как реальная вакансия от HR-отдела, не как реклама
- Пиши конкретно, без воды

Параметры вакансии:
- Зарплата: {chosen_salary["label"]} ({chosen_salary["hours"]})
- График: {vac.get("schedule", "гибкий")}
- О компании: {company_info}
- Что мы предлагаем:
{offer_list}
- Требования:
{req_list}
{"- Дополнительно: " + extra if extra else ""}

Структура поста (строго соблюдай):
1. <b>Название должности</b> — жирный заголовок с эмодзи, конкретное и реальное
2. 🏢 <b>О компании</b> — 1-2 предложения (используй данные из "О компании" выше)
3. 💰 <b>Зарплата</b> — точно как в параметрах: {chosen_salary["label"]} за {chosen_salary["hours"]}. Не добавляй слова "на руки" — только то что указано.
4. 🕐 <b>График работы</b>
5. ✅ <b>Мы предлагаем</b> — список через дефис
6. 📋 <b>Требования</b> — список через дефис
7. 📩 Короткий уникальный призыв откликнуться (без ссылок — кнопка будет отдельно)

Пиши только текст поста, никаких пояснений."""

    try:
        generated_text = await call_openrouter(prompt)
    except Exception as e:
        log.error(f"OpenRouter error: {e}")
        generated_text = None

    if not generated_text:
        err_text = (
            "❌ Ошибка генерации.\n\n"
            "Проверь OPENROUTER_KEY в .env файле.\n\n"
            "Убедись что ключ правильный и есть баланс на аккаунте openrouter.ai"
        )
        if edit:
            await msg.edit_text(err_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Меню", callback_data="back_menu")]]))
        else:
            await msg.reply_text(err_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Меню", callback_data="back_menu")]]))
        return

    # Сохраняем сгенерированный текст
    context.user_data["ai_generated_text"] = generated_text
    context.user_data["ai_vac_type"] = vac_type

    # Показываем предпросмотр
    preview = generated_text[:800] + ("..." if len(generated_text) > 800 else "")
    preview_msg = (
        "✅ <b>Вакансия готова! Предпросмотр:</b>\n\n"
        + preview
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Опубликовать сейчас",        callback_data="ai_pub_now")],
        [InlineKeyboardButton("📅 Запланировать",              callback_data="ai_pub_schedule")],
        [InlineKeyboardButton("✏️ Редактировать текст",        callback_data="ai_edit_text")],
        [InlineKeyboardButton("🔄 Перегенерировать",           callback_data="ai_regenerate")],
        [InlineKeyboardButton("← Отмена",                      callback_data="back_menu")],
    ])

    if edit:
        await msg.edit_text(preview_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await msg.reply_text(preview_msg, parse_mode=ParseMode.HTML, reply_markup=kb)


async def call_openrouter(prompt: str) -> str | None:
    """Вызов OpenRouter API."""
    if not OPENROUTER_KEY:
        log.error("OPENROUTER_KEY не задан!")
        return None

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/kdrupro",
        "X-Title": "Vacancy Bot",
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1200,
        "temperature": 0.8,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.error(f"OpenRouter HTTP {resp.status}: {body[:300]}")
                return None
            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()


async def ai_pub_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Публикация ИИ-вакансии сразу."""
    query = update.callback_query
    await query.answer()

    vac_type    = context.user_data.get("ai_vac_type", "remote")
    text        = context.user_data.get("ai_generated_text", "")
    cfg         = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    chosen_link = context.user_data.get("ai_chosen_link", None)
    photo_path  = context.user_data.get("ai_photo_path", None)

    # Загружаем фото
    photo_file_id = await _upload_photo(context.bot, photo_path) if photo_path else None

    # Формируем кнопку из случайно выбранной ссылки
    buttons = _make_vacancy_buttons(vac_type, cfg, chosen_link)

    post = {
        "id"         : new_id(),
        "text"       : text,
        "photo"      : photo_file_id,
        "video"      : None,
        "buttons"    : buttons,
        "publish_at" : "сейчас",
        "status"     : "publishing",
        "created_at" : datetime.now().strftime("%d.%m.%Y %H:%M"),
        "source"     : "ai",
    }
    posts = load_posts()
    posts.append(post)
    save_posts(posts)

    ok = await send_post_to_channel(context.bot, post)
    update_post(post["id"], {"status": "published" if ok else "failed"})

    result = "✅ Вакансия опубликована в канале!" if ok else "❌ Ошибка при публикации."
    try:
        await query.message.delete()
    except:
        pass
    await context.bot.send_message(query.message.chat_id, result, reply_markup=main_reply_kb())
    context.user_data.clear()


async def ai_pub_schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запланировать публикацию ИИ-вакансии."""
    query = update.callback_query
    await query.answer()
    context.user_data["scheduling_ai"] = True
    await query.edit_message_text(
        "⏰ *Когда опубликовать вакансию?*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=schedule_picker_kb()
    )


async def ai_scheduled_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор времени публикации для ИИ-вакансии."""
    query = update.callback_query
    await query.answer()

    if not context.user_data.get("scheduling_ai"):
        return  # Не наш обработчик

    vac_type    = context.user_data.get("ai_vac_type", "remote")
    text        = context.user_data.get("ai_generated_text", "")
    cfg         = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    chosen_link = context.user_data.get("ai_chosen_link", None)
    buttons     = _make_vacancy_buttons(vac_type, cfg, chosen_link)

    dt_str = query.data.replace("sched_", "")
    if dt_str == "сейчас":
        dt_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    post = {
        "id"         : new_id(),
        "text"       : text,
        "photo"      : None,
        "video"      : None,
        "buttons"    : buttons,
        "publish_at" : dt_str,
        "status"     : "pending",
        "created_at" : datetime.now().strftime("%d.%m.%Y %H:%M"),
        "source"     : "ai",
    }
    posts = load_posts()
    posts.append(post)
    save_posts(posts)

    await query.edit_message_text(
        f"✅ Вакансия запланирована!\n📅 Дата: `{dt_str}`\n🆔 ID: `{post['id']}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_reply_kb()
    )
    context.user_data.clear()


async def ai_regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перегенерация вакансии."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Генерирую новый вариант...")
    await _do_generate(query.message, context, edit=True)


async def ai_edit_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало редактирования текста ИИ-вакансии."""
    query = update.callback_query
    await query.answer()
    current = context.user_data.get("ai_generated_text", "")
    preview = current[:300] + ("..." if len(current) > 300 else "")
    await query.edit_message_text(
        "✏️ <b>Редактирование вакансии</b>\n\n"
        f"Текущий текст (начало):\n<i>{preview}</i>\n\n"
        "Отправь новый текст вакансии целиком:",
        parse_mode=ParseMode.HTML
    )
    return AI_WAIT_EDIT_TEXT


async def ai_edit_text_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение отредактированного текста."""
    context.user_data["ai_generated_text"] = update.message.text
    preview = update.message.text[:800] + ("..." if len(update.message.text) > 800 else "")
    await update.message.reply_text(
        "✅ <b>Текст обновлён! Предпросмотр:</b>\n\n" + preview,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Опубликовать сейчас",  callback_data="ai_pub_now")],
            [InlineKeyboardButton("📅 Запланировать",        callback_data="ai_pub_schedule")],
            [InlineKeyboardButton("✏️ Редактировать ещё",   callback_data="ai_edit_text")],
            [InlineKeyboardButton("🔄 Перегенерировать",     callback_data="ai_regenerate")],
            [InlineKeyboardButton("← Отмена",               callback_data="back_menu")],
        ])
    )
    return ConversationHandler.END
HR_BUTTON = {"text": "💬 Написать HR-менеджеру", "url": "https://t.me/HRKris_1"}

def _make_vacancy_buttons(vac_type: str, cfg: dict, chosen_link: dict = None) -> list:
    """Кнопка 1 — случайная ссылка на вакансию. Кнопка 2 — HR всегда одна и та же."""
    label = "📝 Откликнуться" if vac_type == "remote" else "🚴 Откликнуться"

    # Используем уже выбранную при генерации ссылку
    if chosen_link and chosen_link.get("url"):
        url = chosen_link["url"]
    else:
        links = cfg.get("links", [])
        url = links[0]["url"] if links else ""

    buttons = []
    if url:
        buttons.append([{"text": label, "url": url}])
    buttons.append([{"text": HR_BUTTON["text"], "url": HR_BUTTON["url"]}])
    return buttons



# ── Помощь ────────────────────────────────────────────────────────────────────

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        send = query.edit_message_text
    else:
        send = update.message.reply_text
    text = (
        "❓ *Помощь по боту*\n\n"
        "1. Создай пост (текст + медиа + кнопки).\n"
        "2. Выбери время: прямо сейчас или отложи.\n"
        "3. Бот опубликует всё сам!\n\n"
        "🔗 *Кнопки:* формат `Текст - ссылка`.\n"
        "Можно использовать цвета: `!b`, `!g`, `!r`."
    )
    await send(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]]))


# ── Создание поста ────────────────────────────────────────────────────────────

async def create_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        send = query.edit_message_text
    else:
        send = update.message.reply_text
    context.user_data["new_post"] = {"id": new_id(), "status": "pending"}
    await send(
        "📝 *Создание поста*\n\nПришли текст поста (или нажми /menu для отмены).",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAIT_TEXT

async def got_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text or ""
    if txt not in ("/skip", ""):
        context.user_data["new_post"]["text"] = txt
    await update.message.reply_text(
        "🖼 Прикрепи фото или видео.\n"
        "Или нажми /skip — без медиа.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏩ Пропустить медиа", callback_data="media_skip")],
            [InlineKeyboardButton("← Отмена", callback_data="back_menu")]
        ])
    )
    return WAIT_MEDIA

async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("⏩ Медиа пропущено.")
        await send_button_menu_chat(update.callback_query.message.chat_id, context, update.callback_query.get_bot())
    else:
        await send_button_menu(update.message, context)
    return WAIT_BUTTONS

async def got_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data["new_post"]["photo"] = update.message.photo[-1].file_id
    elif update.message.video:
        context.user_data["new_post"]["video"] = update.message.video.file_id
    await send_button_menu(update.message, context)
    return WAIT_BUTTONS

async def send_button_menu_chat(chat_id, context, bot):
    preview = _btn_preview(context)
    hint = (
        "🔘 *Кнопки поста:*\n"
        f"`{preview}`\n\n"
        "Отправь кнопки в формате:\n"
        "`Текст - https://ссылка`\n"
        "В ряд через `|`:\n"
        "`Кнопка 1 - https://url | Кнопка 2 - https://url`\n\n"
        "Цвет (добавь в начало):\n"
        "`!r` 🔴  `!g` 🟢  `!b` 🔵  `!y` 🟡\n"
        "`!o` 🟠  `!p` 🟣  `!w` ⚪  `!k` ⚫\n\n"
        "*Пример:*\n"
        "`!g Записаться - https://t.me/you`"
    )
    await bot.send_message(chat_id, hint, parse_mode=ParseMode.MARKDOWN, reply_markup=button_menu_kb())


# ── Построитель кнопок ────────────────────────────────────────────────────────

# Маппинг префиксов на стили Telegram API 9.4
COLOR_MAP = {
    "!r": {"emoji": "🔴", "style": "danger"},
    "!g": {"emoji": "🟢", "style": "success"},
    "!b": {"emoji": "🔵", "style": "primary"},
    "!y": {"emoji": "🟡", "style": None},
    "!o": {"emoji": "🟠", "style": None},
    "!p": {"emoji": "🟣", "style": None},
    "!w": {"emoji": "⚪", "style": None},
    "!k": {"emoji": "⚫", "style": None},
}

def parse_buttons(raw: str) -> list:
    result = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row = []
        cells = [c.strip() for c in line.split("|")]
        for cell in cells:
            cell = cell.strip()
            style = None
            color_emoji = ""
            for prefix, info in COLOR_MAP.items():
                if cell.lower().startswith(prefix + " "):
                    # Для цветных кнопок (!r !g !b) — без эмодзи, цвет передаётся через style
                    color_emoji = "" if info["style"] else info["emoji"] + " "
                    style = info["style"]
                    cell = cell[len(prefix)+1:].strip()
                    break
            if " - " in cell:
                parts = cell.rsplit(" - ", 1)
                text = parts[0].strip()
                url  = parts[1].strip()
                if url.startswith("http"):
                    btn = {"text": f"{color_emoji}{text}", "url": url}
                    if style:
                        btn["style"] = style
                    row.append(btn)
        if row:
            result.append(row)
    return result

def _btn_preview(context: ContextTypes.DEFAULT_TYPE) -> str:
    btns = context.user_data.get("new_post", {}).get("buttons", [])
    if not btns:
        return "  (ещё нет кнопок)"
    rows = []
    for row in btns:
        rows.append("  " + "  |  ".join(f"[{b.get('text','?')}]" for b in row))
    return "\n".join(rows)

def button_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Готово — выбрать время", callback_data="btn_done")],
        [InlineKeyboardButton("🗑 Очистить кнопки",        callback_data="btn_clear")],
        [InlineKeyboardButton("⏩ Без кнопок",             callback_data="btn_done")],
        [InlineKeyboardButton("← Отмена",                  callback_data="back_menu")],
    ])

async def send_button_menu(message, context: ContextTypes.DEFAULT_TYPE):
    preview = _btn_preview(context)
    hint = (
        "🔘 *Кнопки поста:*\n"
        f"`{preview}`\n\n"
        "Отправь кнопки в формате:\n"
        "`Текст - https://ссылка`\n"
        "В ряд через `|`\n\n"
        "Цвет кнопки (реальный цвет в Telegram):\n"
        "`!b` 🔵 Синяя  `!g` 🟢 Зелёная  `!r` 🔴 Красная\n"
        "Остальные цвета (только эмодзи):\n"
        "`!y` 🟡  `!o` 🟠  `!p` 🟣  `!w` ⚪  `!k` ⚫"
    )
    await message.reply_text(hint, parse_mode=ParseMode.MARKDOWN, reply_markup=button_menu_kb())

async def edit_button_menu_q(query, context: ContextTypes.DEFAULT_TYPE):
    preview = _btn_preview(context)
    hint = (
        "🔘 *Текущие кнопки:*\n"
        f"`{preview}`\n\n"
        "Отправь новые кнопки или нажми «Готово»."
    )
    await query.edit_message_text(hint, parse_mode=ParseMode.MARKDOWN, reply_markup=button_menu_kb())

async def got_buttons_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = parse_buttons(update.message.text)
    if not rows:
        await update.message.reply_text(
            "❌ Не удалось распознать кнопки.\n\nФормат: `Текст - https://ссылка`",
            parse_mode=ParseMode.MARKDOWN
        )
        return WAIT_BUTTONS
    context.user_data["new_post"].setdefault("buttons", []).extend(rows)
    await send_button_menu(update.message, context)
    return WAIT_BUTTONS

async def buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "btn_done":
        await query.edit_message_text(
            "⏰ *Когда опубликовать пост?*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=schedule_picker_kb()
        )
        return WAIT_SCHEDULE
    if query.data == "btn_clear":
        context.user_data["new_post"]["buttons"] = []
        await edit_button_menu_q(query, context)
        return WAIT_BUTTONS
    return WAIT_BUTTONS


# ── Планировщик ───────────────────────────────────────────────────────────────

def schedule_picker_kb():
    now = datetime.now()
    def fmt(dt): return dt.strftime("%d.%m.%Y %H:%M")
    today_eve  = now.replace(hour=20, minute=0, second=0, microsecond=0)
    tomor_morn = (now + timedelta(days=1)).replace(hour=9,  minute=0, second=0, microsecond=0)
    tomor_eve  = (now + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    in_week    = (now + timedelta(days=7)).replace(hour=10, minute=0, second=0, microsecond=0)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Прямо сейчас",                                       callback_data="sched_now")],
        [InlineKeyboardButton(f"🌆 Сегодня вечером  {today_eve.strftime('%H:%M')}",    callback_data=f"sched_{fmt(today_eve)}")],
        [InlineKeyboardButton(f"🌅 Завтра утром  {tomor_morn.strftime('%H:%M')}",      callback_data=f"sched_{fmt(tomor_morn)}")],
        [InlineKeyboardButton(f"🌃 Завтра вечером  {tomor_eve.strftime('%H:%M')}",     callback_data=f"sched_{fmt(tomor_eve)}")],
        [InlineKeyboardButton(f"📅 Через неделю  {in_week.strftime('%d.%m')}",         callback_data=f"sched_{fmt(in_week)}")],
        [InlineKeyboardButton("🗓 Выбрать дату вручную",                               callback_data="sched_custom")],
        [InlineKeyboardButton("← Отмена",                                              callback_data="back_menu")],
    ])

async def got_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "sched_now":
        context.user_data["new_post"]["publish_at"] = "сейчас"
        await finish_post_query(query, context)
        return ConversationHandler.END

    if query.data == "sched_custom":
        await query.edit_message_text(
            "📅 Напиши дату публикации:\nФормат: `ДД.ММ.ГГГГ`\nПример: `25.03.2026`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Отмена", callback_data="back_menu")]])
        )
        return WAIT_DATE

    dt_str = query.data.replace("sched_", "")
    context.user_data["new_post"]["publish_at"] = dt_str
    await query.edit_message_text(
        f"✅ Время выбрано: `{dt_str}`\n\n"
        "🔁 *Автоповтор?*\nНапиши через сколько дней повторять (например `7`).\n"
        "Или нажми «Без повтора».",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏩ Без повтора", callback_data="repeat_skip")]
        ])
    )
    return WAIT_REPEAT

async def got_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%d.%m.%Y")
        context.user_data["new_post"]["date"] = text
        await update.message.reply_text(
            "🕐 Напиши время публикации:\nФормат: `ЧЧ:ММ`\nПример: `20:00`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Отмена", callback_data="back_menu")]])
        )
        return WAIT_TIME
    except ValueError:
        await update.message.reply_text("❌ Неверный формат.\nПример: `25.03.2026`", parse_mode=ParseMode.MARKDOWN)
        return WAIT_DATE

async def got_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
        np = context.user_data["new_post"]
        np["publish_at"] = f"{np.pop('date')} {text}"
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Пример: `20:00`", parse_mode=ParseMode.MARKDOWN)
        return WAIT_TIME
    await update.message.reply_text(
        f"✅ Время: `{context.user_data['new_post']['publish_at']}`\n\n"
        "🔁 *Автоповтор?* Напиши через сколько дней (например `7`).\nИли напиши /skip.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Отмена", callback_data="back_menu")]])
    )
    return WAIT_REPEAT

async def got_repeat_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip":
        try:
            context.user_data["new_post"]["repeat_days"] = int(text)
        except ValueError:
            await update.message.reply_text("❌ Напиши число дней или /skip")
            return WAIT_REPEAT
    await finish_post(update, context)
    return ConversationHandler.END

async def got_repeat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "repeat_skip":
        await finish_post_query(query, context)
        return ConversationHandler.END
    return WAIT_REPEAT


# ── Сохранение и публикация ───────────────────────────────────────────────────

def _build_post(np: dict) -> dict:
    publish_at = np.get("publish_at", "сейчас")
    return {
        "id"         : np.get("id", new_id()),
        "text"       : np.get("text", ""),
        "photo"      : np.get("photo"),
        "video"      : np.get("video"),
        "buttons"    : np.get("buttons", []),
        "publish_at" : publish_at,
        "repeat_days": np.get("repeat_days"),
        "status"     : "pending" if publish_at != "сейчас" else "publishing",
        "created_at" : datetime.now().strftime("%d.%m.%Y %H:%M"),
    }

def _append_post(post: dict):
    posts = load_posts()
    posts.append(post)
    save_posts(posts)

def _post_saved_msg(post: dict) -> str:
    if post["status"] == "publishing":
        return "✅ Пост отправлен прямо сейчас!"
    repeat_txt = f"каждые {post['repeat_days']} дней" if post.get("repeat_days") else "нет"
    btn_count  = f"\n🔘 Кнопок: {len(post['buttons'])}" if post.get("buttons") else ""
    return (
        f"✅ *Пост запланирован!*\n\n"
        f"📅 Дата: `{post['publish_at']}`\n"
        f"🔁 Автоповтор: {repeat_txt}{btn_count}\n"
        f"🆔 ID: `{post['id']}`"
    )

async def finish_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    np   = context.user_data.get("new_post", {})
    post = _build_post(np)
    _append_post(post)
    await update.message.reply_text(
        _post_saved_msg(post),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_reply_kb()
    )
    if post["status"] == "publishing":
        ok = await send_post_to_channel(context.bot, post)
        update_post(post["id"], {"status": "published" if ok else "failed"})
    context.user_data.clear()

async def finish_post_query(query, context: ContextTypes.DEFAULT_TYPE):
    np   = context.user_data.get("new_post", {})
    post = _build_post(np)
    _append_post(post)
    await query.edit_message_text(
        _post_saved_msg(post),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_reply_kb()
    )
    if post["status"] == "publishing":
        ok = await send_post_to_channel(context.bot, post)
        update_post(post["id"], {"status": "published" if ok else "failed"})
    context.user_data.clear()


# ── Отправка в канал ──────────────────────────────────────────────────────────

def _build_raw_keyboard(buttons: list) -> dict | None:
    """Строит клавиатуру для raw API с поддержкой поля style (Bot API 9.4)."""
    if not buttons:
        return None
    # Определяем, нужен ли raw (есть ли хоть одна кнопка со style)
    has_style = False
    # Нормализуем: buttons может быть list[dict] или list[list[dict]]
    if buttons and isinstance(buttons[0], dict):
        rows = [[b] for b in buttons]
    else:
        rows = buttons
    for row in rows:
        for b in row:
            if b.get("style"):
                has_style = True
    if not has_style:
        return None  # Можно использовать обычный InlineKeyboardMarkup
    # Строим raw JSON для Telegram
    raw_rows = []
    for row in rows:
        raw_row = []
        for b in row:
            btn = {"text": b["text"], "url": b["url"]}
            if b.get("style"):
                btn["style"] = b["style"]
            raw_row.append(btn)
        raw_rows.append(raw_row)
    return {"inline_keyboard": raw_rows}


async def _send_raw_to_channel(payload: dict) -> bool:
    """Отправка через прямой HTTP-запрос к Telegram API (для поддержки style)."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.json()
            if resp.status == 200:
                return True
            log.error(f"❌ Raw API ошибка: {body}")
            return False


async def _send_raw_photo_to_channel(payload: dict) -> bool:
    """Отправка фото через прямой HTTP-запрос к Telegram API."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.json()
            if resp.status == 200:
                return True
            log.error(f"❌ Raw API фото ошибка: {body}")
            return False


async def send_post_to_channel(bot: Bot, post: dict) -> bool:
    raw_text = post.get("text", "")
    photo    = post.get("photo")
    video    = post.get("video")
    buttons  = post.get("buttons", [])

    has_html = any(tag in raw_text for tag in ("<b>", "<i>", "<u>", "<s>", "<a ", "<code>", "<pre>", "<tg-"))
    safe_text = raw_text if has_html else html_module.escape(raw_text)

    # Проверяем, нужна ли raw-отправка (есть ли кнопки с style)
    raw_kb = _build_raw_keyboard(buttons)

    if raw_kb:
        # Отправляем через прямой API-запрос с поддержкой style
        import json as _json
        payload = {
            "chat_id": TARGET_CHANNEL,
            "parse_mode": "HTML",
            "reply_markup": raw_kb,
        }
        if photo:
            payload["photo"] = photo
            payload["caption"] = safe_text
            ok = await _send_raw_photo_to_channel(payload)
        else:
            payload["text"] = safe_text or "."
            ok = await _send_raw_to_channel(payload)
        if ok:
            log.info(f"✅ Пост {post['id']} опубликован (raw API с цветными кнопками)")
            return True
        log.error(f"❌ Ошибка raw отправки, пробуем обычный метод")

    # Обычная отправка через библиотеку
    if buttons:
        if buttons and isinstance(buttons[0], dict):
            kb_rows = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
        else:
            kb_rows = [
                [InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
                for row in buttons
            ]
        reply_markup = InlineKeyboardMarkup(kb_rows)
    else:
        reply_markup = None

    async def _try_send(txt, pm):
        if photo:
            await bot.send_photo(TARGET_CHANNEL, photo=photo, caption=txt,
                                 parse_mode=pm, reply_markup=reply_markup)
        elif video:
            await bot.send_video(TARGET_CHANNEL, video=video, caption=txt,
                                 parse_mode=pm, reply_markup=reply_markup)
        else:
            await bot.send_message(TARGET_CHANNEL, text=txt or ".",
                                   parse_mode=pm, reply_markup=reply_markup)

    try:
        await _try_send(safe_text, ParseMode.HTML)
        log.info(f"✅ Пост {post['id']} опубликован")
        return True
    except Exception as e:
        log.error(f"❌ Ошибка HTML-отправки: {e}")

    try:
        await _try_send(raw_text, None)
        log.info(f"✅ Пост {post['id']} опубликован (без HTML)")
        return True
    except Exception as e2:
        log.error(f"❌ Повторная ошибка: {e2}")
        return False


# ── Список постов ─────────────────────────────────────────────────────────────

async def edit_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        send = query.edit_message_text
    else:
        send = update.message.reply_text
    posts = load_posts()
    if not posts:
        await send(
            "📋 Постов пока нет.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]])
        )
        return
    buttons = []
    for p in reversed(posts[-15:]):
        preview = (p.get("text") or "📷 Медиа")[:28]
        status  = {"pending": "⏳", "published": "✅", "failed": "❌"}.get(p.get("status",""), "❓")
        ai_tag  = " 🤖" if p.get("source") == "ai" else ""
        buttons.append([InlineKeyboardButton(
            f"{status}{ai_tag} {p.get('publish_at','?')} — {preview}",
            callback_data=f"post_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_menu")])
    await send(
        "📝 *Все посты:* (🤖 = ИИ-вакансия)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ── Просмотр поста ────────────────────────────────────────────────────────────

async def view_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    post_id = query.data.replace("post_", "")
    post    = get_post(post_id)
    if not post:
        await query.edit_message_text("❌ Пост не найден.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]]))
        return
    repeat_txt = f"каждые {post['repeat_days']} дней" if post.get("repeat_days") else "нет"
    status_map = {"pending": "⏳ Ожидает", "published": "✅ Опубликован", "failed": "❌ Ошибка", "publishing": "🚀 Публикуется"}
    btns = post.get("buttons", [])
    if btns:
        if btns and isinstance(btns[0], dict):
            btn_info = "\n".join(f"  [{b.get('text','?')}]" for b in btns)
        else:
            btn_info = "\n".join(
                "  " + "  |  ".join(f"[{b.get('text','?')}]" for b in row)
                for row in btns
            )
    else:
        btn_info = "  нет"

    source_tag = " 🤖 ИИ" if post.get("source") == "ai" else ""
    info = (
        f"📌 *Пост* `{post['id']}`{source_tag}\n\n"
        f"📅 Дата: `{post.get('publish_at','—')}`\n"
        f"🔁 Автоповтор: {repeat_txt}\n"
        f"📊 Статус: {status_map.get(post.get('status',''), '—')}\n"
        f"🕐 Создан: {post.get('created_at','—')}\n"
        f"🔘 Кнопки:\n{btn_info}\n\n"
        f"{'📝 ' + post['text'][:200] if post.get('text') else '📷 Медиа без текста'}"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Изменить текст", callback_data=f"edittext_{post_id}"),
            InlineKeyboardButton("📅 Изменить дату",  callback_data=f"editdate_{post_id}"),
        ],
        [
            InlineKeyboardButton("🕐 Запланировать",  callback_data=f"reschedule_{post_id}"),
            InlineKeyboardButton("🔥 Опубликовать",   callback_data=f"pubnow_{post_id}"),
        ],
        [
            InlineKeyboardButton("📋 Дублировать",    callback_data=f"dup_{post_id}"),
            InlineKeyboardButton("🗑 Удалить пост",   callback_data=f"del_confirm_{post_id}"),
        ],
        [InlineKeyboardButton("← Назад",              callback_data="edit_list")],
    ])
    await query.edit_message_text(info, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def pub_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer("Публикую...")
    post_id = query.data.replace("pubnow_", "")
    post    = get_post(post_id)
    if not post:
        await query.edit_message_text("❌ Пост не найден.")
        return
    ok = await send_post_to_channel(context.bot, post)
    update_post(post_id, {"status": "published" if ok else "failed"})
    msg = "✅ Пост опубликован!" if ok else "❌ Ошибка при публикации."
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Все посты", callback_data="edit_list")],
        [InlineKeyboardButton("← Меню",      callback_data="back_menu")],
    ]))

async def dup_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    post_id = query.data.replace("dup_", "")
    post    = get_post(post_id)
    if not post:
        await query.edit_message_text("❌ Пост не найден.")
        return
    new_p = {**post, "id": new_id(), "status": "pending", "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")}
    posts = load_posts()
    posts.append(new_p)
    save_posts(posts)
    await query.edit_message_text(
        f"✅ Пост продублирован!\n🆔 Новый ID: `{new_p['id']}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 Открыть дубль", callback_data=f"post_{new_p['id']}")],
            [InlineKeyboardButton("← Меню",           callback_data="back_menu")],
        ])
    )

async def del_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    post_id = query.data.replace("del_confirm_", "")
    post    = get_post(post_id)
    preview = (post.get("text") or "📷 Медиа")[:50] if post else "?"
    await query.edit_message_text(
        f"🗑 *Удалить пост?*\n\n_{preview}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"del_{post_id}"),
            InlineKeyboardButton("❌ Отмена",       callback_data=f"post_{post_id}"),
        ]])
    )

async def del_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("del_", "")
    delete_post_by_id(post_id)
    await query.edit_message_text("🗑 Пост удалён.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Все посты", callback_data="edit_list")],
        [InlineKeyboardButton("← Меню",      callback_data="back_menu")],
    ]))

async def reschedule_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает пикер расписания для уже существующего поста."""
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("reschedule_", "")
    context.user_data["rescheduling_id"] = post_id
    await query.edit_message_text(
        "⏰ *Выбери новое время публикации:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=schedule_picker_kb()
    )


async def reschedule_post_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор нового времени из пикера."""
    query = update.callback_query
    await query.answer()
    post_id = context.user_data.get("rescheduling_id")
    if not post_id:
        try:
            await query.message.delete()
        except:
            pass
        await context.bot.send_message(query.message.chat_id, "❌ Ошибка: пост не найден.", reply_markup=main_reply_kb())
        return

    dt_str = query.data.replace("sched_", "")
    if dt_str == "сейчас":
        dt_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    if dt_str == "custom":
        # Для ручного ввода — пока просто возвращаем в меню
        await query.edit_message_text(
            "📅 Напиши дату и время:\n`ДД.ММ.ГГГГ ЧЧ:ММ`\nПример: `25.03.2026 20:00`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Отмена", callback_data=f"post_{post_id}")]])
        )
        return

    update_post(post_id, {"publish_at": dt_str, "status": "pending"})
    context.user_data.pop("rescheduling_id", None)
    await query.edit_message_text(
        f"✅ *Пост перепланирован!*\n📅 Новое время: `{dt_str}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 Открыть пост", callback_data=f"post_{post_id}")],
            [InlineKeyboardButton("← Меню",         callback_data="back_menu")],
        ])
    )



async def edit_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("edittext_", "")
    context.user_data["editing_id"] = post_id
    post = get_post(post_id)
    current = post.get("text","")[:100] if post else ""
    await query.edit_message_text(
        f"✏️ *Редактирование текста*\n\nТекущий текст:\n_{current}_\n\nНапиши новый текст поста:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAIT_EDIT_TEXT

async def edit_text_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_post(context.user_data.get("editing_id"), {"text": update.message.text})
    await update.message.reply_text("✅ Текст обновлён!", reply_markup=main_reply_kb())
    context.user_data.clear()
    return ConversationHandler.END

async def edit_date_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["editing_id"] = query.data.replace("editdate_", "")
    await query.edit_message_text(
        "📅 *Выбери новое время публикации:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=schedule_picker_kb()
    )
    return WAIT_EDIT_DATE

async def edit_date_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "sched_custom":
        await query.edit_message_text(
            "📅 Напиши дату и время:\n`ДД.ММ.ГГГГ ЧЧ:ММ`\nПример: `25.03.2026 20:00`",
            parse_mode=ParseMode.MARKDOWN
        )
        return WAIT_EDIT_DATE
    dt_str = query.data.replace("sched_", "")
    if dt_str == "сейчас":
        dt_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    update_post(context.user_data.get("editing_id"), {"publish_at": dt_str, "status": "pending"})
    try:
        await query.message.delete()
    except:
        pass
    await context.bot.send_message(query.message.chat_id, f"✅ Дата обновлена: `{dt_str}`", parse_mode=ParseMode.MARKDOWN, reply_markup=main_reply_kb())
    context.user_data.clear()
    return ConversationHandler.END

async def edit_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%d.%m.%Y %H:%M")
        update_post(context.user_data.get("editing_id"), {"publish_at": text, "status": "pending"})
        await update.message.reply_text("✅ Дата обновлена!", reply_markup=main_reply_kb())
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Неверный формат.\nПример: `25.03.2026 20:00`", parse_mode=ParseMode.MARKDOWN)
        return WAIT_EDIT_DATE


# ── Настройки ─────────────────────────────────────────────────────────────────

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    posts     = load_posts()
    total     = len(posts)
    pending   = len([p for p in posts if p.get("status") == "pending"])
    published = len([p for p in posts if p.get("status") == "published"])
    ai_posts  = len([p for p in posts if p.get("source") == "ai"])
    ai_status = "✅ Настроен" if OPENROUTER_KEY else "❌ Не настроен (добавь OPENROUTER_KEY в .env)"
    await query.edit_message_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"📢 Канал: <code>{TARGET_CHANNEL}</code>\n"
        f"👤 Admin ID: <code>{ADMIN_ID}</code>\n"
        f"🤖 OpenRouter: {ai_status}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"📋 Всего постов: {total}\n"
        f"⏳ Ожидают публикации: {pending}\n"
        f"✅ Опубликовано: {published}\n"
        f"🤖 ИИ-вакансий: {ai_posts}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]])
    )


async def scheduler_loop(bot: Bot):
    log.info("⏰ Планировщик запущен — проверка каждые 30 сек")
    while True:
        try:
            now_dt   = datetime.now()
            now_str  = now_dt.strftime("%d.%m.%Y %H:%M")
            now_time = now_dt.strftime("%H:%M")
            today    = now_dt.strftime("%d.%m.%Y")

            # Обычные запланированные посты
            posts   = load_posts()
            changed = False
            for post in posts:
                if post.get("status") != "pending":
                    continue
                if post.get("publish_at", "9999") <= now_str:
                    log.info(f"⏰ Публикую пост {post['id']}")
                    ok = await send_post_to_channel(bot, post)
                    if ok:
                        if post.get("repeat_days"):
                            try:
                                dt = datetime.strptime(post["publish_at"], "%d.%m.%Y %H:%M")
                                dt += timedelta(days=post["repeat_days"])
                                post["publish_at"] = dt.strftime("%d.%m.%Y %H:%M")
                            except Exception:
                                post["status"] = "published"
                        else:
                            post["status"] = "published"
                    else:
                        post["status"] = "failed"
                    changed = True
            if changed:
                save_posts(posts)



        except Exception as e:
            log.error(f"Ошибка планировщика: {e}")
        await asyncio.sleep(30)


# ── Запуск ────────────────────────────────────────────────────────────────────

async def run():
    if not BOT_TOKEN:
        log.error("BOT_TOKEN не задан в .env!")
        return
    if not TARGET_CHANNEL:
        log.error("TARGET_CHANNEL не задан в .env!")
        return
    if not OPENROUTER_KEY:
        log.warning("⚠️ OPENROUTER_KEY не задан — ИИ-вакансии не будут работать!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu",  menu_cmd))

    # ── Создание поста
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(create_post_start, pattern="^create_post$"),
            MessageHandler(filters.Regex("^✏️ Создать пост$"), create_post_start)
        ],
        states={
            WAIT_TEXT    : [MessageHandler(filters.TEXT, got_text)],
            WAIT_MEDIA   : [
                MessageHandler(filters.PHOTO | filters.VIDEO, got_media),
                CallbackQueryHandler(skip_media, pattern="^media_skip$"),
                CommandHandler("skip", skip_media),
            ],
            WAIT_BUTTONS : [
                CallbackQueryHandler(buttons_callback, pattern="^(btn_done|btn_clear)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_buttons_text),
            ],
            WAIT_SCHEDULE: [CallbackQueryHandler(got_schedule, pattern="^sched_")],
            WAIT_DATE    : [MessageHandler(filters.TEXT & ~filters.COMMAND, got_date)],
            WAIT_TIME    : [MessageHandler(filters.TEXT & ~filters.COMMAND, got_time)],
            WAIT_REPEAT  : [
                MessageHandler(filters.TEXT, got_repeat_text),
                CallbackQueryHandler(got_repeat_cb, pattern="^repeat_skip$"),
            ],
        },
        fallbacks=[
            CommandHandler("menu", menu_cmd),
            CallbackQueryHandler(back_menu, pattern="^back_menu$")
        ],
        per_message=False,
    ))

    # ── ИИ-генерация вакансии (прямая, без уточнений)
    app.add_handler(CallbackQueryHandler(ai_gen_start, pattern="^ai_gen_(remote|courier)$"))

    # ── Редактирование текста
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_text_start, pattern="^edittext_")],
        states={WAIT_EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_done)]},
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))

    # ── Редактирование даты
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_date_start, pattern="^editdate_")],
        states={
            WAIT_EDIT_DATE: [
                CallbackQueryHandler(edit_date_cb,  pattern="^sched_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_text),
            ],
        },
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))

    # ── Редактирование текста ИИ-вакансии
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ai_edit_text_start, pattern="^ai_edit_text$")],
        states={
            AI_WAIT_EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_edit_text_done)],
        },
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))

    app.add_handler(CallbackQueryHandler(reschedule_post_start,     pattern="^reschedule_"))
    app.add_handler(CallbackQueryHandler(reschedule_post_done,      pattern="^sched_"))
    
    app.add_handler(MessageHandler(filters.Regex("^🤖 ИИ-вакансия$"), ai_vacancy_menu))
    app.add_handler(MessageHandler(filters.Regex("^🤖 Сгенерировать пост$"), ai_vacancy_menu))
    app.add_handler(MessageHandler(filters.Regex("^📝 Мои посты$"), edit_list))
    app.add_handler(MessageHandler(filters.Regex("^📋 Список постов$"), edit_list))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Настройки$"), settings))
    app.add_handler(MessageHandler(filters.Regex("^❓ Помощь$"), help_menu))

    app.add_handler(CallbackQueryHandler(ai_gen_quick,    pattern="^ai_gen_quick_remote$"))
    app.add_handler(CallbackQueryHandler(ai_vacancy_menu,        pattern="^ai_vacancy_menu$"))
    app.add_handler(CallbackQueryHandler(ai_pub_now_handler,     pattern="^ai_pub_now$"))
    app.add_handler(CallbackQueryHandler(ai_pub_schedule_handler,pattern="^ai_pub_schedule$"))
    app.add_handler(CallbackQueryHandler(ai_scheduled_time,      pattern="^sched_"))
    app.add_handler(CallbackQueryHandler(ai_regenerate,          pattern="^ai_regenerate$"))
    app.add_handler(CallbackQueryHandler(edit_list,              pattern="^edit_list$"))
    app.add_handler(CallbackQueryHandler(settings,               pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(help_menu,              pattern="^help_menu$"))
    app.add_handler(CallbackQueryHandler(back_menu,              pattern="^back_menu$"))
    app.add_handler(CallbackQueryHandler(view_post,              pattern="^post_"))
    app.add_handler(CallbackQueryHandler(pub_now,                pattern="^pubnow_"))
    app.add_handler(CallbackQueryHandler(dup_post,               pattern="^dup_"))
    app.add_handler(CallbackQueryHandler(del_confirm,            pattern="^del_confirm_"))
    app.add_handler(CallbackQueryHandler(del_post,               pattern="^del_"))

    log.info("🤖 Content Manager Bot v6.0 запускается...")
    log.info(f"📢 Канал: {TARGET_CHANNEL} | Admin: {ADMIN_ID}")
    log.info(f"🤖 OpenRouter: {'✅' if OPENROUTER_KEY else '❌ не настроен'}")

    async with app:
        await app.start()
        await app.updater.start_polling()
        log.info("✅ Бот запущен!")
        await scheduler_loop(app.bot)


if __name__ == "__main__":
    asyncio.run(run())


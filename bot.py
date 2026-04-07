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

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
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

def main_menu_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Создать пост",   callback_data="create_post"),
            InlineKeyboardButton("📝 Мои посты",      callback_data="edit_list"),
        ],
        [
            InlineKeyboardButton("🤖 ИИ-вакансия",    callback_data="ai_vacancy_menu"),
            InlineKeyboardButton("⚙️ Настр. вакансий",callback_data="vacancy_settings_menu"),
        ],
        [
            InlineKeyboardButton("🤖 Автопилот",      callback_data="ap_menu"),
            InlineKeyboardButton("📅 Контент-план",   callback_data="content_plan"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки",      callback_data="settings"),
        ],
        [
            InlineKeyboardButton("📋 Шаблоны",        callback_data="templates"),
            InlineKeyboardButton("🎉 Эмодзи",         callback_data="emoji_cat"),
        ],
        [
            InlineKeyboardButton("❓ Помощь",         callback_data="help_menu"),
        ],
    ])

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
        reply_markup=main_menu_kb()
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    context.user_data.clear()
    await update.message.reply_text("📌 Главное меню:", reply_markup=main_menu_kb())

async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("📌 Главное меню:", reply_markup=main_menu_kb())


# ══════════════════════════════════════════════════════════════════════════════
#  🤖 ИИ-ВАКАНСИИ
# ══════════════════════════════════════════════════════════════════════════════

async def ai_vacancy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора типа ИИ-вакансии."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
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
        "publish_at" : "now",
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
    await query.edit_message_text(result, reply_markup=main_menu_kb())
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
    if dt_str == "now":
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
        reply_markup=main_menu_kb()
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


# ══════════════════════════════════════════════════════════════════════════════
#  ⚙️ НАСТРОЙКИ ВАКАНСИЙ
# ══════════════════════════════════════════════════════════════════════════════

async def vacancy_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚙️ *Настройки вакансий*\n\nВыбери тип для редактирования:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Настройки: Удалёнка",   callback_data="vsett_remote")],
            [InlineKeyboardButton("🚴 Настройки: Курьер",     callback_data="vsett_courier")],
            [InlineKeyboardButton("← Назад",                   callback_data="back_menu")],
        ])
    )

async def vacancy_settings_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vac_type = query.data.replace("vsett_", "")
    cfg = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    type_label = "Удалённая работа" if vac_type == "remote" else "Курьер"

    offer_str = "\n".join(f"• {o}" for o in cfg.get("offer", []))
    req_str   = "\n".join(f"• {r}" for r in cfg.get("requirements", []))

    text = (
        f"⚙️ *{type_label}* — текущие настройки:\n\n"
        f"💰 Зарплата: `{cfg.get('salary_min', 0):,} – {cfg.get('salary_max', 0):,} ₽`\n"
        f"🕐 График: `{cfg.get('schedule', '—')}`\n"
        f"🏢 О компании: _{cfg.get('company_info', '—')}_\n\n"
        f"✅ *Что предлагаем:*\n{offer_str}\n\n"
        f"📋 *Требования:*\n{req_str}\n\n"
        f"🔗 Ссылки:\n" + "\n".join(f"  {i+1}. `{l.get('url','—')}` ({l.get('label','?')})" for i, l in enumerate(cfg.get("links", [])))
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Изменить зарплату",   callback_data=f"vedit_salary_{vac_type}")],
            [InlineKeyboardButton("✏️ Изменить ссылки",     callback_data=f"vedit_links_{vac_type}")],
            [InlineKeyboardButton("✏️ Изменить график",     callback_data=f"vedit_sched_{vac_type}")],
            [InlineKeyboardButton("← Назад",                callback_data="vacancy_settings_menu")],
        ])
    )

# ── Редактирование ссылок (ConversationHandler ниже) ─────────────────────────

VEDIT_WAIT_LINK_MAIN, VEDIT_WAIT_LINK_ALT, VEDIT_WAIT_SALARY, VEDIT_WAIT_SCHED = range(20, 24)

async def vedit_links_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vac_type = query.data.replace("vedit_links_", "")
    context.user_data["vedit_type"] = vac_type
    cfg   = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    links = cfg.get("links", [])
    cur1  = links[0]["url"] if links else "—"
    btn1  = "📝 Откликнуться" if vac_type == "remote" else "🚴 Откликнуться"
    await query.edit_message_text(
        f"🔗 *Ссылка 1 (кнопка «{btn1}»)*\n\n"
        f"Текущая: `{cur1}`\n\n"
        "Отправь новую ссылку:",
        parse_mode=ParseMode.MARKDOWN
    )
    return VEDIT_WAIT_LINK_MAIN

async def vedit_got_link_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not link.startswith("http"):
        await update.message.reply_text("❌ Ссылка должна начинаться с http(s)://")
        return VEDIT_WAIT_LINK_MAIN
    context.user_data["vedit_link_main"] = link
    vac_type = context.user_data.get("vedit_type", "remote")
    cfg   = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    links = cfg.get("links", [])
    cur2  = links[1]["url"] if len(links) > 1 else "—"
    await update.message.reply_text(
        f"🔗 *Ссылка 2*\n\n"
        f"Текущая: `{cur2}`\n\n"
        "Отправь новую ссылку или /skip чтобы оставить без изменений:",
        parse_mode=ParseMode.MARKDOWN
    )
    return VEDIT_WAIT_LINK_ALT

async def vedit_got_link_alt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if link == "/skip":
        link = context.user_data.get("vedit_link_main", "")
    elif not link.startswith("http"):
        await update.message.reply_text("❌ Ссылка должна начинаться с http(s)://  или /skip")
        return VEDIT_WAIT_LINK_ALT

    vac_type = context.user_data.get("vedit_type", "remote")
    cfg = load_vacancy_config()
    cfg.setdefault(vac_type, DEFAULT_VACANCY_CONFIG[vac_type].copy())
    link1 = context.user_data.get("vedit_link_main", "")
    existing_links = cfg[vac_type].get("links", DEFAULT_VACANCY_CONFIG[vac_type]["links"])
    label1 = existing_links[0]["label"] if existing_links else "Ссылка 1"
    label2 = existing_links[1]["label"] if len(existing_links) > 1 else "Ссылка 2"
    if link == context.user_data.get("vedit_link_main", ""):
        link = existing_links[1]["url"] if len(existing_links) > 1 else link
    cfg[vac_type]["links"] = [
        {"url": link1, "label": label1},
        {"url": link,  "label": label2},
    ]
    save_vacancy_config(cfg)

    await update.message.reply_text(
        "✅ Ссылки обновлены!",
        reply_markup=main_menu_kb()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def vedit_salary_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vac_type = query.data.replace("vedit_salary_", "")
    context.user_data["vedit_type"] = vac_type
    cfg = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    await query.edit_message_text(
        f"💰 *Зарплата*\n\n"
        f"Текущая: `{cfg.get('salary_min',0):,} – {cfg.get('salary_max',0):,} ₽`\n\n"
        "Введи диапазон через дефис:\n`60000-110000`",
        parse_mode=ParseMode.MARKDOWN
    )
    return VEDIT_WAIT_SALARY

async def vedit_got_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    try:
        parts = text.split("-")
        sal_min, sal_max = int(parts[0]), int(parts[1])
    except Exception:
        await update.message.reply_text("❌ Формат: `60000-110000`", parse_mode=ParseMode.MARKDOWN)
        return VEDIT_WAIT_SALARY
    vac_type = context.user_data.get("vedit_type", "remote")
    cfg = load_vacancy_config()
    cfg.setdefault(vac_type, DEFAULT_VACANCY_CONFIG[vac_type].copy())
    cfg[vac_type]["salary_min"] = sal_min
    cfg[vac_type]["salary_max"] = sal_max
    save_vacancy_config(cfg)
    await update.message.reply_text("✅ Зарплата обновлена!", reply_markup=main_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END

async def vedit_sched_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vac_type = query.data.replace("vedit_sched_", "")
    context.user_data["vedit_type"] = vac_type
    cfg = load_vacancy_config().get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])
    await query.edit_message_text(
        f"🕐 *График работы*\n\nТекущий: `{cfg.get('schedule', '—')}`\n\nВведи новый:",
        parse_mode=ParseMode.MARKDOWN
    )
    return VEDIT_WAIT_SCHED

async def vedit_got_sched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vac_type = context.user_data.get("vedit_type", "remote")
    cfg = load_vacancy_config()
    cfg.setdefault(vac_type, DEFAULT_VACANCY_CONFIG[vac_type].copy())
    cfg[vac_type]["schedule"] = update.message.text.strip()
    save_vacancy_config(cfg)
    await update.message.reply_text("✅ График обновлён!", reply_markup=main_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END


# ── Помощь ────────────────────────────────────────────────────────────────────

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "❓ *Справка по боту*\n\n"
        "*🤖 ИИ-вакансия:*\n"
        "Нажми «ИИ-вакансия» → выбери тип → настрой параметры → одобри и опубликуй\n\n"
        "*Создание поста:*\n"
        "1. Напиши текст поста\n"
        "2. Прикрепи фото/видео (или пропусти)\n"
        "3. Добавь кнопки (или пропусти)\n"
        "4. Выбери время публикации\n\n"
        "*Формат кнопок:*\n"
        "`Текст - https://ссылка`\n"
        "В ряд через `|`:\n"
        "`Кнопка 1 - https://url | Кнопка 2 - https://url`\n\n"
        "*Команды:*\n"
        "/start — перезапуск\n"
        "/menu — главное меню\n"
        "/skip — пропустить шаг"
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]])
    )


# ── Создание поста ────────────────────────────────────────────────────────────

async def create_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_post"] = {"buttons": []}
    await query.edit_message_text(
        "✏️ *Создание поста*\n\n"
        "Напиши текст поста.\n"
        "Поддерживается HTML-форматирование:\n"
        "`<b>жирный</b>` `<i>курсив</i>` `<u>подчёркнутый</u>`\n\n"
        "Или /skip — без текста.",
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
            [InlineKeyboardButton("⏩ Пропустить медиа", callback_data="media_skip")]
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

COLOR_MAP = {
    "!r": "🔴", "!g": "🟢", "!b": "🔵", "!y": "🟡",
    "!o": "🟠", "!p": "🟣", "!w": "⚪", "!k": "⚫",
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
            color_emoji = ""
            for prefix, emoji in COLOR_MAP.items():
                if cell.lower().startswith(prefix + " "):
                    color_emoji = emoji + " "
                    cell = cell[len(prefix)+1:].strip()
                    break
            if " - " in cell:
                parts = cell.rsplit(" - ", 1)
                text = parts[0].strip()
                url  = parts[1].strip()
                if url.startswith("http"):
                    row.append({"text": f"{color_emoji}{text}", "url": url})
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
    ])

async def send_button_menu(message, context: ContextTypes.DEFAULT_TYPE):
    preview = _btn_preview(context)
    hint = (
        "🔘 *Кнопки поста:*\n"
        f"`{preview}`\n\n"
        "Отправь кнопки в формате:\n"
        "`Текст - https://ссылка`\n"
        "В ряд через `|`\n\n"
        "Цвет:\n"
        "`!r` 🔴  `!g` 🟢  `!b` 🔵  `!y` 🟡\n"
        "`!o` 🟠  `!p` 🟣  `!w` ⚪  `!k` ⚫"
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
    ])

async def got_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "sched_now":
        context.user_data["new_post"]["publish_at"] = "now"
        await finish_post_query(query, context)
        return ConversationHandler.END

    if query.data == "sched_custom":
        await query.edit_message_text(
            "📅 Напиши дату публикации:\nФормат: `ДД.ММ.ГГГГ`\nПример: `25.03.2026`",
            parse_mode=ParseMode.MARKDOWN
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
            parse_mode=ParseMode.MARKDOWN
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
        parse_mode=ParseMode.MARKDOWN
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
    publish_at = np.get("publish_at", "now")
    return {
        "id"         : new_id(),
        "text"       : np.get("text", ""),
        "photo"      : np.get("photo"),
        "video"      : np.get("video"),
        "buttons"    : np.get("buttons", []),
        "publish_at" : publish_at,
        "repeat_days": np.get("repeat_days"),
        "status"     : "pending" if publish_at != "now" else "publishing",
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
        reply_markup=main_menu_kb()
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
        reply_markup=main_menu_kb()
    )
    if post["status"] == "publishing":
        ok = await send_post_to_channel(context.bot, post)
        update_post(post["id"], {"status": "published" if ok else "failed"})
    context.user_data.clear()


# ── Отправка в канал ──────────────────────────────────────────────────────────

async def send_post_to_channel(bot: Bot, post: dict) -> bool:
    raw_text = post.get("text", "")
    photo    = post.get("photo")
    video    = post.get("video")
    buttons  = post.get("buttons", [])

    has_html = any(tag in raw_text for tag in ("<b>", "<i>", "<u>", "<s>", "<a ", "<code>", "<pre>", "<tg-"))
    safe_text = raw_text if has_html else html_module.escape(raw_text)

    reply_markup = None
    if buttons:
        if buttons and isinstance(buttons[0], dict):
            kb_rows = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
        else:
            kb_rows = [
                [InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
                for row in buttons
            ]
        reply_markup = InlineKeyboardMarkup(kb_rows)

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


# ── Контент-план ──────────────────────────────────────────────────────────────

async def content_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pending = [p for p in load_posts() if p.get("status") == "pending"]
    if not pending:
        await query.edit_message_text(
            "📅 *Контент-план пуст*\n\nНет запланированных постов.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]])
        )
        return
    text    = "📅 *Запланированные посты:*\n\n"
    buttons = []
    for p in pending:
        preview = (p.get("text") or "📷 Медиа")[:35]
        source  = " 🤖" if p.get("source") == "ai" else ""
        repeat  = f" 🔁{p['repeat_days']}д" if p.get("repeat_days") else ""
        text   += f"🕐 `{p['publish_at']}`{repeat}{source} — {preview}\n"
        buttons.append([InlineKeyboardButton(
            f"📌 {p['publish_at']} — {preview[:25]}",
            callback_data=f"post_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton("← Назад", callback_data="back_menu")])
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ── Список постов ─────────────────────────────────────────────────────────────

async def edit_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    posts = load_posts()
    if not posts:
        await query.edit_message_text(
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
    await query.edit_message_text(
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
            InlineKeyboardButton("📋 Дублировать",    callback_data=f"dup_{post_id}"),
            InlineKeyboardButton("🔥 Опубликовать",   callback_data=f"pubnow_{post_id}"),
        ],
        [InlineKeyboardButton("🗑 Удалить пост",      callback_data=f"del_confirm_{post_id}")],
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


# ── Редактирование ────────────────────────────────────────────────────────────

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
    await update.message.reply_text("✅ Текст обновлён!", reply_markup=main_menu_kb())
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
    if dt_str == "now":
        dt_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    update_post(context.user_data.get("editing_id"), {"publish_at": dt_str, "status": "pending"})
    await query.edit_message_text(f"✅ Дата обновлена: `{dt_str}`", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END

async def edit_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%d.%m.%Y %H:%M")
        update_post(context.user_data.get("editing_id"), {"publish_at": text, "status": "pending"})
        await update.message.reply_text("✅ Дата обновлена!", reply_markup=main_menu_kb())
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Неверный формат.\nПример: `25.03.2026 20:00`", parse_mode=ParseMode.MARKDOWN)
        return WAIT_EDIT_DATE


# ── Шаблоны ───────────────────────────────────────────────────────────────────

TEMPLATES = {
    "📢 Анонс":        "📢 <b>АНОНС</b>\n\n✍️ Текст анонса...\n\n📅 Дата: \n📍 Место: ",
    "🔥 Акция":        "🔥 <b>АКЦИЯ</b>\n\n💥 Описание акции...\n\n⏰ Действует до: ",
    "💼 Вакансия":     "💼 <b>ВАКАНСИЯ</b>\n\n🏢 Компания: \n📌 Должность: \n💰 Зарплата: ",
    "📊 Вопрос дня":   "📊 <b>ВОПРОС ДНЯ</b>\n\n❓ Твой вопрос...\n\n👇 Ответь в комментариях!",
    "🎉 Поздравление": "🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n🥳 Текст поздравления...\n\n❤️ Ваша команда",
    "📌 Новость":      "📌 <b>НОВОСТЬ</b>\n\nТекст новости...\n\n🔗 Подробнее: ",
}

async def show_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    btns = [[InlineKeyboardButton(name, callback_data=f"tpl_{i}")] for i, name in enumerate(TEMPLATES)]
    btns.append([InlineKeyboardButton("← Назад", callback_data="back_menu")])
    await query.edit_message_text("📋 *Выбери шаблон:*", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(btns))

async def use_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx  = int(query.data.replace("tpl_", ""))
    name = list(TEMPLATES.keys())[idx]
    tpl  = list(TEMPLATES.values())[idx]
    await query.edit_message_text(
        f"📋 *{name}*\n\nСкопируй и используй при создании поста:\n\n`{tpl}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Создать пост", callback_data="create_post")],
            [InlineKeyboardButton("← Шаблоны",       callback_data="templates")],
        ])
    )


# ── Эмодзи ───────────────────────────────────────────────────────────────────

async def emoji_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎉 *Каталог эмодзи* — скопируй нужные:\n\n"
        "🎉 🔥 💥 ⭐ 🚀 💡 📢 📌 ✅ ❌ 💰 🎁 🏆 🎯 📊 💼 🔑 🌟 💎 👑\n"
        "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💗 💓 💞 💕\n"
        "😀 😎 🤩 🥳 🤑 😍 🤗 👍 🙌 💪 🤝 ✌️ 👏 🫶\n"
        "📱 💻 🖥️ 📷 📸 🎬 🎥 🎙️ 🔊 📣\n"
        "🏠 🏢 🏪 🏦 ✈️ 🚗 🚌 🚀 🚂\n"
        "📅 📆 ⏰ ⌚ 🕐 🕑 🕒 🕓 🕔 🕕\n"
        "🔵 🟢 🔴 🟡 🟠 🟣 ⚪ ⚫",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]])
    )


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
        f"⚙️ *Настройки*\n\n"
        f"📢 Канал: `{TARGET_CHANNEL}`\n"
        f"👤 Admin ID: `{ADMIN_ID}`\n"
        f"🤖 OpenRouter: {ai_status}\n\n"
        f"📊 *Статистика:*\n"
        f"📋 Всего постов: {total}\n"
        f"⏳ Ожидают публикации: {pending}\n"
        f"✅ Опубликовано: {published}\n"
        f"🤖 ИИ-вакансий: {ai_posts}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back_menu")]])
    )


# ── Планировщик задач ──────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
#  🤖 АВТОПИЛОТ
# ══════════════════════════════════════════════════════════════════════════════

AUTOPILOT_FILE = "autopilot.json"

def load_autopilot() -> dict:
    default = {
        "enabled": False,
        "times": ["08:00", "12:00", "20:00"],
        "types": ["remote", "courier"],
        "last_date": "",
        "done_times": [],
    }
    try:
        with open(AUTOPILOT_FILE, encoding="utf-8") as f:
            d = json.load(f)
            for k, v in default.items():
                d.setdefault(k, v)
            return d
    except Exception:
        return default

def save_autopilot(cfg: dict):
    with open(AUTOPILOT_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


async def _upload_photo(bot, photo_path: str):
    """Загружает фото через бота и возвращает file_id."""
    try:
        with open(photo_path, "rb") as f:
            msg = await bot.send_photo(chat_id=ADMIN_ID, photo=f)
            file_id = msg.photo[-1].file_id
            await bot.delete_message(chat_id=ADMIN_ID, message_id=msg.message_id)
            log.info(f"📸 Фото загружено: {photo_path} → {file_id[:20]}...")
            return file_id
    except Exception as e:
        log.error(f"❌ Ошибка загрузки фото {photo_path}: {e}")
        return None


async def _autopilot_run(bot):
    """Генерирует и публикует одну вакансию — вызывается планировщиком."""
    import random as _r, pathlib as _pl

    cfg_vac = load_vacancy_config()
    ap      = load_autopilot()
    vac_type = _r.choice(ap["types"])
    vac_cfg  = cfg_vac.get(vac_type, DEFAULT_VACANCY_CONFIG[vac_type])

    offer_list   = "\n".join(f"- {o}" for o in vac_cfg.get("offer", []))
    req_list     = "\n".join(f"- {r}" for r in vac_cfg.get("requirements", []))
    company_info = vac_cfg.get("company_info", "")
    type_label   = "удалённую работу" if vac_type == "remote" else "курьера/доставщика"

    salary_variants = vac_cfg.get("salary_variants", [{"label": "от 60 000 ₽", "hours": "полный день"}])
    chosen_salary   = _r.choice(salary_variants)
    links           = vac_cfg.get("links", [])
    chosen_link     = _r.choice(links) if links else {"url": "", "label": "", "photo_dir": ""}

    # Фото из папки оффера
    photo_path = None
    photo_dir_name = chosen_link.get("photo_dir", "")
    if photo_dir_name:
        pd = _pl.Path(photo_dir_name)
        if pd.exists():
            files = [f for f in pd.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
            if files:
                photo_path = str(_r.choice(files))

    titles_remote = [
        "Оператор колл-центра (удалённо)", "Менеджер по работе с клиентами / удалённо",
        "Специалист поддержки (home office)", "Контент-менеджер на удалёнку",
        "Оператор онлайн-чата / дистанционно", "Менеджер по продажам (удалённая работа)",
        "Специалист по обработке заявок / remote", "Администратор онлайн-сервиса (удалённо)",
        "Координатор клиентского сервиса (дистанционно)", "Оператор входящих обращений / удалённо",
    ]
    titles_courier = [
        "Курьер-доставщик (пеший/вело)", "Водитель-курьер / доставка еды",
        "Пеший курьер в службу доставки", "Курьер на велосипеде — ежедневные выплаты",
        "Курьер последней мили", "Доставщик заказов (пешком/вело/авто)",
        "Курьер в сервис доставки продуктов", "Курьер-исполнитель / гибкий график",
    ]
    company_remote = [
        "Стабильная компания с распределённой командой по всей России.",
        "Работаем в сфере дистанционного сервиса более 5 лет, команда — свыше 2 000 человек.",
        "Федеральный работодатель, специализирующийся на удалённом обслуживании клиентов.",
        "Компания с офисами в 15 городах и полностью удалённым штатом операторов.",
        "Более 8 лет подбираем и развиваем удалённых специалистов по всей стране.",
        "Крупный контакт-центр — более 4 000 сотрудников работают дистанционно.",
        "Официальный работодатель, партнёр ведущих банков и торговых сетей страны.",
        "Стабильный работодатель с многолетней историей и сотнями успешных сотрудников.",
    ]
    company_courier = [
        "Один из крупнейших сервисов экспресс-доставки, работаем в 50+ городах России.",
        "Федеральная служба доставки с ежедневным оборотом более 100 000 заказов.",
        "Динамично растущая логистическая компания — более 12 000 активных курьеров.",
        "Надёжный партнёр: стабильные заказы, быстрые выплаты, поддержка 24/7.",
        "Сервис доставки с высоким рейтингом среди клиентов — ценим каждого в команде.",
        "Работаем с ведущими ресторанами и магазинами города, заказов всегда много.",
        "Логистический партнёр крупных торговых сетей и интернет-магазинов.",
        "Компания, которая платит честно: ежедневные выплаты без задержек уже 6 лет.",
    ]
    призыв_list = [
        "Откликайся прямо сейчас — ждём тебя в команде!",
        "Подавай заявку сегодня и выходи на работу уже на этой неделе.",
        "Присоединяйся — свободные места ограничены.",
        "Жми кнопку ниже и начни зарабатывать уже завтра.",
        "Не откладывай — оставь отклик и мы свяжемся в течение часа.",
        "Актуальная вакансия, набор открыт прямо сейчас.",
        "Твоя новая работа — в одном нажатии кнопки.",
    ]

    title   = _r.choice(titles_remote   if vac_type == "remote" else titles_courier)
    company = _r.choice(company_remote  if vac_type == "remote" else company_courier)
    призыв  = _r.choice(призыв_list)

    prompt = (
        f"Напиши реалистичный текст вакансии для Telegram-канала. Тип: {type_label}.\n\n"
        "ПРАВИЛА:\n"
        "- HTML-теги: <b>жирный</b>, <i>курсив</i>\n"
        "- Эмодзи в начале каждого раздела\n"
        f"- Название СТРОГО: {title}\n"
        f"- О компании СТРОГО: {company}\n"
        f"- Призыв в конце СТРОГО: {призыв}\n"
        "- НЕ упоминай сайты поиска работы\n"
        "- Каждый пункт перефразируй своими словами\n\n"
        "Параметры:\n"
        f"- Зарплата: {chosen_salary['label']} ({chosen_salary['hours']})\n"
        f"- График: {vac_cfg.get('schedule', 'гибкий')}\n"
        f"- Предлагаем: {offer_list}\n"
        f"- Требования: {req_list}\n\n"
        "Структура: заголовок → о компании → зарплата → график → предлагаем → требования → призыв.\n"
        "Только текст поста, без пояснений."
    )

    try:
        text = await call_openrouter(prompt)
    except Exception as e:
        log.error(f"Автопилот: ошибка OpenRouter: {e}")
        return False

    if not text:
        log.error("Автопилот: пустой ответ от OpenRouter")
        return False

    photo_file_id = await _upload_photo(bot, photo_path) if photo_path else None
    buttons = _make_vacancy_buttons(vac_type, vac_cfg, chosen_link)

    post = {
        "id":         new_id(),
        "text":       text,
        "photo":      photo_file_id,
        "video":      None,
        "buttons":    buttons,
        "publish_at": "now",
        "status":     "publishing",
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "source":     "autopilot",
    }
    posts = load_posts()
    posts.append(post)
    save_posts(posts)

    ok = await send_post_to_channel(bot, post)
    update_post(post["id"], {"status": "published" if ok else "failed"})
    log.info(f"🤖 Автопилот: {'✅ опубликована' if ok else '❌ ошибка'} ({vac_type}, {chosen_salary['label']})")
    return ok


# ── Меню автопилота ────────────────────────────────────────────────────────────

async def autopilot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ap = load_autopilot()
    status   = "✅ Включён" if ap["enabled"] else "❌ Выключен"
    times    = "  ".join(ap["times"])
    types_lbl = {"remote": "только удалёнка", "courier": "только курьер"}
    types_str = "удалёнка + курьер" if len(ap["types"]) == 2 else types_lbl.get(ap["types"][0], "?")
    toggle_btn = "🔴 Выключить" if ap["enabled"] else "🟢 Включить"
    await query.edit_message_text(
        f"🤖 *Автопилот вакансий*\n\n"
        f"Статус: {status}\n"
        f"🕐 Расписание: `{times}`\n"
        f"📋 Тип: {types_str}\n\n"
        "Бот сам генерирует и публикует вакансии каждый день без твоего участия.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(toggle_btn, callback_data="ap_toggle")],
            [InlineKeyboardButton("🕐 Изменить время",  callback_data="ap_set_times")],
            [InlineKeyboardButton("📋 Изменить тип",   callback_data="ap_set_types")],
            [InlineKeyboardButton("← Назад",           callback_data="back_menu")],
        ])
    )

async def ap_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ap = load_autopilot()
    ap["enabled"] = not ap["enabled"]
    save_autopilot(ap)
    await autopilot_menu(update, context)

async def ap_set_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ap = load_autopilot()
    cur = ap["types"]
    def mark(val):
        return "✅ " if cur == val else ""
    await query.edit_message_text(
        "📋 *Какие вакансии публиковать?*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{mark(['remote','courier'])}Удалёнка + Курьер", callback_data="aptype_both")],
            [InlineKeyboardButton(f"{mark(['remote'])}Только удалённая",            callback_data="aptype_remote")],
            [InlineKeyboardButton(f"{mark(['courier'])}Только курьер",              callback_data="aptype_courier")],
            [InlineKeyboardButton("← Назад", callback_data="ap_menu")],
        ])
    )

async def ap_set_type_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ap = load_autopilot()
    ap["types"] = {"aptype_both": ["remote","courier"], "aptype_remote": ["remote"], "aptype_courier": ["courier"]}.get(query.data, ["remote","courier"])
    save_autopilot(ap)
    await autopilot_menu(update, context)

AP_WAIT_TIMES = 50

async def ap_set_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ap = load_autopilot()
    times = "  ".join(ap["times"])
    await query.edit_message_text(
        f"🕐 *Расписание автопилота*\n\n"
        f"Текущее: `{times}`\n\n"
        "Отправь новое время через пробел:\n"
        "Пример: `08:00 12:00 20:00`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Оставить текущее", callback_data="ap_menu")]])
    )
    return AP_WAIT_TIMES

async def ap_got_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import re as _re
    times = sorted(set(_re.findall(r'\d{1,2}:\d{2}', update.message.text)))
    valid = []
    for t in times:
        try:
            datetime.strptime(t, "%H:%M")
            valid.append(t.zfill(5))
        except ValueError:
            pass
    if not valid:
        await update.message.reply_text("❌ Не распознал. Пример: `08:00 12:00 20:00`", parse_mode=ParseMode.MARKDOWN)
        return AP_WAIT_TIMES
    ap = load_autopilot()
    ap["times"] = valid
    save_autopilot(ap)
    await update.message.reply_text(
        f"✅ Расписание: `{'  '.join(valid)}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb()
    )
    return ConversationHandler.END

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

            # Автопилот
            ap = load_autopilot()
            if ap.get("enabled"):
                if ap.get("last_date") != today:
                    ap["last_date"]  = today
                    ap["done_times"] = []
                    save_autopilot(ap)
                for slot in ap.get("times", []):
                    if slot <= now_time and slot not in ap.get("done_times", []):
                        # Если слот уже прошёл больше чем на 5 минут — пропускаем
                        # (защита от массовой отправки при первом включении)
                        try:
                            slot_dt = datetime.strptime(f"{today} {slot}", "%d.%m.%Y %H:%M")
                            minutes_late = (now_dt - slot_dt).total_seconds() / 60
                            if minutes_late > 5:
                                log.info(f"🤖 Автопилот: слот {slot} пропущен (опоздание {int(minutes_late)} мин)")
                                ap = load_autopilot()
                                ap["done_times"] = ap.get("done_times", []) + [slot]
                                save_autopilot(ap)
                                continue
                        except Exception:
                            pass
                        log.info(f"🤖 Автопилот: слот {slot}")
                        ok = await _autopilot_run(bot)
                        ap = load_autopilot()
                        ap["done_times"] = ap.get("done_times", []) + [slot]
                        save_autopilot(ap)

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
        entry_points=[CallbackQueryHandler(create_post_start, pattern="^create_post$")],
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
        fallbacks=[CommandHandler("menu", menu_cmd)],
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

    # ── Редактирование ссылок вакансий
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(vedit_links_start, pattern="^vedit_links_")],
        states={
            VEDIT_WAIT_LINK_MAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, vedit_got_link_main)],
            VEDIT_WAIT_LINK_ALT : [MessageHandler(filters.TEXT, vedit_got_link_alt)],
        },
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))

    # ── Редактирование зарплаты
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(vedit_salary_start, pattern="^vedit_salary_")],
        states={
            VEDIT_WAIT_SALARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, vedit_got_salary)],
        },
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))

    # ── Редактирование графика
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(vedit_sched_start, pattern="^vedit_sched_")],
        states={
            VEDIT_WAIT_SCHED: [MessageHandler(filters.TEXT & ~filters.COMMAND, vedit_got_sched)],
        },
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))

    # ── Остальные обработчики
    # ── Автопилот
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ap_set_times, pattern="^ap_set_times$")],
        states={AP_WAIT_TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_got_times)]},
        fallbacks=[CommandHandler("menu", menu_cmd)],
        per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(autopilot_menu,  pattern="^ap_menu$"))
    app.add_handler(CallbackQueryHandler(ap_toggle,       pattern="^ap_toggle$"))
    app.add_handler(CallbackQueryHandler(ap_set_types,    pattern="^ap_set_types$"))
    app.add_handler(CallbackQueryHandler(ap_set_type_cb,  pattern="^aptype_"))
    app.add_handler(CallbackQueryHandler(ai_gen_quick,    pattern="^ai_gen_quick_remote$"))
    app.add_handler(CallbackQueryHandler(ai_vacancy_menu,        pattern="^ai_vacancy_menu$"))
    app.add_handler(CallbackQueryHandler(vacancy_settings_menu,  pattern="^vacancy_settings_menu$"))
    app.add_handler(CallbackQueryHandler(vacancy_settings_type,  pattern="^vsett_"))
    app.add_handler(CallbackQueryHandler(ai_pub_now_handler,     pattern="^ai_pub_now$"))
    app.add_handler(CallbackQueryHandler(ai_pub_schedule_handler,pattern="^ai_pub_schedule$"))
    app.add_handler(CallbackQueryHandler(ai_scheduled_time,      pattern="^sched_"))
    app.add_handler(CallbackQueryHandler(ai_regenerate,          pattern="^ai_regenerate$"))
    app.add_handler(CallbackQueryHandler(content_plan,           pattern="^content_plan$"))
    app.add_handler(CallbackQueryHandler(edit_list,              pattern="^edit_list$"))
    app.add_handler(CallbackQueryHandler(settings,               pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(show_templates,         pattern="^templates$"))
    app.add_handler(CallbackQueryHandler(emoji_catalog,          pattern="^emoji_cat$"))
    app.add_handler(CallbackQueryHandler(help_menu,              pattern="^help_menu$"))
    app.add_handler(CallbackQueryHandler(back_menu,              pattern="^back_menu$"))
    app.add_handler(CallbackQueryHandler(view_post,              pattern="^post_"))
    app.add_handler(CallbackQueryHandler(pub_now,                pattern="^pubnow_"))
    app.add_handler(CallbackQueryHandler(dup_post,               pattern="^dup_"))
    app.add_handler(CallbackQueryHandler(del_confirm,            pattern="^del_confirm_"))
    app.add_handler(CallbackQueryHandler(del_post,               pattern="^del_"))
    app.add_handler(CallbackQueryHandler(use_template,           pattern="^tpl_"))

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


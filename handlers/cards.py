"""
handlers/cards.py

Пользователи: просмотр карточек, голоса, автор-фильтр, жалобы.
Админы:       /addcard (FSM с предпросмотром + авто-парсинг поста),
              /cardstats, /priority, /addpriority, /removepriority,
              /addartistid, /changeartistid, /removeartistid
"""
import logging
import re
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from states import CardBrowseStates, AddCardStates
from keyboards.cards_kb import (
    card_keyboard, card_author_filter_keyboard,
    adm_addcard_source_kb, adm_addcard_preview_kb,
    adm_addcard_edit_choose_kb, adm_addcard_skip_kb,
    adm_addcard_category_kb, adm_addcard_author_kb,
    adm_panel_kb,
)
from keyboards.main_kb import main_keyboard
from services.user_service import is_user_banned, get_or_create_user
from services.card_service import (
    get_active_cards, get_card, vote_card, report_card,
    get_artist_by_id, get_artist_by_user,
    create_card, set_priority, get_priority_cards,
    get_card_stats, add_artist, change_artist_id, remove_artist,
)
from config import ADMIN_GROUP_ID

router = Router()
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ════════════════════════════════════════════════════════

def _build_card_caption(card: dict, artist_id: Optional[int] = None) -> str:
    """Строит подпись карточки без баланса."""
    import random
    from config import CARD_EMOJIS
    emoji     = card.get("emoji") or random.choice(CARD_EMOJIS)
    pub_id    = card.get("public_id", "?")
    rating    = card.get("rating", 0)
    category  = card.get("category") or "—"
    desc      = card.get("description") or ""
    post_url  = card.get("post_url") or ""
    author_str = f"Автор: id{artist_id}" if artist_id else "Автор: —"
    link_str   = f"\n🔗 {post_url}" if post_url else ""
    return (
        f"{emoji} {pub_id} ♥️{rating} #️⃣{category}\n"
        f"{desc}\n"
        f"{author_str}{link_str}"
    )


async def _show_card(msg: Message, card: dict, edit: bool = False) -> None:
    """Отображает карточку пользователю (без баланса)."""
    artist = (
        await get_artist_by_id(card["author_id"])
        if card.get("author_id") else None
    )
    caption  = _build_card_caption(card, artist["artist_id"] if artist else None)
    kb       = card_keyboard(card["id"])
    file_id  = card.get("file_id")
    ftype    = card.get("file_type", "photo")

    try:
        if file_id:
            if ftype == "audio":
                await msg.answer_audio(file_id, caption=caption, reply_markup=kb)
            else:
                await msg.answer_photo(file_id, caption=caption, reply_markup=kb)
        else:
            if edit:
                await msg.edit_text(caption, reply_markup=kb)
            else:
                await msg.answer(caption, reply_markup=kb)
    except Exception:
        await msg.answer(caption, reply_markup=kb)


def _parse_tg_post_url(url: str) -> Optional[tuple[str, int]]:
    """
    Парсит ссылку на пост Telegram-канала.
    Поддерживает:
      https://t.me/channelname/123
      https://t.me/c/1234567890/123
    Возвращает (chat_id_str, message_id) или None.
    """
    m = re.match(r"https?://t\.me/c/(\d+)/(\d+)", url)
    if m:
        return f"-100{m.group(1)}", int(m.group(2))
    m = re.match(r"https?://t\.me/([^/]+)/(\d+)", url)
    if m:
        return f"@{m.group(1)}", int(m.group(2))
    return None


async def _fetch_post(bot: Bot, url: str, admin_chat_id: int) -> Optional[dict]:
    """
    Пересылает пост из канала в чат администратора,
    извлекает file_id / file_type / caption, удаляет пересланное.
    Возвращает dict с ключами file_id, file_type, description или None.
    """
    parsed = _parse_tg_post_url(url)
    if not parsed:
        return None
    chat_id_str, msg_id = parsed
    try:
        fwd = await bot.forward_message(
            chat_id=admin_chat_id,
            from_chat_id=chat_id_str,
            message_id=msg_id,
        )
    except Exception as e:
        logger.warning("Cannot forward post %s: %s", url, e)
        return None

    result: dict = {"file_id": None, "file_type": None, "description": None}

    if fwd.photo:
        result["file_id"]   = fwd.photo[-1].file_id
        result["file_type"] = "photo"
    elif fwd.audio:
        result["file_id"]   = fwd.audio.file_id
        result["file_type"] = "audio"
    elif fwd.document:
        result["file_id"]   = fwd.document.file_id
        result["file_type"] = "document"
    elif fwd.video:
        result["file_id"]   = fwd.video.file_id
        result["file_type"] = "video"

    result["description"] = fwd.caption or fwd.text or None

    try:
        await fwd.delete()
    except Exception:
        pass

    return result


# ════════════════════════════════════════════════════════
#  ПОЛЬЗОВАТЕЛЬ — просмотр карточек
# ════════════════════════════════════════════════════════

@router.callback_query(F.data == "cards_browse")
async def cards_browse_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    cards = await get_active_cards()
    if not cards:
        await callback.message.edit_text(
            "🎴 Карточек пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
            ])
        )
        await callback.answer()
        return

    card_ids = [c["id"] for c in cards]
    await state.set_state(CardBrowseStates.browsing)
    await state.update_data(card_ids=card_ids, card_index=0)
    await _show_card(callback.message, cards[0], edit=True)
    await callback.answer()


@router.callback_query(CardBrowseStates.browsing, F.data == "card_next")
async def card_next(callback: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    card_ids: list = data.get("card_ids", [])
    index    = (data.get("card_index", 0) + 1) % len(card_ids)
    await state.update_data(card_index=index)
    card = await get_card(card_ids[index])
    if not card or card["status"] != "active":
        await callback.answer("⚠️ Карточка недоступна.", show_alert=True)
        return
    await _show_card(callback.message, card, edit=True)
    await callback.answer()


@router.callback_query(CardBrowseStates.browsing, F.data == "card_prev")
async def card_prev(callback: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    card_ids: list = data.get("card_ids", [])
    index    = (data.get("card_index", 0) - 1) % len(card_ids)
    await state.update_data(card_index=index)
    card = await get_card(card_ids[index])
    if not card or card["status"] != "active":
        await callback.answer("⚠️ Карточка недоступна.", show_alert=True)
        return
    await _show_card(callback.message, card, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("card_vote_"))
async def card_vote(callback: CallbackQuery):
    # card_vote_<id>_<vote>  (vote может быть отрицательным: -3)
    parts   = callback.data.split("_")   # ['card','vote','123','-3']
    card_id = int(parts[2])
    vote    = int(parts[3])
    _, new_rating = await vote_card(card_id, callback.from_user.id, vote)
    sign = "+" if vote > 0 else ""
    await callback.answer(f"{sign}{vote} | Рейтинг: {new_rating}♥️")


@router.callback_query(F.data.startswith("card_author_"))
async def card_author_info(callback: CallbackQuery):
    card_id = int(callback.data.split("_")[2])
    card    = await get_card(card_id)
    if not card or not card.get("author_id"):
        await callback.answer("Автор неизвестен.", show_alert=True)
        return
    artist = await get_artist_by_id(card["author_id"])
    if not artist:
        await callback.answer("Автор не найден.", show_alert=True)
        return
    await callback.message.reply(
        f"💫 Автор: id{artist['artist_id']}",
        reply_markup=card_author_filter_keyboard(artist["artist_id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("card_filter_author_"))
async def card_filter_author(callback: CallbackQuery, state: FSMContext):
    artist_id = int(callback.data.split("_")[3])
    cards     = await get_active_cards(author_id=artist_id)
    if not cards:
        await callback.answer("У этого автора нет карточек.", show_alert=True)
        return
    card_ids = [c["id"] for c in cards]
    await state.set_state(CardBrowseStates.browsing)
    await state.update_data(card_ids=card_ids, card_index=0)
    await _show_card(callback.message, cards[0], edit=False)
    await callback.answer()


@router.callback_query(F.data == "card_back_to_current")
async def card_back_to_current(callback: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    card_ids = data.get("card_ids", [])
    index    = data.get("card_index", 0)
    if card_ids:
        card = await get_card(card_ids[index])
        if card:
            await _show_card(callback.message, card, edit=False)
    await callback.answer()


@router.callback_query(F.data.startswith("card_report_"))
async def card_report_cb(callback: CallbackQuery, bot: Bot):
    card_id = int(callback.data.split("_")[2])
    await report_card(card_id, callback.from_user.id)
    card = await get_card(card_id)
    uid  = callback.from_user.id
    user = await get_or_create_user(uid, callback.from_user.username)
    uname = f"@{user['username']}" if user.get("username") else f"ID:{uid}"
    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"‼️ ЖАЛОБА НА КАРТОЧКУ\n\n"
            f"Карточка: #{card['public_id'] if card else '?'} (id={card_id})\n"
            f"От: {uname}",
        )
    except Exception:
        pass
    await callback.answer("‼️ Жалоба отправлена", show_alert=True)


# ════════════════════════════════════════════════════════
#  АДМИН — /addcard   (FSM с уникальными adm_ callback)
# ════════════════════════════════════════════════════════

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="adm_addcard_cancel")]
    ])


# ── Запуск ───────────────────────────────────────────────

@router.message(F.text == "/addcard", F.chat.id == ADMIN_GROUP_ID)
async def cmd_addcard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AddCardStates.enter_post_url)
    await message.reply(
        "➕ ДОБАВЛЕНИЕ КАРТОЧКИ\n\n"
        "Выбери способ добавления:",
        reply_markup=adm_addcard_source_kb(),
    )


# ── Кнопки выбора источника ───────────────────────────────

@router.callback_query(AddCardStates.enter_post_url, F.data == "adm_addcard_src_url")
async def addcard_src_url(callback: CallbackQuery, state: FSMContext):
    await state.update_data(source="url")
    await callback.message.edit_text(
        "🔗 Отправь ссылку на пост канала (например https://t.me/channel/123):",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@router.callback_query(AddCardStates.enter_post_url, F.data == "adm_addcard_src_manual")
async def addcard_src_manual(callback: CallbackQuery, state: FSMContext):
    await state.update_data(source="manual", post_url=None, file_id=None,
                            file_type=None, description=None)
    await state.set_state(AddCardStates.edit_file)
    await callback.message.edit_text(
        "🖼 Отправь медиафайл (фото / аудио / документ) или нажми «Пропустить»:",
        reply_markup=adm_addcard_skip_kb("adm_addcard_cancel"),
    )
    await callback.answer()


# ── Получение URL и авто-парсинг ─────────────────────────

@router.message(AddCardStates.enter_post_url, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_url(message: Message, state: FSMContext, bot: Bot):
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.reply("❗ Отправь корректную ссылку (https://t.me/...)",
                            reply_markup=_back_kb())
        return

    await message.reply("⏳ Получаю данные поста...")
    fetched = await _fetch_post(bot, url, message.chat.id)

    if not fetched:
        await message.reply(
            "⚠️ Не удалось получить пост автоматически.\n"
            "Убедись, что бот добавлен в канал как администратор.\n\n"
            "Продолжаем в ручном режиме:",
            reply_markup=adm_addcard_source_kb(),
        )
        return

    await state.update_data(
        post_url    = url,
        file_id     = fetched["file_id"],
        file_type   = fetched["file_type"],
        description = fetched["description"],
        source      = "url",
    )
    await _send_preview(message, state, bot)


async def _send_preview(message: Message, state: FSMContext, bot: Bot):
    """Отправляет предпросмотр карточки администратору."""
    await state.set_state(AddCardStates.preview)
    data = await state.get_data()

    caption = (
        f"👁 ПРЕДПРОСМОТР КАРТОЧКИ\n\n"
        f"📝 Описание: {data.get('description') or '—'}\n"
        f"🖼 Медиа: {'есть' if data.get('file_id') else 'нет'}\n"
        f"🔗 Источник: {data.get('post_url') or 'вручную'}"
    )
    file_id = data.get("file_id")
    ftype   = data.get("file_type", "photo")
    kb      = adm_addcard_preview_kb()

    try:
        if file_id:
            if ftype == "audio":
                await message.answer_audio(file_id, caption=caption, reply_markup=kb)
            else:
                await message.answer_photo(file_id, caption=caption, reply_markup=kb)
        else:
            await message.answer(caption, reply_markup=kb)
    except Exception:
        await message.answer(caption, reply_markup=kb)


# ── Кнопки предпросмотра ─────────────────────────────────

@router.callback_query(AddCardStates.preview, F.data == "adm_addcard_preview_keep")
async def addcard_preview_keep(callback: CallbackQuery, state: FSMContext):
    """Оставить данные → переходим к категории."""
    await state.set_state(AddCardStates.enter_category)
    await callback.message.reply(
        "🏷 Введи категорию карточки:",
        reply_markup=adm_addcard_category_kb(),
    )
    await callback.answer()


@router.callback_query(AddCardStates.preview, F.data == "adm_addcard_preview_edit")
async def addcard_preview_edit(callback: CallbackQuery, state: FSMContext):
    """Изменить → показываем выбор что редактировать."""
    await callback.message.edit_reply_markup(reply_markup=adm_addcard_edit_choose_kb())
    await callback.answer()


@router.callback_query(AddCardStates.preview, F.data == "adm_addcard_back_preview")
async def addcard_back_to_preview(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await _send_preview_from_cb(callback, state)


async def _send_preview_from_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.preview)
    data    = await state.get_data()
    caption = (
        f"👁 ПРЕДПРОСМОТР КАРТОЧКИ\n\n"
        f"📝 Описание: {data.get('description') or '—'}\n"
        f"🖼 Медиа: {'есть' if data.get('file_id') else 'нет'}\n"
        f"🔗 Источник: {data.get('post_url') or 'вручную'}"
    )
    file_id = data.get("file_id")
    ftype   = data.get("file_type", "photo")
    kb      = adm_addcard_preview_kb()
    try:
        if file_id:
            if ftype == "audio":
                await callback.message.answer_audio(file_id, caption=caption, reply_markup=kb)
            else:
                await callback.message.answer_photo(file_id, caption=caption, reply_markup=kb)
        else:
            await callback.message.edit_text(caption, reply_markup=kb)
    except Exception:
        await callback.message.answer(caption, reply_markup=kb)
    await callback.answer()


# ── Редактирование медиа ──────────────────────────────────

@router.callback_query(
    F.data == "adm_addcard_edit_file",
    F.message.chat.id == ADMIN_GROUP_ID,
)
async def addcard_edit_file_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.edit_file)
    await callback.message.reply(
        "🖼 Отправь новый медиафайл (фото / аудио / документ):",
        reply_markup=adm_addcard_skip_kb("adm_addcard_back_preview"),
    )
    await callback.answer()


@router.callback_query(AddCardStates.edit_file, F.data == "adm_addcard_skip")
async def addcard_skip_file(callback: CallbackQuery, state: FSMContext):
    """Пропустить медиа — идём к описанию (или к предпросмотру если уже есть данные)."""
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.edit_desc)
        await callback.message.edit_text(
            "📝 Введи описание карточки:",
            reply_markup=adm_addcard_skip_kb("adm_addcard_cancel"),
        )
    else:
        await _send_preview_from_cb(callback, state)
    await callback.answer()


@router.message(AddCardStates.edit_file, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_file(message: Message, state: FSMContext):
    file_id, ftype = None, None
    if message.photo:
        file_id = message.photo[-1].file_id
        ftype   = "photo"
    elif message.audio:
        file_id = message.audio.file_id
        ftype   = "audio"
    elif message.document:
        file_id = message.document.file_id
        ftype   = "document"
    elif message.video:
        file_id = message.video.file_id
        ftype   = "video"
    else:
        await message.reply("❗ Отправь медиафайл или нажми «Пропустить».")
        return

    await state.update_data(file_id=file_id, file_type=ftype)
    data = await state.get_data()

    if data.get("source") == "manual":
        await state.set_state(AddCardStates.edit_desc)
        await message.reply(
            "📝 Введи описание карточки:",
            reply_markup=adm_addcard_skip_kb("adm_addcard_cancel"),
        )
    else:
        # Редактируем уже существующий preview — возвращаемся к нему
        await state.set_state(AddCardStates.preview)
        await message.reply("✅ Медиа обновлено.", reply_markup=adm_addcard_preview_kb())


# ── Редактирование описания ───────────────────────────────

@router.callback_query(
    F.data == "adm_addcard_edit_desc",
    F.message.chat.id == ADMIN_GROUP_ID,
)
async def addcard_edit_desc_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.edit_desc)
    await callback.message.reply(
        "📝 Введи новое описание карточки:",
        reply_markup=adm_addcard_skip_kb("adm_addcard_back_preview"),
    )
    await callback.answer()


@router.callback_query(AddCardStates.edit_desc, F.data == "adm_addcard_skip")
async def addcard_skip_desc(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.enter_category)
        await callback.message.edit_text(
            "🏷 Введи категорию карточки:",
            reply_markup=adm_addcard_category_kb(),
        )
    else:
        await _send_preview_from_cb(callback, state)
    await callback.answer()


@router.message(AddCardStates.edit_desc, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.enter_category)
        await message.reply(
            "🏷 Введи категорию карточки:",
            reply_markup=adm_addcard_category_kb(),
        )
    else:
        await state.set_state(AddCardStates.preview)
        await message.reply("✅ Описание обновлено.", reply_markup=adm_addcard_preview_kb())


# ── Категория ─────────────────────────────────────────────

@router.message(AddCardStates.enter_category, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_category(message: Message, state: FSMContext):
    await state.update_data(category=(message.text or "").strip())
    await state.set_state(AddCardStates.enter_author_id)
    await message.reply(
        "👤 Введи artist_id автора (число 1–9999)\nили нажми «Без автора»:",
        reply_markup=adm_addcard_author_kb(),
    )


# ── Автор ─────────────────────────────────────────────────

@router.callback_query(AddCardStates.enter_author_id, F.data == "adm_addcard_no_author")
async def addcard_no_author(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(author_id=None)
    await _finalize_card(callback.message, state)
    await callback.answer()


@router.message(AddCardStates.enter_author_id, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_author(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    author_db_id = None
    if txt.isdigit():
        artist = await get_artist_by_id(int(txt))
        if artist:
            author_db_id = artist["id"]
        else:
            await message.reply(
                f"⚠️ artist_id {txt} не найден. Введи другой или нажми «Без автора»:",
                reply_markup=adm_addcard_author_kb(),
            )
            return
    else:
        await message.reply("❗ Введи число или нажми «Без автора».",
                            reply_markup=adm_addcard_author_kb())
        return

    await state.update_data(author_id=author_db_id)
    await _finalize_card(message, state)


async def _finalize_card(msg: Message, state: FSMContext):
    """Сохраняет карточку в БД и сообщает результат."""
    data = await state.get_data()
    await state.clear()
    card_id, public_id = await create_card(
        author_id   = data.get("author_id"),
        file_id     = data.get("file_id"),
        file_type   = data.get("file_type"),
        description = data.get("description"),
        category    = data.get("category"),
        post_url    = data.get("post_url"),
    )
    await msg.reply(
        f"✅ Карточка создана!\n"
        f"Внутренний ID: {card_id} · Публичный: #{public_id}\n"
        f"Категория: {data.get('category') or '—'}",
        reply_markup=adm_panel_kb(),
    )
    logger.info("Card %s (#%s) created", card_id, public_id)


# ── Общая отмена / «Назад» ────────────────────────────────

@router.callback_query(F.data == "adm_addcard_cancel", F.message.chat.id == ADMIN_GROUP_ID)
async def addcard_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание карточки отменено.\n\n"
        "Используй /addcard чтобы начать заново.",
    )
    await callback.answer()


@router.callback_query(F.data == "adm_done", F.message.chat.id == ADMIN_GROUP_ID)
async def adm_done(callback: CallbackQuery):
    await callback.answer("👍")


# ════════════════════════════════════════════════════════
#  АДМИН — статистика, приоритеты
# ════════════════════════════════════════════════════════

@router.message(F.text == "/cardstats", F.chat.id == ADMIN_GROUP_ID)
async def cmd_cardstats(message: Message):
    stats = await get_card_stats()
    def _fmt(rows):
        return "\n".join(
            f"  {r['emoji']} #{r['public_id']} ({r['category'] or '—'}) — {r['rating']}♥️"
            for r in rows
        ) or "  —"
    await message.reply(
        f"📊 СТАТИСТИКА КАРТОЧЕК\n\n"
        f"Карточек: {stats['total_cards']}\n"
        f"Авторов:  {stats['total_artists']}\n\n"
        f"⭐ Топ-5 по ♥️:\n{_fmt(stats['top_liked'])}\n\n"
        f"👎 Топ-5 по дизлайкам:\n{_fmt(stats['top_disliked'])}",
        reply_markup=adm_panel_kb(),
    )


@router.message(F.text == "/priority", F.chat.id == ADMIN_GROUP_ID)
async def cmd_priority_list(message: Message):
    cards = await get_priority_cards()
    if not cards:
        await message.reply("Приоритетных карточек нет.", reply_markup=adm_panel_kb())
        return
    lines = "\n".join(
        f"  #{c['public_id']} {c['emoji']} {c['category'] or '—'}"
        for c in cards
    )
    await message.reply(f"⭐ ПРИОРИТЕТНЫЕ КАРТОЧКИ:\n{lines}", reply_markup=adm_panel_kb())


@router.message(F.text.startswith("/addpriority "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_add_priority(message: Message):
    parts = message.text.split(maxsplit=1)
    if not parts[1].isdigit():
        await message.reply("Использование: /addpriority <card_id>")
        return
    await set_priority(int(parts[1]), True)
    await message.reply(f"⭐ Карточка {parts[1]} в приоритете.", reply_markup=adm_panel_kb())


@router.message(F.text.startswith("/removepriority "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_remove_priority(message: Message):
    parts = message.text.split(maxsplit=1)
    if not parts[1].isdigit():
        await message.reply("Использование: /removepriority <card_id>")
        return
    await set_priority(int(parts[1]), False)
    await message.reply(f"Карточка {parts[1]} убрана из приоритета.", reply_markup=adm_panel_kb())


# ════════════════════════════════════════════════════════
#  АДМИН — авторы
# ════════════════════════════════════════════════════════

@router.message(F.text == "/addartistid", F.chat.id == ADMIN_GROUP_ID)
async def cmd_addartistid(message: Message):
    uid      = message.from_user.id
    existing = await get_artist_by_user(uid)
    if existing:
        await message.reply(
            f"У вас уже есть artist_id: {existing['artist_id']}\n"
            f"Используй /changeartistid чтобы изменить.",
            reply_markup=adm_panel_kb(),
        )
        return
    aid = await add_artist(uid)
    await message.reply(f"✅ Ваш artist_id: {aid}", reply_markup=adm_panel_kb())


@router.message(F.text.startswith("/changeartistid "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_changeartistid(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.reply("Использование: /changeartistid <old_id> <new_id>")
        return
    ok = await change_artist_id(int(parts[1]), int(parts[2]))
    if ok:
        await message.reply(
            f"✅ artist_id {parts[1]} → {parts[2]}",
            reply_markup=adm_panel_kb(),
        )
    else:
        await message.reply("❌ Ошибка: ID уже занят или не существует.")


@router.message(F.text == "/removeartistid", F.chat.id == ADMIN_GROUP_ID)
async def cmd_removeartistid(message: Message):
    await remove_artist(message.from_user.id)
    await message.reply("✅ artist_id удалён.", reply_markup=adm_panel_kb())

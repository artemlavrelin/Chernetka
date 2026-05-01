"""
handlers/cards.py

Пользователи: просмотр карточек, голоса, автор-фильтр, жалобы (с причиной + cooldown).
Админы: /addcard FSM (авто-парсинг + предпросмотр), /cardstats, /priority,
        /addartistid, /editartist, /removeartistid, /changeartistid.
"""
import logging
import re
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from states import CardBrowseStates, AddCardStates, AddArtistStates, EditArtistStates
from keyboards.cards_kb import (
    card_keyboard, card_author_filter_keyboard,
    adm_addcard_source_kb, adm_addcard_preview_kb,
    adm_addcard_edit_choose_kb, adm_addcard_skip_kb,
    adm_addcard_category_kb, adm_addcard_author_kb,
    adm_panel_kb,
    adm_artist_skip_kb, adm_editartist_choose_kb, adm_editartist_field_kb,
)
from services.user_service import is_user_banned, get_or_create_user
from services.card_service import (
    get_active_cards, get_card, vote_card, report_card, check_report_cooldown,
    get_artist_by_id, get_artist_by_user, get_artist_by_db_id, update_artist_fields,
    create_card, set_priority, get_priority_cards,
    get_card_stats, add_artist, change_artist_id, remove_artist,
)
from config import ADMIN_GROUP_ID

router = Router()
logger = logging.getLogger(__name__)


# ─── Inline state для ввода причины жалобы ──────────────────────────────────
class ReportCardState(StatesGroup):
    enter_reason = State()


# ════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ════════════════════════════════════════════════════════

def _artist_label(artist: dict) -> str:
    """Строит метку автора: display_id (@username если есть)."""
    did   = artist.get("display_id") or str(artist["artist_id"])
    uname = artist.get("tg_username")
    return f"{did} (@{uname.lstrip('@')})" if uname else did


def _build_card_caption(card: dict, artist: Optional[dict] = None) -> str:
    """Подпись карточки — без баланса, без служебных заголовков."""
    import random
    from config import CARD_EMOJIS
    emoji    = card.get("emoji") or random.choice(CARD_EMOJIS)
    pub_id   = card.get("public_id", "?")
    rating   = card.get("rating", 0)
    category = card.get("category") or "—"
    desc     = card.get("description") or ""
    post_url = card.get("post_url") or ""

    if artist:
        did   = artist.get("display_id") or str(artist["artist_id"])
        alink = artist.get("link")
        uname = artist.get("tg_username")
        if alink:
            author_str = f'Автор: <a href="{alink}">{did}</a>'
        elif uname:
            author_str = f"Автор: {did} (@{uname.lstrip('@')})"
        else:
            author_str = f"Автор: {did}"
    else:
        author_str = "Автор: —"

    source_line = f"\n📌 Источник: {post_url}" if post_url else ""
    return (
        f"{emoji} {pub_id} ♥️{rating} #️⃣{category}\n"
        f"{desc}\n"
        f"{author_str}{source_line}"
    )


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="adm_addcard_cancel")]
    ])


def _nav_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])


async def _show_card(msg: Message, card: dict, edit: bool = False) -> None:
    artist  = await get_artist_by_db_id(card["author_id"]) if card.get("author_id") else None
    caption = _build_card_caption(card, artist)
    kb      = card_keyboard(card["id"])
    file_id = card.get("file_id")
    ftype   = card.get("file_type", "photo")
    try:
        if file_id:
            if ftype == "audio":
                await msg.answer_audio(file_id, caption=caption, reply_markup=kb)
            else:
                await msg.answer_photo(file_id, caption=caption, reply_markup=kb)
        else:
            if edit:
                await msg.edit_text(caption, reply_markup=kb, disable_web_page_preview=True)
            else:
                await msg.answer(caption, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await msg.answer(caption, reply_markup=kb, disable_web_page_preview=True)


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
            reply_markup=_nav_back_kb(),
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
    card_ids = data.get("card_ids", [])
    index    = data.get("card_index", 0) + 1

    if index >= len(card_ids):
        # Конец — не зацикливаем
        await state.clear()
        await callback.message.edit_text(
            "🎴 Карточки закончились.\n\nЧтобы посмотреть ещё раз — нажмите «Старт».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Старт", callback_data="cards_browse")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
            ]),
        )
        await callback.answer()
        return

    await state.update_data(card_index=index)
    card = await get_card(card_ids[index])
    if not card or card["status"] != "active":
        # Пропускаем недоступную карточку
        await state.update_data(card_index=index)
        await callback.answer()
        return
    await _show_card(callback.message, card, edit=True)
    await callback.answer()


@router.callback_query(CardBrowseStates.browsing, F.data == "card_prev")
async def card_prev(callback: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    card_ids = data.get("card_ids", [])
    index    = max(0, data.get("card_index", 0) - 1)
    await state.update_data(card_index=index)
    card = await get_card(card_ids[index])
    if not card or card["status"] != "active":
        await callback.answer("⚠️ Карточка недоступна.", show_alert=True)
        return
    await _show_card(callback.message, card, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("card_vote_"))
async def card_vote(callback: CallbackQuery):
    parts   = callback.data.split("_")   # card_vote_<id>_<vote>
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
    artist = await get_artist_by_db_id(card["author_id"])
    if not artist:
        await callback.answer("Автор не найден.", show_alert=True)
        return
    label = _artist_label(artist)
    alink = artist.get("link")
    lines = [f"💫 Автор: {label}"]
    if alink:
        lines.append(f"🔗 {alink}")
    await callback.message.reply(
        "\n".join(lines),
        reply_markup=card_author_filter_keyboard(artist["artist_id"]),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("card_filter_author_"))
async def card_filter_author(callback: CallbackQuery, state: FSMContext):
    artist_id = int(callback.data.split("_")[3])
    artist    = await get_artist_by_id(artist_id)
    if not artist:
        await callback.answer("Автор не найден.", show_alert=True)
        return
    cards = await get_active_cards(author_id=artist["id"])
    if not cards:
        await callback.answer("У этого автора нет активных карточек.", show_alert=True)
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


# ── Жалобы (с причиной + cooldown 30 мин) ───────────────────────────────────

@router.callback_query(F.data.startswith("card_report_"))
async def card_report_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    card_id = int(callback.data.split("_")[2])

    can_report, remaining = await check_report_cooldown(user_id)
    if not can_report:
        m = remaining // 60
        await callback.answer(
            f"⏳ Следующая жалоба доступна через {m} мин.", show_alert=True
        )
        return

    await state.set_state(ReportCardState.enter_reason)
    await state.update_data(report_card_id=card_id)
    await callback.message.reply(
        "‼️ ЖАЛОБА НА КАРТОЧКУ\n\nОпиши причину жалобы:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="card_report_cancel")]
        ]),
    )
    await callback.answer()


@router.callback_query(ReportCardState.enter_reason, F.data == "card_report_cancel")
async def card_report_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Жалоба отменена.")
    await callback.answer()


@router.message(ReportCardState.enter_reason)
async def card_report_receive_reason(message: Message, state: FSMContext, bot: Bot):
    reason  = (message.text or "").strip()
    if not reason:
        await message.reply("❗ Введи причину жалобы.")
        return

    data    = await state.get_data()
    card_id = data.get("report_card_id")
    await state.clear()

    uid  = message.from_user.id
    card = await get_card(card_id)
    user = await get_or_create_user(uid, message.from_user.username)
    uname = f"@{user['username']}" if user.get("username") else f"ID:{uid}"

    await report_card(card_id, uid, reason)

    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"‼️ ЖАЛОБА НА КАРТОЧКУ\n\n"
            f"Карточка: #{card['public_id'] if card else '?'} (id={card_id})\n"
            f"От: {uname} (ID: {uid})\n\n"
            f"Причина:\n{reason}",
        )
    except Exception:
        pass

    await message.reply("✅ Жалоба отправлена администраторам.")


# ════════════════════════════════════════════════════════
#  АДМИН — /addcard  (FSM с авто-парсингом + предпросмотром)
# ════════════════════════════════════════════════════════

def _parse_tg_post_url(url: str) -> Optional[tuple[str, int]]:
    m = re.match(r"https?://t\.me/c/(\d+)/(\d+)", url)
    if m:
        return f"-100{m.group(1)}", int(m.group(2))
    m = re.match(r"https?://t\.me/([^/]+)/(\d+)", url)
    if m:
        return f"@{m.group(1)}", int(m.group(2))
    return None


async def _fetch_post(bot: Bot, url: str, admin_chat_id: int) -> Optional[dict]:
    parsed = _parse_tg_post_url(url)
    if not parsed:
        return None
    chat_id_str, msg_id = parsed
    try:
        fwd = await bot.forward_message(
            chat_id=admin_chat_id, from_chat_id=chat_id_str, message_id=msg_id,
        )
    except Exception as e:
        logger.warning("Cannot forward post %s: %s", url, e)
        return None

    result = {"file_id": None, "file_type": None, "description": None}
    if fwd.photo:
        result.update(file_id=fwd.photo[-1].file_id, file_type="photo")
    elif fwd.audio:
        result.update(file_id=fwd.audio.file_id, file_type="audio")
    elif fwd.document:
        result.update(file_id=fwd.document.file_id, file_type="document")
    elif fwd.video:
        result.update(file_id=fwd.video.file_id, file_type="video")

    # Берём только оригинальное описание без служебного текста
    raw_desc = fwd.caption or fwd.text or None
    result["description"] = raw_desc
    try:
        await fwd.delete()
    except Exception:
        pass
    return result


async def _send_preview(msg: Message, state: FSMContext):
    await state.set_state(AddCardStates.preview)
    data    = await state.get_data()
    # Чистое описание без служебных заголовков
    desc    = data.get("description") or "—"
    file_id = data.get("file_id")
    ftype   = data.get("file_type", "photo")
    src     = data.get("post_url") or "вручную"

    caption = (
        f"👁 Предпросмотр\n\n"
        f"📝 {desc}\n"
        f"📌 Источник: {src}\n"
        f"🖼 Медиа: {'есть' if file_id else 'нет'}"
    )
    kb = adm_addcard_preview_kb()
    try:
        if file_id:
            if ftype == "audio":
                await msg.answer_audio(file_id, caption=caption, reply_markup=kb)
            else:
                await msg.answer_photo(file_id, caption=caption, reply_markup=kb)
        else:
            await msg.answer(caption, reply_markup=kb)
    except Exception:
        await msg.answer(caption, reply_markup=kb)


@router.message(F.text == "/addcard", F.chat.id == ADMIN_GROUP_ID)
async def cmd_addcard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AddCardStates.enter_post_url)
    await message.reply("➕ ДОБАВЛЕНИЕ КАРТОЧКИ\n\nВыбери способ:", reply_markup=adm_addcard_source_kb())


@router.callback_query(AddCardStates.enter_post_url, F.data == "adm_addcard_src_url")
async def addcard_src_url(callback: CallbackQuery, state: FSMContext):
    await state.update_data(source="url")
    await callback.message.edit_text(
        "🔗 Отправь ссылку на пост канала (https://t.me/channel/123):", reply_markup=_back_kb()
    )
    await callback.answer()


@router.callback_query(AddCardStates.enter_post_url, F.data == "adm_addcard_src_manual")
async def addcard_src_manual(callback: CallbackQuery, state: FSMContext):
    await state.update_data(source="manual", post_url=None, file_id=None, file_type=None, description=None)
    await state.set_state(AddCardStates.edit_file)
    await callback.message.edit_text(
        "🖼 Отправь медиафайл или нажми «Пропустить»:",
        reply_markup=adm_addcard_skip_kb("adm_addcard_cancel"),
    )
    await callback.answer()


@router.message(AddCardStates.enter_post_url, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_url(message: Message, state: FSMContext, bot: Bot):
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.reply("❗ Отправь ссылку (https://t.me/...)", reply_markup=_back_kb())
        return
    await message.reply("⏳ Получаю данные поста...")
    fetched = await _fetch_post(bot, url, message.chat.id)
    if not fetched:
        await message.reply(
            "⚠️ Не удалось получить пост автоматически.\n"
            "Убедись что бот — администратор канала.\n\n"
            "Переключаемся в ручной режим:",
            reply_markup=adm_addcard_source_kb(),
        )
        return
    await state.update_data(
        post_url=url, source="url",
        file_id=fetched["file_id"], file_type=fetched["file_type"],
        description=fetched["description"],
    )
    await _send_preview(message, state)


# ── Предпросмотр ─────────────────────────────────────────

@router.callback_query(AddCardStates.preview, F.data == "adm_addcard_preview_keep")
async def addcard_preview_keep(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.enter_category)
    await callback.message.reply("🏷 Введи категорию:", reply_markup=adm_addcard_category_kb())
    await callback.answer()


@router.callback_query(AddCardStates.preview, F.data == "adm_addcard_preview_edit")
async def addcard_preview_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=adm_addcard_edit_choose_kb())
    await callback.answer()


@router.callback_query(AddCardStates.preview, F.data == "adm_addcard_back_preview")
async def addcard_back_to_preview(callback: CallbackQuery, state: FSMContext):
    await _send_preview_from_cb(callback, state)


async def _send_preview_from_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.preview)
    data    = await state.get_data()
    desc    = data.get("description") or "—"
    file_id = data.get("file_id")
    ftype   = data.get("file_type", "photo")
    src     = data.get("post_url") or "вручную"
    caption = (
        f"👁 Предпросмотр\n\n"
        f"📝 {desc}\n"
        f"📌 Источник: {src}\n"
        f"🖼 Медиа: {'есть' if file_id else 'нет'}"
    )
    kb = adm_addcard_preview_kb()
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

@router.callback_query(F.data == "adm_addcard_edit_file", F.message.chat.id == ADMIN_GROUP_ID)
async def addcard_edit_file_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.edit_file)
    await callback.message.reply(
        "🖼 Отправь новый медиафайл:",
        reply_markup=adm_addcard_skip_kb("adm_addcard_back_preview"),
    )
    await callback.answer()


@router.callback_query(AddCardStates.edit_file, F.data == "adm_addcard_skip")
async def addcard_skip_file(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.edit_desc)
        await callback.message.edit_text(
            "📝 Введи описание:", reply_markup=adm_addcard_skip_kb("adm_addcard_cancel")
        )
    else:
        await _send_preview_from_cb(callback, state)
    await callback.answer()


@router.message(AddCardStates.edit_file, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_file(message: Message, state: FSMContext):
    file_id, ftype = None, None
    if message.photo:
        file_id, ftype = message.photo[-1].file_id, "photo"
    elif message.audio:
        file_id, ftype = message.audio.file_id, "audio"
    elif message.document:
        file_id, ftype = message.document.file_id, "document"
    elif message.video:
        file_id, ftype = message.video.file_id, "video"
    else:
        await message.reply("❗ Отправь медиафайл или нажми «Пропустить».")
        return
    await state.update_data(file_id=file_id, file_type=ftype)
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.edit_desc)
        await message.reply("📝 Введи описание:", reply_markup=adm_addcard_skip_kb("adm_addcard_cancel"))
    else:
        await state.set_state(AddCardStates.preview)
        await message.reply("✅ Медиа обновлено.", reply_markup=adm_addcard_preview_kb())


# ── Редактирование описания ───────────────────────────────

@router.callback_query(F.data == "adm_addcard_edit_desc", F.message.chat.id == ADMIN_GROUP_ID)
async def addcard_edit_desc_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCardStates.edit_desc)
    await callback.message.reply(
        "📝 Введи описание:", reply_markup=adm_addcard_skip_kb("adm_addcard_back_preview")
    )
    await callback.answer()


@router.callback_query(AddCardStates.edit_desc, F.data == "adm_addcard_skip")
async def addcard_skip_desc(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.enter_category)
        await callback.message.edit_text("🏷 Введи категорию:", reply_markup=adm_addcard_category_kb())
    else:
        await _send_preview_from_cb(callback, state)
    await callback.answer()


@router.message(AddCardStates.edit_desc, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    data = await state.get_data()
    if data.get("source") == "manual":
        await state.set_state(AddCardStates.enter_category)
        await message.reply("🏷 Введи категорию:", reply_markup=adm_addcard_category_kb())
    else:
        await state.set_state(AddCardStates.preview)
        await message.reply("✅ Описание обновлено.", reply_markup=adm_addcard_preview_kb())


# ── Категория ─────────────────────────────────────────────

@router.message(AddCardStates.enter_category, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_category(message: Message, state: FSMContext):
    await state.update_data(category=(message.text or "").strip())
    await state.set_state(AddCardStates.enter_author_id)
    await message.reply("👤 Введи artist_id автора (число) или «Без автора»:", reply_markup=adm_addcard_author_kb())


@router.callback_query(AddCardStates.enter_author_id, F.data == "adm_addcard_no_author")
async def addcard_no_author(callback: CallbackQuery, state: FSMContext):
    await state.update_data(author_id=None)
    await _finalize_card(callback.message, state)
    await callback.answer()


@router.message(AddCardStates.enter_author_id, F.chat.id == ADMIN_GROUP_ID)
async def addcard_receive_author(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.reply("❗ Введи числовой artist_id.", reply_markup=adm_addcard_author_kb())
        return
    artist = await get_artist_by_id(int(txt))
    if not artist:
        await message.reply(f"⚠️ artist_id {txt} не найден.", reply_markup=adm_addcard_author_kb())
        return
    await state.update_data(author_id=artist["id"])
    await _finalize_card(message, state)


async def _finalize_card(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    card_id, public_id = await create_card(
        author_id=data.get("author_id"),
        file_id=data.get("file_id"), file_type=data.get("file_type"),
        description=data.get("description"), category=data.get("category"),
        post_url=data.get("post_url"),
    )
    await msg.reply(
        f"✅ Карточка создана!\n"
        f"ID: {card_id} · #{public_id}\n"
        f"Категория: {data.get('category') or '—'}",
        reply_markup=adm_panel_kb(),
    )


@router.callback_query(F.data == "adm_addcard_cancel", F.message.chat.id == ADMIN_GROUP_ID)
async def addcard_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание отменено. /addcard — начать заново.")
    await callback.answer()


@router.callback_query(F.data == "adm_done", F.message.chat.id == ADMIN_GROUP_ID)
async def adm_done(callback: CallbackQuery):
    await callback.answer("👍")


# ════════════════════════════════════════════════════════
#  АДМИН — статистика, приоритеты
# ════════════════════════════════════════════════════════

@router.message(F.text == "/cardstats", F.chat.id == ADMIN_GROUP_ID)
async def cmd_cardstats(message: Message):
    s = await get_card_stats()
    def _fmt(rows):
        return "\n".join(
            f"  {r['emoji']} #{r['public_id']} ({r['category'] or '—'}) — {r['rating']}♥️"
            for r in rows
        ) or "  —"
    await message.reply(
        f"📊 КАРТОЧКИ\n\nКарточек: {s['total_cards']}\nАвторов: {s['total_artists']}\n\n"
        f"⭐ Топ-5:\n{_fmt(s['top_liked'])}\n\n👎 Антирейтинг:\n{_fmt(s['top_disliked'])}",
        reply_markup=adm_panel_kb(),
    )


@router.message(F.text == "/priority", F.chat.id == ADMIN_GROUP_ID)
async def cmd_priority_list(message: Message):
    cards = await get_priority_cards()
    if not cards:
        await message.reply("Приоритетных карточек нет.", reply_markup=adm_panel_kb())
        return
    lines = "\n".join(f"  #{c['public_id']} {c['emoji']} {c['category'] or '—'}" for c in cards)
    await message.reply(f"⭐ ПРИОРИТЕТ:\n{lines}", reply_markup=adm_panel_kb())


@router.message(F.text.startswith("/addpriority "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_add_priority(message: Message):
    p = message.text.split(maxsplit=1)
    if not p[1].isdigit():
        await message.reply("Использование: /addpriority <card_id>")
        return
    await set_priority(int(p[1]), True)
    await message.reply(f"⭐ Карточка {p[1]} в приоритете.", reply_markup=adm_panel_kb())


@router.message(F.text.startswith("/removepriority "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_remove_priority(message: Message):
    p = message.text.split(maxsplit=1)
    if not p[1].isdigit():
        await message.reply("Использование: /removepriority <card_id>")
        return
    await set_priority(int(p[1]), False)
    await message.reply(f"Карточка {p[1]} убрана из приоритета.", reply_markup=adm_panel_kb())


# ════════════════════════════════════════════════════════
#  АДМИН — /addartistid  (FSM 3 шага + artist_id = tg_id)
# ════════════════════════════════════════════════════════

def _artist_info_text(artist: dict) -> str:
    did   = artist.get("display_id") or str(artist["artist_id"])
    uname = artist.get("tg_username") or "—"
    link  = artist.get("link") or "—"
    return (
        f"🎨 АРТИСТ\n\n"
        f"Числовой Artist ID: {artist['artist_id']}\n"
        f"Display ID (TG):    {did}\n"
        f"@Username:          {uname}\n"
        f"Ссылка:             {link}"
    )


@router.message(F.text == "/addartistid", F.chat.id == ADMIN_GROUP_ID)
async def cmd_addartistid(message: Message, state: FSMContext):
    uid      = message.from_user.id
    existing = await get_artist_by_user(uid)
    if existing:
        await message.reply(
            f"У вас уже есть профиль:\n{_artist_info_text(existing)}\n\n/editartist — изменить",
            reply_markup=adm_panel_kb(),
        )
        return
    await state.clear()
    await state.set_state(AddArtistStates.enter_link)
    # display_id = Telegram ID автоматически
    await state.update_data(display_id=str(uid))
    await message.reply(
        f"🎨 СОЗДАНИЕ ПРОФИЛЯ АРТИСТА\n\n"
        f"Display ID установлен автоматически: {uid}\n\n"
        f"Шаг 1/2 — 🔗 Введи ссылку на свой профиль\n"
        f"(Threads, Instagram, SoundCloud и т.д.) или пропусти:",
        reply_markup=adm_artist_skip_kb("adm_artist_cancel"),
    )


@router.callback_query(AddArtistStates.enter_link, F.data == "adm_artist_skip")
async def addartist_skip_link(callback: CallbackQuery, state: FSMContext):
    await state.update_data(link=None)
    await state.set_state(AddArtistStates.enter_username)
    await callback.message.edit_text(
        "Шаг 2/2 — 👤 Введи свой @username или пропусти:",
        reply_markup=adm_artist_skip_kb("adm_artist_cancel"),
    )
    await callback.answer()


@router.message(AddArtistStates.enter_link, F.chat.id == ADMIN_GROUP_ID)
async def addartist_receive_link(message: Message, state: FSMContext):
    link = (message.text or "").strip()
    if not link.startswith("http") and not link.startswith("@"):
        await message.reply("❗ Введи ссылку (https://...) или нажми «Пропустить».",
                            reply_markup=adm_artist_skip_kb("adm_artist_cancel"))
        return
    await state.update_data(link=link)
    await state.set_state(AddArtistStates.enter_username)
    await message.reply(
        "Шаг 2/2 — 👤 Введи свой @username или пропусти:",
        reply_markup=adm_artist_skip_kb("adm_artist_cancel"),
    )


@router.callback_query(AddArtistStates.enter_username, F.data == "adm_artist_skip")
async def addartist_skip_uname(callback: CallbackQuery, state: FSMContext):
    await state.update_data(tg_username=None)
    await _save_new_artist(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(AddArtistStates.enter_username, F.chat.id == ADMIN_GROUP_ID)
async def addartist_receive_uname(message: Message, state: FSMContext):
    uname = (message.text or "").strip().lstrip("@")
    await state.update_data(tg_username=uname or None)
    await _save_new_artist(message, state, message.from_user.id)


async def _save_new_artist(msg: Message, state: FSMContext, user_id: int):
    data   = await state.get_data()
    await state.clear()
    artist = await add_artist(
        user_id     = user_id,
        link        = data.get("link"),
        display_id  = data.get("display_id") or str(user_id),
        tg_username = data.get("tg_username"),
    )
    await msg.reply(f"✅ Профиль создан!\n\n{_artist_info_text(artist)}", reply_markup=adm_panel_kb())


@router.callback_query(F.data == "adm_artist_cancel", F.message.chat.id == ADMIN_GROUP_ID)
async def addartist_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


# ════════════════════════════════════════════════════════
#  АДМИН — /editartist
# ════════════════════════════════════════════════════════

@router.message(F.text == "/editartist", F.chat.id == ADMIN_GROUP_ID)
async def cmd_editartist(message: Message, state: FSMContext):
    artist = await get_artist_by_user(message.from_user.id)
    if not artist:
        await message.reply("❌ Нет профиля артиста. /addartistid — создать.")
        return
    await state.clear()
    await state.set_state(EditArtistStates.choose_field)
    await message.reply(
        f"✏️ РЕДАКТИРОВАНИЕ\n\n{_artist_info_text(artist)}\n\nВыбери поле:",
        reply_markup=adm_editartist_choose_kb(),
    )


@router.callback_query(EditArtistStates.choose_field, F.data == "adm_ea_field_link")
async def ea_field_link(callback: CallbackQuery, state: FSMContext):
    await state.update_data(editing_field="link")
    await state.set_state(EditArtistStates.enter_link)
    await callback.message.edit_text("🔗 Введи новую ссылку:", reply_markup=adm_editartist_field_kb())
    await callback.answer()


@router.callback_query(EditArtistStates.choose_field, F.data == "adm_ea_field_did")
async def ea_field_did(callback: CallbackQuery, state: FSMContext):
    await state.update_data(editing_field="display_id")
    await state.set_state(EditArtistStates.enter_display_id)
    await callback.message.edit_text(
        "🆔 Введи новый Display ID\n(по умолчанию = Telegram ID, можно изменить):",
        reply_markup=adm_editartist_field_kb(),
    )
    await callback.answer()


@router.callback_query(EditArtistStates.choose_field, F.data == "adm_ea_field_uname")
async def ea_field_uname(callback: CallbackQuery, state: FSMContext):
    await state.update_data(editing_field="tg_username")
    await state.set_state(EditArtistStates.enter_username)
    await callback.message.edit_text("👤 Введи новый @username:", reply_markup=adm_editartist_field_kb())
    await callback.answer()


@router.callback_query(F.data == "adm_ea_back_choose", F.message.chat.id == ADMIN_GROUP_ID)
async def ea_back_choose(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditArtistStates.choose_field)
    artist = await get_artist_by_user(callback.from_user.id)
    await callback.message.edit_text(
        f"✏️ РЕДАКТИРОВАНИЕ\n\n{_artist_info_text(artist)}\n\nВыбери поле:",
        reply_markup=adm_editartist_choose_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm_ea_clear", F.message.chat.id == ADMIN_GROUP_ID)
async def ea_clear_field(callback: CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    field = data.get("editing_field", "")
    uid   = callback.from_user.id
    kwargs = {f"clear_{field}": True} if field in ("link", "display_id", "tg_username") else {}
    artist = await update_artist_fields(uid, **kwargs)
    await state.set_state(EditArtistStates.choose_field)
    await callback.message.edit_text(
        f"✅ Поле очищено.\n\n{_artist_info_text(artist)}\n\nВыбери поле:",
        reply_markup=adm_editartist_choose_kb(),
    )
    await callback.answer()


async def _ea_apply(message: Message, state: FSMContext, **kw):
    artist = await update_artist_fields(message.from_user.id, **kw)
    await state.set_state(EditArtistStates.choose_field)
    await message.reply(
        f"✅ Сохранено.\n\n{_artist_info_text(artist)}\n\nВыбери поле:",
        reply_markup=adm_editartist_choose_kb(),
    )


@router.message(EditArtistStates.enter_link, F.chat.id == ADMIN_GROUP_ID)
async def ea_receive_link(message: Message, state: FSMContext):
    link = (message.text or "").strip()
    if not link.startswith("http") and not link.startswith("@"):
        await message.reply("❗ Введи ссылку (https://...).", reply_markup=adm_editartist_field_kb())
        return
    await _ea_apply(message, state, link=link)


@router.message(EditArtistStates.enter_display_id, F.chat.id == ADMIN_GROUP_ID)
async def ea_receive_did(message: Message, state: FSMContext):
    did = (message.text or "").strip()
    if not did:
        await message.reply("❗ Введи Display ID.", reply_markup=adm_editartist_field_kb())
        return
    await _ea_apply(message, state, display_id=did)


@router.message(EditArtistStates.enter_username, F.chat.id == ADMIN_GROUP_ID)
async def ea_receive_uname(message: Message, state: FSMContext):
    uname = (message.text or "").strip().lstrip("@")
    if not uname:
        await message.reply("❗ Введи @username.", reply_markup=adm_editartist_field_kb())
        return
    await _ea_apply(message, state, tg_username=uname)


@router.message(F.text == "/removeartistid", F.chat.id == ADMIN_GROUP_ID)
async def cmd_removeartistid(message: Message, state: FSMContext):
    await state.clear()
    await remove_artist(message.from_user.id)
    await message.reply("✅ Профиль артиста удалён.", reply_markup=adm_panel_kb())

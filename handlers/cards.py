import logging
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaAudio
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import CardBrowseStates, AddCardStates
from keyboards.cards_kb import card_keyboard, card_author_filter_keyboard
from keyboards.main_kb import main_keyboard
from services.user_service import is_user_banned, get_balance, get_or_create_user
from services.card_service import (
    get_active_cards, get_card, vote_card, report_card, get_artist_by_id,
    get_artist_by_user, create_card, set_priority, get_priority_cards,
    get_card_stats, add_artist, change_artist_id, remove_artist,
)
from config import ADMIN_GROUP_ID, is_admin

router = Router()
logger = logging.getLogger(__name__)


def _build_card_caption(card: dict, artist_id: Optional[int] = None) -> str:
    import random
    from config import CARD_EMOJIS
    emoji = card.get("emoji") or random.choice(CARD_EMOJIS)
    pub_id = card.get("public_id", "?")
    rating = card.get("rating", 0)
    category = card.get("category") or "—"
    desc = card.get("description") or ""
    post_url = card.get("post_url") or ""

    author_str = f"Автор: id{artist_id}" if artist_id else "Автор: —"
    link_str = f"\n🔗 {post_url}" if post_url else ""

    return (
        f"{emoji} {pub_id} ♥️{rating} #️⃣{category}\n"
        f"{desc}\n"
        f"{author_str}{link_str}"
    )



@router.callback_query(F.data == "cards_browse")
async def cards_browse_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    cards = await get_active_cards()
    if not cards:
        await callback.message.edit_text(
            "🎴 Карточек пока нет.\n\nBalance: ?🌟",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
            ])
        )
        await callback.answer()
        return

    card_ids = [c["id"] for c in cards]
    await state.set_state(CardBrowseStates.browsing)
    await state.update_data(card_ids=card_ids, card_index=0, author_filter=None)
    await _show_card(callback.message, cards[0], callback.from_user.id, edit=True)
    await callback.answer()


async def _show_card(msg, card: dict, user_id: int, edit: bool = False):
    balance = await get_balance(user_id)
    artist = await get_artist_by_id(card.get("author_id")) if card.get("author_id") else None
    artist_id = artist["artist_id"] if artist else None
    caption = _build_card_caption(card, artist_id) + f"\n\nBalance: {balance}🌟"
    kb = card_keyboard(card["id"])

    file_id = card.get("file_id")
    file_type = card.get("file_type", "photo")

    try:
        if file_id:
            if edit:
                if file_type == "audio":
                    await msg.answer_audio(file_id, caption=caption, reply_markup=kb)
                else:
                    await msg.answer_photo(file_id, caption=caption, reply_markup=kb)
            else:
                if file_type == "audio":
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


@router.callback_query(CardBrowseStates.browsing, F.data == "card_next")
async def card_next(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    card_ids: list = data.get("card_ids", [])
    index: int = data.get("card_index", 0) + 1
    if index >= len(card_ids):
        index = 0  # зацикливаем
    await state.update_data(card_index=index)
    card = await get_card(card_ids[index])
    if not card or card["status"] != "active":
        await callback.answer("⚠️ Карточка недоступна.", show_alert=True)
        return
    await _show_card(callback.message, card, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(CardBrowseStates.browsing, F.data == "card_prev")
async def card_prev(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    card_ids: list = data.get("card_ids", [])
    index: int = data.get("card_index", 0) - 1
    if index < 0:
        index = len(card_ids) - 1
    await state.update_data(card_index=index)
    card = await get_card(card_ids[index])
    if not card or card["status"] != "active":
        await callback.answer("⚠️ Карточка недоступна.", show_alert=True)
        return
    await _show_card(callback.message, card, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("card_vote_"))
async def card_vote(callback: CallbackQuery):
    parts = callback.data.split("_")
    card_id = int(parts[2])
    vote = int(parts[3])
    success, new_rating = await vote_card(card_id, callback.from_user.id, vote)
    sign = "+" if vote > 0 else ""
    await callback.answer(f"{sign}{vote} | Рейтинг: {new_rating}♥️", show_alert=False)


@router.callback_query(F.data.startswith("card_author_"))
async def card_author(callback: CallbackQuery, state: FSMContext):
    card_id = int(callback.data.split("_")[2])
    card = await get_card(card_id)
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
    cards = await get_active_cards(author_id=artist_id)
    if not cards:
        await callback.answer("У этого автора нет карточек.", show_alert=True)
        return
    card_ids = [c["id"] for c in cards]
    await state.set_state(CardBrowseStates.browsing)
    await state.update_data(card_ids=card_ids, card_index=0, author_filter=artist_id)
    await _show_card(callback.message, cards[0], callback.from_user.id, edit=False)
    await callback.answer()


@router.callback_query(F.data == "card_back_to_current")
async def card_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    card_ids = data.get("card_ids", [])
    index = data.get("card_index", 0)
    if not card_ids:
        await callback.answer()
        return
    card = await get_card(card_ids[index])
    if card:
        await _show_card(callback.message, card, callback.from_user.id, edit=False)
    await callback.answer()


@router.callback_query(F.data.startswith("card_report_"))
async def card_report_cb(callback: CallbackQuery, bot: Bot):
    card_id = int(callback.data.split("_")[2])
    await report_card(card_id, callback.from_user.id)
    card = await get_card(card_id)
    uid = callback.from_user.id
    user = await get_or_create_user(uid, callback.from_user.username)
    uname = f"@{user['username']}" if user.get("username") else f"ID:{uid}"
    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"‼️ ЖАЛОБА НА КАРТОЧКУ\n\n"
            f"Карточка ID: {card_id} (публичный #{card['public_id'] if card else '?'})\n"
            f"От: {uname}"
        )
    except Exception:
        pass
    await callback.answer("‼️ Жалоба отправлена", show_alert=True)


# ── Admin card commands ──────────────────────────────────────────────────────

@router.message(F.text == "/cardstats", F.chat.id == ADMIN_GROUP_ID)
async def cmd_cardstats(message: Message):
    stats = await get_card_stats()
    top_l = "\n".join(
        f"  {r['emoji']} #{r['public_id']} ({r['category']}) — {r['rating']}♥️"
        for r in stats["top_liked"]
    ) or "  —"
    top_d = "\n".join(
        f"  {r['emoji']} #{r['public_id']} ({r['category']}) — {r['rating']}♥️"
        for r in stats["top_disliked"]
    ) or "  —"
    await message.reply(
        f"📊 СТАТИСТИКА КАРТОЧЕК\n\n"
        f"Карточек: {stats['total_cards']}\n"
        f"Авторов: {stats['total_artists']}\n\n"
        f"⭐ Топ 5 по ♥️:\n{top_l}\n\n"
        f"👎 Топ 5 по дизлайкам:\n{top_d}"
    )


@router.message(F.text == "/priority", F.chat.id == ADMIN_GROUP_ID)
async def cmd_priority_list(message: Message):
    cards = await get_priority_cards()
    if not cards:
        await message.reply("Приоритетных карточек нет.")
        return
    lines = "\n".join(
        f"  #{c['public_id']} {c['emoji']} {c['category'] or '—'}" for c in cards
    )
    await message.reply(f"⭐ ПРИОРИТЕТНЫЕ КАРТОЧКИ:\n{lines}")


@router.message(F.text.startswith("/addpriority "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_add_priority(message: Message):
    parts = message.text.split(maxsplit=1)
    if not parts[1].isdigit():
        await message.reply("Использование: /addpriority <card_id>")
        return
    await set_priority(int(parts[1]), True)
    await message.reply(f"⭐ Карточка {parts[1]} добавлена в приоритет.")


@router.message(F.text.startswith("/removepriority "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_remove_priority(message: Message):
    parts = message.text.split(maxsplit=1)
    if not parts[1].isdigit():
        await message.reply("Использование: /removepriority <card_id>")
        return
    await set_priority(int(parts[1]), False)
    await message.reply(f"Карточка {parts[1]} убрана из приоритета.")


@router.message(F.text == "/addcard", F.chat.id == ADMIN_GROUP_ID)
async def cmd_addcard(message: Message, state: FSMContext):
    await state.set_state(AddCardStates.enter_post_url)
    await message.reply(
        "➕ ДОБАВЛЕНИЕ КАРТОЧКИ\n\n"
        "Введи ссылку на пост в канале или напиши 'вручную' для ручного ввода:"
    )


@router.message(AddCardStates.enter_post_url, F.chat.id == ADMIN_GROUP_ID)
async def addcard_url(message: Message, state: FSMContext):
    url = (message.text or "").strip()
    if url.lower() == "вручную":
        await state.update_data(post_url=None)
    else:
        await state.update_data(post_url=url)
    await state.set_state(AddCardStates.enter_file)
    await message.reply("📎 Отправь медиафайл (фото/аудио) или напиши 'нет':")


@router.message(AddCardStates.enter_file, F.chat.id == ADMIN_GROUP_ID)
async def addcard_file(message: Message, state: FSMContext):
    file_id, file_type = None, None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    await state.update_data(file_id=file_id, file_type=file_type)
    await state.set_state(AddCardStates.enter_desc)
    await message.reply("📝 Введи описание карточки:")


@router.message(AddCardStates.enter_desc, F.chat.id == ADMIN_GROUP_ID)
async def addcard_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddCardStates.enter_category)
    await message.reply("🏷 Введи категорию:")


@router.message(AddCardStates.enter_category, F.chat.id == ADMIN_GROUP_ID)
async def addcard_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(AddCardStates.enter_author_id)
    await message.reply("👤 Введи artist_id автора (число) или 'нет':")


@router.message(AddCardStates.enter_author_id, F.chat.id == ADMIN_GROUP_ID)
async def addcard_author(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    author_id = None
    if txt.isdigit():
        artist = await get_artist_by_id(int(txt))
        author_id = artist["id"] if artist else None
    await state.update_data(author_id=author_id)
    await state.set_state(AddCardStates.confirm)
    data = await state.get_data()
    await message.reply(
        f"📋 Подтверди создание карточки:\n\n"
        f"Ссылка: {data.get('post_url') or '—'}\n"
        f"Файл: {'есть' if data.get('file_id') else '—'}\n"
        f"Описание: {data.get('description') or '—'}\n"
        f"Категория: {data.get('category') or '—'}\n"
        f"Автор ID: {txt if txt.isdigit() else '—'}\n\n"
        f"Отправь 'да' для создания или 'нет' для отмены."
    )


@router.message(AddCardStates.confirm, F.chat.id == ADMIN_GROUP_ID)
async def addcard_confirm(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() != "да":
        await state.clear()
        await message.reply("❌ Отменено.")
        return
    data = await state.get_data()
    await state.clear()
    card_id, public_id = await create_card(
        author_id=data.get("author_id"),
        file_id=data.get("file_id"),
        file_type=data.get("file_type"),
        description=data.get("description"),
        category=data.get("category"),
        post_url=data.get("post_url"),
    )
    await message.reply(f"✅ Карточка создана! ID: {card_id}, публичный #{public_id}")


# ── Artist commands ──────────────────────────────────────────────────────────

@router.message(F.text == "/addartistid", F.chat.id == ADMIN_GROUP_ID)
async def cmd_addartistid(message: Message):
    uid = message.from_user.id
    existing = await get_artist_by_user(uid)
    if existing:
        await message.reply(f"У вас уже есть artist_id: {existing['artist_id']}")
        return
    aid = await add_artist(uid)
    await message.reply(f"✅ Ваш artist_id: {aid}")


@router.message(F.text.startswith("/changeartistid "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_changeartistid(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.reply("Использование: /changeartistid <old_id> <new_id>")
        return
    success = await change_artist_id(int(parts[1]), int(parts[2]))
    if success:
        await message.reply(f"✅ artist_id {parts[1]} → {parts[2]}")
    else:
        await message.reply("❌ Ошибка. ID уже занят или не существует.")


@router.message(F.text == "/removeartistid", F.chat.id == ADMIN_GROUP_ID)
async def cmd_removeartistid(message: Message):
    await remove_artist(message.from_user.id)
    await message.reply("✅ artist_id удалён.")

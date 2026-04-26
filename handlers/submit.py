import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SubmitStates
from keyboards.submit_kb import (
    content_type_keyboard,
    ask_description_keyboard,
    ask_link_keyboard,
    publication_mode_keyboard,
)
from keyboards.main_kb import main_keyboard
from keyboards.moderation_kb import submission_moderation_keyboard
from services.user_service import get_or_create_user, is_user_banned
from services.task_service import create_submission
from config import ADMIN_GROUP_IDS

router = Router()
logger = logging.getLogger(__name__)

CONTENT_TYPE_NAMES = {
    "text":  "📝 Текст",
    "image": "🖼 Изображение",
    "audio": "🎵 Аудио",
}


# ─── Вход в сабмишн ────────────────────────────────────────────────────────

@router.callback_query(F.data == "submit_work")
async def start_submit(callback: CallbackQuery, state: FSMContext):
    if await is_user_banned(callback.from_user.id):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return
    await state.set_state(SubmitStates.select_type)
    await callback.message.edit_text(
        "📤 Выбери тип работы:",
        reply_markup=content_type_keyboard(),
    )
    await callback.answer()


# ─── Шаг 1: Тип контента ──────────────────────────────────────────────────

@router.callback_query(SubmitStates.select_type, F.data.startswith("stype_"))
async def select_content_type(callback: CallbackQuery, state: FSMContext):
    ctype = callback.data.split("_")[1]  # text / image / audio
    await state.update_data(content_type=ctype)
    await state.set_state(SubmitStates.send_content)

    prompts = {
        "text":  "✏️ Отправь свой текст (стихотворение, эссе и т.д.):",
        "image": "🖼 Отправь изображение (арт, фото):",
        "audio": "🎵 Отправь аудиофайл или голосовое сообщение:",
    }
    await callback.message.edit_text(prompts[ctype])
    await callback.answer()


# ─── Шаг 2: Контент ───────────────────────────────────────────────────────

@router.message(SubmitStates.send_content)
async def receive_content(message: Message, state: FSMContext):
    data = await state.get_data()
    ctype = data.get("content_type")

    content = None
    file_id = None

    if ctype == "text":
        if not message.text:
            await message.answer("❗ Пожалуйста, отправь текст сообщением.")
            return
        content = message.text

    elif ctype == "image":
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document:
            file_id = message.document.file_id
        else:
            await message.answer("❗ Пожалуйста, отправь изображение.")
            return

    elif ctype == "audio":
        if message.audio:
            file_id = message.audio.file_id
        elif message.voice:
            file_id = message.voice.file_id
        elif message.document:
            file_id = message.document.file_id
        else:
            await message.answer("❗ Пожалуйста, отправь аудиофайл.")
            return

    await state.update_data(content=content, file_id=file_id)
    await state.set_state(SubmitStates.ask_desc)
    await message.answer(
        "📌 Хочешь добавить описание к работе?",
        reply_markup=ask_description_keyboard(),
    )


# ─── Шаг 3: Описание ──────────────────────────────────────────────────────

@router.callback_query(SubmitStates.ask_desc, F.data == "sub_add_desc")
async def prompt_description(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SubmitStates.add_desc)
    await callback.message.edit_text("✏️ Введи описание:")
    await callback.answer()


@router.callback_query(SubmitStates.ask_desc, F.data == "sub_skip_desc")
async def skip_description(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await state.set_state(SubmitStates.ask_link)
    await callback.message.edit_text(
        "🔗 Хочешь добавить ссылку на оригинал (YouTube, SoundCloud, Instagram и т.д.)?",
        reply_markup=ask_link_keyboard(),
    )
    await callback.answer()


@router.message(SubmitStates.add_desc)
async def receive_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(SubmitStates.ask_link)
    await message.answer(
        "🔗 Хочешь добавить ссылку на оригинал (YouTube, SoundCloud, Instagram и т.д.)?",
        reply_markup=ask_link_keyboard(),
    )


# ─── Шаг 4: Ссылка на оригинал ────────────────────────────────────────────

@router.callback_query(SubmitStates.ask_link, F.data == "sub_add_link")
async def prompt_link(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SubmitStates.add_link)
    await callback.message.edit_text("🔗 Отправь ссылку:")
    await callback.answer()


@router.callback_query(SubmitStates.ask_link, F.data == "sub_skip_link")
async def skip_link(callback: CallbackQuery, state: FSMContext):
    await state.update_data(original_link=None)
    await state.set_state(SubmitStates.select_mode)
    await callback.message.edit_text(
        "👤 Как опубликовать работу?",
        reply_markup=publication_mode_keyboard(),
    )
    await callback.answer()


@router.message(SubmitStates.add_link)
async def receive_link(message: Message, state: FSMContext):
    await state.update_data(original_link=message.text)
    await state.set_state(SubmitStates.select_mode)
    await message.answer(
        "👤 Как опубликовать работу?",
        reply_markup=publication_mode_keyboard(),
    )


# ─── Шаг 5: Режим публикации → сохранение и отправка в модерацию ──────────

@router.callback_query(SubmitStates.select_mode, F.data.in_({"sub_mode_anon", "sub_mode_public"}))
async def select_publication_mode(callback: CallbackQuery, state: FSMContext, bot: Bot):
    mode = "anonymous" if callback.data == "sub_mode_anon" else "public"
    data = await state.get_data()
    await state.clear()

    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)

    submission_id = await create_submission(
        user_id=user["id"],
        content_type=data.get("content_type"),
        content=data.get("content"),
        file_id=data.get("file_id"),
        description=data.get("description"),
        original_link=data.get("original_link"),
        publication_mode=mode,
    )

    await callback.message.edit_text(
        "✅ Заявка отправлена на рассмотрение!\n\n"
        "Мы свяжемся с тобой, если работа будет принята.",
        reply_markup=main_keyboard(),
    )
    await callback.answer()

    # Отправляем в группу модерации
    await _send_to_moderation(bot, submission_id, user, data, mode)


async def _send_to_moderation(bot: Bot, submission_id: int, user: dict, data: dict, mode: str):
    ctype = data.get("content_type", "unknown")
    description = data.get("description") or "—"
    original_link = data.get("original_link") or "—"
    username_display = f"@{user['username']}" if user.get("username") else f"ID: {user['id']}"

    if mode == "anonymous":
        pub_mode_text = "🕶 Анонимно"
    else:
        pub_mode_text = f"👤 {username_display}"

    header = (
        f"📥 НОВАЯ ЗАЯВКА\n\n"
        f"Тип: {CONTENT_TYPE_NAMES.get(ctype, ctype)}\n"
        f"ID: {user['id']}\n"
        f"Username: {username_display}\n\n"
        f"📌 Описание:\n{description}\n\n"
        f"🔗 Оригинал:\n{original_link}\n\n"
        f"👤 Режим публикации: {pub_mode_text}"
    )

    kb = submission_moderation_keyboard(submission_id)

    try:
        if ctype == "text":
            text_content = data.get("content", "")
            full = f"{header}\n\n📝 Содержание:\n{text_content}"
            # Telegram limit 4096
            if len(full) > 4096:
                await bot.send_message(ADMIN_GROUP_ID, header, reply_markup=kb)
                await bot.send_message(ADMIN_GROUP_ID, f"📝 Содержание:\n{text_content[:3500]}…")
            else:
                await bot.send_message(ADMIN_GROUP_ID, full, reply_markup=kb)

        elif ctype == "image":
            await bot.send_photo(
                ADMIN_GROUP_ID,
                photo=data.get("file_id"),
                caption=header,
                reply_markup=kb,
            )
        elif ctype == "audio":
            await bot.send_audio(
                ADMIN_GROUP_ID,
                audio=data.get("file_id"),
                caption=header,
                reply_markup=kb,
            )
    except Exception as e:
        logger.error("Failed to send submission to moderation: %s", e)

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import VerificationStates
from services.user_service import get_user, get_or_create_user, is_user_banned, get_balance
from services.verification_service import (
    submit_verification, get_verification,
    approve_verification, reject_verification, get_verified_count,
)
from keyboards.moderation_kb import verification_moderation_keyboard
from config import ADMIN_GROUP_ID, THREADS_URL, THREADS_POST_URL, is_admin

router = Router()
logger = logging.getLogger(__name__)


def _ver_menu_kb(is_verified: bool) -> InlineKeyboardMarkup:
    if is_verified:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Верифицирован", callback_data="ver_already")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="promotion")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☑️ Выполнено", callback_data="ver_submit")],
        [InlineKeyboardButton(text="↩️ Назад",      callback_data="promotion")],
    ])


@router.callback_query(F.data == "verification_menu")
async def verification_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    if await is_user_banned(uid):
        await callback.answer("🚫 Вы заблокированы.", show_alert=True)
        return

    user = await get_or_create_user(uid, callback.from_user.username)
    balance = user["balance"]
    is_verified = bool(user.get("is_verified"))

    post_line = f"\n🔗 Пост для лайка: {THREADS_POST_URL}" if THREADS_POST_URL else ""
    text = (
        f"🪪 ВЕРИФИКАЦИЯ\n\n"
        f"Чтобы открыть «Создать задание», нужно:\n"
        f"1. Подписаться на Threads аккаунт:\n{THREADS_URL}\n"
        f"2. Поставить лайк на пост{post_line}\n"
        f"3. Нажать ☑️ Выполнено и ввести свой @username\n\n"
        f"Balance: {balance}🌟"
    )
    if is_verified:
        threads_uname = user.get("threads_username") or "—"
        text = (
            f"🪪 ВЕРИФИКАЦИЯ\n\n"
            f"✅ Вы верифицированы!\n"
            f"Threads: @{threads_uname}\n\n"
            f"Balance: {balance}🌟"
        )
    await callback.message.edit_text(text, reply_markup=_ver_menu_kb(is_verified))
    await callback.answer()


@router.callback_query(F.data == "ver_already")
async def ver_already(callback: CallbackQuery):
    await callback.answer("✅ Вы уже верифицированы!", show_alert=True)


@router.callback_query(F.data == "ver_submit")
async def ver_submit_start(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    # Проверяем нет ли pending заявки
    existing = await get_verification(uid)
    if existing and existing["status"] == "pending":
        await callback.answer(
            "⏳ Ваша заявка уже на рассмотрении. Ожидайте.", show_alert=True
        )
        return

    await state.set_state(VerificationStates.enter_username)
    await callback.message.edit_text(
        "✏️ Введи свой @username на Threads:\n\n"
        "(Убедись, что ты подписался и поставил лайк)"
    )
    await callback.answer()


@router.message(VerificationStates.enter_username)
async def ver_receive_username(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    threads_uname = (message.text or "").strip().lstrip("@")
    if not threads_uname:
        await message.answer("❗ Введи корректный @username.")
        return
    await state.clear()

    await submit_verification(uid, threads_uname)
    user = await get_or_create_user(uid, message.from_user.username)
    tg_uname = f"@{user['username']}" if user.get("username") else f"ID:{uid}"

    await message.answer(
        "✅ Заявка на верификацию отправлена!\n"
        "Ожидай подтверждения администратора."
    )

    # Отправить в группу модерации
    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"🪪 ВЕРИФИКАЦИЯ\n\n"
            f"Пользователь: {tg_uname} (ID: {uid})\n"
            f"Threads: @{threads_uname}\n\n"
            f"Проверь подписку и лайк на посте.",
            reply_markup=verification_moderation_keyboard(uid),
        )
    except Exception as e:
        logger.error("Failed to send verification to admin: %s", e)


# ── Модерация верификации ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ver_approve_"), F.message.chat.id == ADMIN_GROUP_ID)
async def approve_ver(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[2])
    threads_uname = await approve_verification(user_id, callback.from_user.id)
    if not threads_uname:
        await callback.answer("❌ Пользователь не найден.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"✅ Верификация принята. @{threads_uname}"
    )
    try:
        await bot.send_message(
            user_id,
            "🪪 Верификация подтверждена!\n\n"
            "Теперь тебе доступно создание заданий в 📈 Продвижение."
        )
    except Exception:
        pass
    await callback.answer("✅ Принято")
    logger.info("Verification approved for user %s by %s", user_id, callback.from_user.id)


@router.callback_query(F.data.startswith("ver_reject_"), F.message.chat.id == ADMIN_GROUP_ID)
async def reject_ver(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[2])
    await reject_verification(user_id, callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("❌ Верификация отклонена.")
    try:
        await bot.send_message(
            user_id,
            "❌ Верификация отклонена.\n\n"
            "Убедись, что ты подписался на аккаунт и поставил лайк, затем попробуй снова."
        )
    except Exception:
        pass
    await callback.answer("❌ Отклонено")


# ── Команды администратора ───────────────────────────────────────────────────

@router.message(F.text.startswith("/ver "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_ver(message: Message, bot: Bot):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /ver <id/@username>")
        return
    from services.user_service import get_user_by_username
    ident = parts[1].strip()
    user = (await get_user(int(ident)) if ident.lstrip("@").isdigit()
            else await get_user_by_username(ident))
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    threads_uname = await approve_verification(user["id"], message.from_user.id)
    if not threads_uname:
        await message.reply("❌ Нет заявки на верификацию.")
        return
    await message.reply(f"✅ Верификация принята для ID {user['id']} (@{threads_uname})")
    try:
        await bot.send_message(
            user["id"],
            "🪪 Верификация подтверждена!\n\nТеперь тебе доступно создание заданий."
        )
    except Exception:
        pass


@router.message(F.text.startswith("/unver "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_unver(message: Message):
    from services.user_service import get_user_by_username, unset_verified
    parts = message.text.split(maxsplit=1)
    ident = parts[1].strip()
    user = (await get_user(int(ident)) if ident.lstrip("@").isdigit()
            else await get_user_by_username(ident))
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    await unset_verified(user["id"])
    await message.reply(f"✅ Верификация снята с ID {user['id']}")


@router.message(F.text == "/verstats", F.chat.id == ADMIN_GROUP_ID)
async def cmd_verstats(message: Message):
    count = await get_verified_count()
    await message.reply(f"🪪 Верифицировано пользователей: {count}")


@router.message(F.text.startswith("/vercheck "), F.chat.id == ADMIN_GROUP_ID)
async def cmd_vercheck(message: Message):
    from services.user_service import get_user_by_username
    parts = message.text.split(maxsplit=1)
    ident = parts[1].strip()
    user = (await get_user(int(ident)) if ident.lstrip("@").isdigit()
            else await get_user_by_username(ident))
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return
    ver = await get_verification(user["id"])
    tg_uname = f"@{user['username']}" if user.get("username") else "—"
    threads = user.get("threads_username") or (ver["threads_username"] if ver else "—")
    await message.reply(
        f"🪪 ДАННЫЕ ПОЛЬЗОВАТЕЛЯ\n\n"
        f"TG: {tg_uname} (ID: {user['id']})\n"
        f"Threads: @{threads}\n"
        f"Верифицирован: {'✅ Да' if user.get('is_verified') else '❌ Нет'}\n"
        f"Баланс: {user['balance']}🌟"
    )

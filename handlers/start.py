"""
/start и главное меню
ФИКС: кнопка "Меню" под алертом шлёт НОВОЕ сообщение!
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from datetime import datetime
from database import db
from keyboards import main_menu_keyboard, welcome_keyboard, expired_keyboard, back_keyboard
from locales import get_text
from config import TIERS, TRIAL_ACCOUNTS, SUPPORT_USERNAME
import logging

logger = logging.getLogger(__name__)
router = Router()


def get_account_limit(tier: str) -> int:
    if tier == "trial":
        return TRIAL_ACCOUNTS
    return TIERS.get(tier, {}).get("accounts", 0)


async def is_active(user: dict) -> bool:
    if not user.get("tier") or not user.get("subscription_until"):
        return False
    until = user["subscription_until"]
    if isinstance(until, str):
        until = datetime.fromisoformat(until)
    return until > datetime.now()


async def show_menu(target, user: dict, edit: bool = True):
    """
    Показывает главное меню.
    ФИКС: если edit=True но сообщение фото/медиа — шлём НОВОЕ!
    """
    user_id = user["user_id"]

    if await is_active(user):
        current = await db.get_user_tracking_count(user_id)
        mx = get_account_limit(user["tier"])
        until = user["subscription_until"]
        if isinstance(until, str):
            until = datetime.fromisoformat(until)
        tier_name = TIERS.get(user["tier"], {}).get("name", user["tier"].title())
        text = get_text("welcome_subscribed", tier=tier_name, until=until.strftime("%d.%m.%Y"), current=current, max=mx)
        kb = main_menu_keyboard(current, mx)
    else:
        if user.get("trial_used"):
            text = get_text("welcome_expired")
            kb = expired_keyboard()
        else:
            text = get_text("welcome_new")
            kb = welcome_keyboard(True)

    # Определяем целевое сообщение
    if hasattr(target, 'message'):
        msg = target.message
    else:
        msg = target

    if edit:
        try:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass

    # Отправляем новое сообщение
    await msg.answer(text, reply_markup=kb, parse_mode="HTML")


async def resolve_referrer(ref_code: str, user_id: int):
    if not ref_code:
        return None
    try:
        rid = int(ref_code)
        if rid != user_id:
            r = await db.get_user(rid)
            if r:
                return rid
    except ValueError:
        pass
    r = await db.get_user_by_username(ref_code)
    if r and r["user_id"] != user_id:
        return r["user_id"]
    return None


@router.message(CommandStart())
async def cmd_start(message: Message):
    uid = message.from_user.id
    uname = message.from_user.username
    referred_by = None
    if message.text and len(message.text.split()) > 1:
        referred_by = await resolve_referrer(message.text.split()[1], uid)
    user = await db.get_user(uid)
    if not user:
        user = await db.create_user(uid, uname, referred_by)
        logger.info(f"New user: {uid} (@{uname})")
    elif uname and user.get("username") != uname:
        await db.update_user(uid, username=uname)
    if user.get("banned"):
        await message.answer(get_text("banned"))
        return
    await show_menu(message, user, edit=False)


@router.callback_query(F.data == "main")
async def cb_main(callback: CallbackQuery):
    """
    Главное меню по кнопке "Меню"
    ФИКС: всегда шлём НОВОЕ сообщение чтобы алерт оставался!
    """
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Напишите /start")
        return
    if user.get("banned"):
        await callback.message.answer(get_text("banned"))
        await callback.answer()
        return

    # ФИКС: Всегда шлём НОВОЕ сообщение, чтобы алерт оставался нетронутым!
    await show_menu(callback, user, edit=False)
    await callback.answer()


@router.callback_query(F.data == "trial")
async def cb_trial(callback: CallbackQuery):
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user or user.get("trial_used"):
        await callback.answer(get_text("trial_already_used"), show_alert=True)
        return
    if await db.activate_trial(uid):
        await callback.message.edit_text(
            get_text("trial_activated"),
            reply_markup=main_menu_keyboard(0, TRIAL_ACCOUNTS),
            parse_mode="HTML"
        )
    else:
        await callback.answer(get_text("trial_already_used"), show_alert=True)


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(
        get_text("help", support=SUPPORT_USERNAME),
        reply_markup=back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

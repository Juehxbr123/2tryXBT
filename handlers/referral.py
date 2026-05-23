"""
Реферальная программа + вывод на xRocket
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from database import db
from keyboards import referral_keyboard, back_keyboard
from locales import get_text
from services.payment import payment_service
import logging

logger = logging.getLogger(__name__)
router = Router()

_bot_username: str = None


async def get_bot_username(bot: Bot) -> str:
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username
    return _bot_username


@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery, bot: Bot):
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user:
        await callback.answer("Напишите /start")
        return
    if user.get("banned"):
        return

    stats = await db.get_referral_stats(uid)
    referrals_list = await db.get_user_referrals(uid)

    bot_uname = await get_bot_username(bot)
    user_uname = callback.from_user.username or str(uid)
    link = f"https://t.me/{bot_uname}?start={user_uname}"

    refs_text = ""
    if referrals_list:
        refs_text = "\n\n👥 <b>Приглашённые:</b>\n"
        for ref in referrals_list[:10]:
            s = "💎" if ref.get("has_paid") else "⏳"
            rn = ref.get("username") or f"id{ref['user_id']}"
            refs_text += f"{s} @{rn}\n"
        if len(referrals_list) > 10:
            refs_text += f"<i>...и ещё {len(referrals_list) - 10}</i>\n"

    text = get_text("referral_menu",
        link=link, invited=stats["invited"], paid=stats["paid"],
        earned_ton=stats["earned_ton"], earned_usdt=stats["earned_usdt"],
        balance_ton=round(user.get("balance_ton", 0), 4),
        balance_usdt=round(user.get("balance_usdt", 0), 2)
    ) + refs_text

    await callback.message.edit_text(text, reply_markup=referral_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("withdraw_"))
async def cb_withdraw(callback: CallbackQuery):
    currency = callback.data.replace("withdraw_", "")
    uid = callback.from_user.id

    if currency not in ["TONCOIN", "USDT"]:
        return

    success, msg = await payment_service.withdraw(uid, currency)

    if success:
        await callback.answer(f"✅ Выведено: {msg}", show_alert=True)
        # Обновляем меню рефералки
        user = await db.get_user(uid)
        stats = await db.get_referral_stats(uid)
        bot_uname = _bot_username or "bot"
        user_uname = callback.from_user.username or str(uid)
        link = f"https://t.me/{bot_uname}?start={user_uname}"

        text = get_text("referral_menu",
            link=link, invited=stats["invited"], paid=stats["paid"],
            earned_ton=stats["earned_ton"], earned_usdt=stats["earned_usdt"],
            balance_ton=round(user.get("balance_ton", 0), 4),
            balance_usdt=round(user.get("balance_usdt", 0), 2))

        await callback.message.edit_text(text, reply_markup=referral_keyboard(), parse_mode="HTML")
    else:
        await callback.answer(f"❌ {msg}", show_alert=True)

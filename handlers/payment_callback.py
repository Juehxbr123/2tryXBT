"""
Проверка оплаты
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from datetime import datetime
from database import db
from keyboards import back_keyboard, main_menu_keyboard
from locales import get_text
from config import TIERS, TRIAL_ACCOUNTS
from services.payment import payment_service
import logging

logger = logging.getLogger(__name__)
router = Router()


def get_limit(tier: str) -> int:
    if tier == "trial":
        return TRIAL_ACCOUNTS
    return TIERS.get(tier, {}).get("accounts", 0)


@router.callback_query(F.data.startswith("check_"))
async def cb_check(callback: CallbackQuery, bot: Bot):
    invoice_id = callback.data.replace("check_", "")
    uid = callback.from_user.id

    payment = await db.get_payment_by_invoice(invoice_id)
    if not payment or payment["user_id"] != uid:
        await callback.answer("❌ Платёж не найден", show_alert=True)
        return
    if payment["status"] == "paid":
        await callback.answer("✅ Уже обработан", show_alert=True)
        return

    status = await payment_service.check_invoice(invoice_id)

    # xRocket статусы: active (ожидает), paid (оплачен), expired (истёк)
    if status == "paid":
        user = await db.get_user(uid)
        extend = user.get("tier") == payment["tier"]
        if await payment_service.process_successful_payment(uid, payment["tier"], invoice_id, extend, bot):
            user = await db.get_user(uid)
            until = datetime.fromisoformat(user["subscription_until"])
            td = TIERS.get(payment["tier"], {})
            current = await db.get_user_tracking_count(uid)
            mx = get_limit(user["tier"])

            text = get_text("payment_success", tier=td.get("name", payment["tier"]), until=until.strftime("%d.%m.%Y"))
            text += f"\n\n{'─' * 20}\n\n"
            text += get_text("welcome_subscribed", tier=td.get("name", payment["tier"]),
                            until=until.strftime("%d.%m.%Y"), current=current, max=mx)

            await callback.message.edit_text(text, reply_markup=main_menu_keyboard(current, mx), parse_mode="HTML")
            logger.info(f"Payment OK: {uid} -> {payment['tier']}")
        else:
            await callback.answer("❌ Ошибка активации", show_alert=True)

    elif status == "expired":
        await db.expire_payment(invoice_id)
        await callback.answer("❌ Счёт истёк", show_alert=True)
        await callback.message.edit_text("❌ Счёт истёк", reply_markup=back_keyboard("subscription"))

    else:
        # active = ещё не оплачен
        await callback.answer("⏳ Ожидаем оплату...")


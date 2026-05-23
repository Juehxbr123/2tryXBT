"""
Подписка и оплата через xRocket + баланс
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from datetime import datetime
from database import db
from keyboards import subscription_tiers_keyboard, currency_keyboard, active_subscription_keyboard, payment_keyboard, back_keyboard, main_menu_keyboard
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


async def is_active(user: dict) -> bool:
    if not user.get("tier") or not user.get("subscription_until"):
        return False
    until = user["subscription_until"]
    if isinstance(until, str):
        until = datetime.fromisoformat(until)
    return until > datetime.now()


@router.callback_query(F.data == "subscription")
async def cb_sub(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or user.get("banned"):
        return
    if await is_active(user) and user["tier"] != "trial":
        tier = user["tier"]
        td = TIERS.get(tier, {})
        until = user["subscription_until"]
        if isinstance(until, str):
            until = datetime.fromisoformat(until)
        days = (until - datetime.now()).days
        await callback.message.edit_text(
            get_text("subscription_active", tier=td.get("name", tier), price=td.get("price", 0),
                    max=td.get("accounts", 0), until=until.strftime("%d.%m.%Y"), days_left=max(0, days)),
            reply_markup=active_subscription_keyboard(tier != "pro"), parse_mode="HTML")
    else:
        await callback.message.edit_text(get_text("subscription_choose"),
            reply_markup=subscription_tiers_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("tier_"))
async def cb_tier(callback: CallbackQuery):
    tier = callback.data.replace("tier_", "")
    if tier not in TIERS:
        return
    user = await db.get_user(callback.from_user.id)
    if not user:
        return

    price = TIERS[tier]["price"]
    bal_ton = user.get("balance_ton", 0)
    bal_usdt = user.get("balance_usdt", 0)

    text = get_text("choose_currency")
    if bal_ton > 0 or bal_usdt > 0:
        text = f"💰 <b>Ваш баланс:</b>\n💎 TON: {bal_ton:.4f}\n💵 USDT: {bal_usdt:.2f}\n\n"
        text += "Баланс спишется автоматически при оплате.\n\n"
        text += get_text("choose_currency")

    await callback.message.edit_text(text, reply_markup=currency_keyboard(tier), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("pay_"))
async def cb_pay(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    if len(parts) != 3:
        return
    tier, currency = parts[1], parts[2]
    uid = callback.from_user.id
    if tier not in TIERS or currency not in ["TONCOIN", "USDT"]:
        return
    user = await db.get_user(uid)
    if not user:
        return
    await callback.message.edit_text("⏳ Создаём счёт...")

    invoice_id, pay_url, amount, balance_used = await payment_service.create_invoice(uid, tier, currency)

    if not invoice_id:
        await callback.message.edit_text("❌ Ошибка создания счёта", reply_markup=back_keyboard("subscription"))
        return

    td = TIERS[tier]
    cur_label = "TON" if currency == "TONCOIN" else "USDT"

    # Оплачено полностью с баланса
    if pay_url is None:
        extend = await is_active(user) and user.get("tier") == tier
        if await payment_service.process_successful_payment(uid, tier, invoice_id, extend, bot):
            user = await db.get_user(uid)
            until = datetime.fromisoformat(user["subscription_until"])
            current = await db.get_user_tracking_count(uid)
            mx = get_limit(user["tier"])

            text = f"💰 С баланса списано: <b>{balance_used:.4f} {cur_label}</b>\n\n"
            text += get_text("payment_success", tier=td["name"], until=until.strftime("%d.%m.%Y"))
            text += f"\n\n{'─' * 20}\n\n"
            text += get_text("welcome_subscribed", tier=td["name"],
                            until=until.strftime("%d.%m.%Y"), current=current, max=mx)

            await callback.message.edit_text(text, reply_markup=main_menu_keyboard(current, mx), parse_mode="HTML")
            logger.info(f"User {uid} paid from balance: {tier}")
        else:
            await callback.message.edit_text("❌ Ошибка активации", reply_markup=back_keyboard("subscription"))
        return

    # Частичная оплата или полная через xRocket
    text = ""
    if balance_used > 0:
        text = f"💰 С баланса списано: <b>{balance_used:.4f} {cur_label}</b>\n\n"
    text += get_text("invoice_created", amount=amount, currency=cur_label, tier=td["name"])
    await callback.message.edit_text(text, reply_markup=payment_keyboard(pay_url, invoice_id), parse_mode="HTML")


@router.callback_query(F.data == "extend_sub")
async def cb_extend(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or not user.get("tier") or user["tier"] == "trial":
        await callback.message.edit_text(get_text("subscription_choose"),
            reply_markup=subscription_tiers_keyboard(), parse_mode="HTML")
    else:
        await callback.message.edit_text(get_text("choose_currency"),
            reply_markup=currency_keyboard(user["tier"]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "upgrade_sub")
async def cb_upgrade(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        return
    await callback.message.edit_text(get_text("subscription_choose"),
        reply_markup=subscription_tiers_keyboard(user.get("tier")), parse_mode="HTML")
    await callback.answer()


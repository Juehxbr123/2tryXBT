"""
Клавиатуры
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any
from config import TIERS


def main_menu_keyboard(current: int, max_accounts: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"📋 Мои аккаунты ({current}/{max_accounts})", callback_data="accounts"))
    b.row(InlineKeyboardButton(text="⚙️ Фильтры", callback_data="global_filters"),
          InlineKeyboardButton(text="💎 Подписка", callback_data="subscription"))
    b.row(InlineKeyboardButton(text="👥 Рефералка", callback_data="referral"),
          InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
    return b.as_markup()


def welcome_keyboard(trial_available: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if trial_available:
        b.row(InlineKeyboardButton(text="🎁 Триал 1 день", callback_data="trial"))
    b.row(InlineKeyboardButton(text="💎 Оформить подписку", callback_data="subscription"))
    return b.as_markup()


def expired_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💎 Оформить подписку", callback_data="subscription"))
    b.row(InlineKeyboardButton(text="👥 Рефералка", callback_data="referral"),
          InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
    return b.as_markup()


def back_keyboard(callback_data: str = "main") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data))
    return b.as_markup()


def accounts_keyboard(accounts: List[Dict[str, Any]], can_add: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        b.row(InlineKeyboardButton(
            text=f"⚙️ @{acc['twitter_username']}",
            callback_data=f"accsettings_{acc['twitter_username']}"))
    if can_add:
        b.row(InlineKeyboardButton(text="➕ Добавить", callback_data="add_account"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return b.as_markup()


def account_settings_keyboard(username: str, rt: bool, rp: bool, tr: bool, lk: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"🔄 Ретвиты: {'✅' if rt else '❌'}", callback_data=f"tf_rt_{username}"))
    b.row(InlineKeyboardButton(text=f"💬 Ответы: {'✅' if rp else '❌'}", callback_data=f"tf_rp_{username}"))
    b.row(InlineKeyboardButton(text=f"🌐 Перевод: {'✅' if tr else '❌'}", callback_data=f"tf_tr_{username}"))
    b.row(InlineKeyboardButton(text=f"🔗 Ссылка: {'✅' if lk else '❌'}", callback_data=f"tf_lk_{username}"))
    b.row(InlineKeyboardButton(text=f"🗑 Удалить @{username}", callback_data=f"del_{username}"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="accounts"))
    return b.as_markup()


def global_filters_keyboard(rt: bool, rp: bool, tr: bool, lk: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"🔄 Ретвиты: {'✅' if rt else '❌'}", callback_data="gf_rt"))
    b.row(InlineKeyboardButton(text=f"💬 Ответы: {'✅' if rp else '❌'}", callback_data="gf_rp"))
    b.row(InlineKeyboardButton(text=f"🌐 Перевод: {'✅' if tr else '❌'}", callback_data="gf_tr"))
    b.row(InlineKeyboardButton(text=f"🔗 Ссылка: {'✅' if lk else '❌'}", callback_data="gf_lk"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return b.as_markup()


def tweet_keyboard(username: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main"),
          InlineKeyboardButton(text=f"⚙️ @{username}", callback_data=f"accsettings_{username}"))
    return b.as_markup()


def subscription_tiers_keyboard(current_tier: str = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    icons = {"base": "⭐", "pro": "💎"}
    for tid, td in TIERS.items():
        if current_tier and tid == current_tier:
            continue
        b.row(InlineKeyboardButton(
            text=f"{icons.get(tid, '💎')} {td['name']} — ${td['price']}/мес ({td['accounts']} акк)",
            callback_data=f"tier_{tid}"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return b.as_markup()


def currency_keyboard(tier: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💎 TON", callback_data=f"pay_{tier}_TONCOIN"),
          InlineKeyboardButton(text="💵 USDT", callback_data=f"pay_{tier}_USDT"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="subscription"))
    return b.as_markup()


def active_subscription_keyboard(can_upgrade: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Продлить", callback_data="extend_sub"))
    if can_upgrade:
        b.row(InlineKeyboardButton(text="⬆️ Повысить тариф", callback_data="upgrade_sub"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return b.as_markup()


def payment_keyboard(pay_url: str, invoice_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    b.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_{invoice_id}"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="subscription"))
    return b.as_markup()


def extend_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Продлить", callback_data="extend_sub"))
    return b.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="main"))
    return b.as_markup()


def referral_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💎 Вывести TON", callback_data="withdraw_TONCOIN"),
          InlineKeyboardButton(text="💵 Вывести USDT", callback_data="withdraw_USDT"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main"))
    return b.as_markup()


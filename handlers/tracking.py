"""
Отслеживание + персональные и глобальные фильтры
+ Batch-добавление аккаунтов в ЛЮБОМ формате
+ Фикс: кнопка @username НЕ заменяет алерт-сообщение
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from database import db
from keyboards import (
    accounts_keyboard, account_settings_keyboard,
    cancel_keyboard, global_filters_keyboard, back_keyboard
)
from locales import get_text
from config import TIERS, TRIAL_ACCOUNTS
from services.twitter import twitter_service
from services.username_parser import parse_usernames
import logging

logger = logging.getLogger(__name__)
router = Router()


class AddAccountStates(StatesGroup):
    waiting_username = State()


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


# ==================== ACCOUNTS ====================

@router.callback_query(F.data == "accounts")
async def cb_accounts(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user or user.get("banned"):
        return

    accounts = await db.get_user_tracking(uid)
    mx = get_limit(user.get("tier", ""))
    can_add = len(accounts) < mx and await is_active(user)

    text = get_text(
        "accounts_list" if accounts else "accounts_empty",
        current=len(accounts), max=mx
    )
    await callback.message.edit_text(
        text, reply_markup=accounts_keyboard(accounts, can_add), parse_mode="HTML"
    )
    await callback.answer()


# ==================== ACCOUNT SETTINGS ====================

@router.callback_query(F.data.startswith("accsettings_"))
async def cb_account_settings(callback: CallbackQuery):
    """
    ФИКС: Кнопка @username в алерте — отправляем НОВОЕ сообщение,
    а не редактируем алерт о посте!
    """
    username = callback.data.replace("accsettings_", "")
    uid = callback.from_user.id

    entry = await db.get_tracking_entry(uid, username)
    if not entry:
        await callback.answer("❌ Аккаунт не найден")
        return

    text = get_text("account_settings", username=username,
                    rt="✅" if entry["filter_retweets"] else "❌",
                    rp="✅" if entry["filter_replies"] else "❌",
                    tr="✅" if entry["filter_translate"] else "❌",
                    lk="✅" if entry["filter_link"] else "❌")

    # Проверяем: если текущее сообщение — это алерт о твите
    # (содержит "Новый пост от" / "Ретвит от" / "Ответ от" или "МСК")
    # то НЕ редактируем его, а отправляем НОВОЕ сообщение
    current_text = callback.message.text or callback.message.caption or ""
    is_tweet_alert = any(marker in current_text for marker in [
        "Новый пост от @", "Ретвит от @", "Ответ от @", "МСК",
        "New post from @", "Retweet from @", "Reply from @"
    ])

    if is_tweet_alert:
        # Отправляем НОВОЕ сообщение, алерт остаётся нетронутым!
        await callback.message.answer(
            text,
            reply_markup=account_settings_keyboard(
                username,
                entry["filter_retweets"], entry["filter_replies"],
                entry["filter_translate"], entry["filter_link"]
            ),
            parse_mode="HTML"
        )
    else:
        # Обычный случай — редактируем текущее сообщение
        await callback.message.edit_text(
            text,
            reply_markup=account_settings_keyboard(
                username,
                entry["filter_retweets"], entry["filter_replies"],
                entry["filter_translate"], entry["filter_link"]
            ),
            parse_mode="HTML"
        )
    await callback.answer()


# ==================== PER-ACCOUNT FILTERS ====================

async def _toggle_filter(callback: CallbackQuery, prefix: str, field: str):
    username = callback.data.replace(prefix, "")
    uid = callback.from_user.id
    entry = await db.get_tracking_entry(uid, username)
    if not entry:
        return
    nv = 0 if entry[field] else 1
    await db.update_tracking_filter(uid, username, field, nv)
    entry[field] = nv

    text = get_text("account_settings", username=username,
                    rt="✅" if entry["filter_retweets"] else "❌",
                    rp="✅" if entry["filter_replies"] else "❌",
                    tr="✅" if entry["filter_translate"] else "❌",
                    lk="✅" if entry["filter_link"] else "❌")
    await callback.message.edit_text(
        text,
        reply_markup=account_settings_keyboard(
            username, entry["filter_retweets"], entry["filter_replies"],
            entry["filter_translate"], entry["filter_link"]
        ),
        parse_mode="HTML"
    )
    await callback.answer(get_text("filter_updated"))


@router.callback_query(F.data.startswith("tf_rt_"))
async def cb_tf_rt(cb: CallbackQuery):
    await _toggle_filter(cb, "tf_rt_", "filter_retweets")


@router.callback_query(F.data.startswith("tf_rp_"))
async def cb_tf_rp(cb: CallbackQuery):
    await _toggle_filter(cb, "tf_rp_", "filter_replies")


@router.callback_query(F.data.startswith("tf_tr_"))
async def cb_tf_tr(cb: CallbackQuery):
    await _toggle_filter(cb, "tf_tr_", "filter_translate")


@router.callback_query(F.data.startswith("tf_lk_"))
async def cb_tf_lk(cb: CallbackQuery):
    await _toggle_filter(cb, "tf_lk_", "filter_link")


# ==================== GLOBAL FILTERS ====================

@router.callback_query(F.data == "global_filters")
async def cb_global_filters(callback: CallbackQuery):
    uid = callback.from_user.id
    entry = await db.get_first_tracking_entry(uid)
    if not entry:
        await callback.answer("Добавьте аккаунт для настройки фильтров", show_alert=True)
        return

    await callback.message.edit_text(
        "⚙️ <b>Глобальные фильтры</b>\n\nИзменения применятся ко ВСЕМ аккаунтам:",
        reply_markup=global_filters_keyboard(
            entry["filter_retweets"], entry["filter_replies"],
            entry["filter_translate"], entry["filter_link"]
        ),
        parse_mode="HTML"
    )
    await callback.answer()


async def _global_toggle(callback, field):
    uid = callback.from_user.id
    entry = await db.get_first_tracking_entry(uid)
    if not entry:
        return
    nv = 0 if entry[field] else 1
    await db.update_all_tracking_filters(uid, field, nv)
    entry[field] = nv
    await callback.message.edit_text(
        "⚙️ <b>Глобальные фильтры</b>\n\nИзменения применятся ко ВСЕМ аккаунтам:",
        reply_markup=global_filters_keyboard(
            entry["filter_retweets"], entry["filter_replies"],
            entry["filter_translate"], entry["filter_link"]
        ),
        parse_mode="HTML"
    )
    await callback.answer(f"✅ Обновлено для всех аккаунтов!")


@router.callback_query(F.data == "gf_rt")
async def cb_gf_rt(cb: CallbackQuery):
    await _global_toggle(cb, "filter_retweets")


@router.callback_query(F.data == "gf_rp")
async def cb_gf_rp(cb: CallbackQuery):
    await _global_toggle(cb, "filter_replies")


@router.callback_query(F.data == "gf_tr")
async def cb_gf_tr(cb: CallbackQuery):
    await _global_toggle(cb, "filter_translate")


@router.callback_query(F.data == "gf_lk")
async def cb_gf_lk(cb: CallbackQuery):
    await _global_toggle(cb, "filter_link")


# ==================== ADD / DELETE ====================

@router.callback_query(F.data == "add_account")
async def cb_add(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user or not await is_active(user):
        await callback.answer(get_text("no_subscription"), show_alert=True)
        return

    current = await db.get_user_tracking_count(uid)
    mx = get_limit(user.get("tier", ""))
    if current >= mx:
        await callback.answer(get_text("account_limit_reached", max=mx), show_alert=True)
        return

    await state.set_state(AddAccountStates.waiting_username)
    await callback.message.edit_text(
        get_text("enter_username"), reply_markup=cancel_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddAccountStates.waiting_username)
async def process_username(message: Message, state: FSMContext):
    """
    Обработка ввода username — поддерживает ВСЕ форматы:
    1. Одиночный: elonmusk, @elonmusk
    2. URL: https://x.com/elonmusk, https://twitter.com/elonmusk
    3. Список через пробелы: @user1 @user2 @user3
    4. Список через запятые: user1, user2, user3
    5. Список через переносы строк
    6. Нумерованный список: 1. @user1  2. @user2
    7. Формат "@user (https://x.com/user)": как в запросе
    8. JSON массив: ["user1", "user2"]
    9. Любая комбинация выше
    """
    uid = message.from_user.id
    user = await db.get_user(uid)
    if not user or not await is_active(user):
        await state.clear()
        await message.answer(get_text("no_subscription"))
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        await message.answer("❌ Пустое сообщение", reply_markup=cancel_keyboard())
        return

    # Парсим все юзернеймы из текста
    parsed = parse_usernames(raw_text)

    if not parsed:
        await message.answer("❌ Не удалось распознать username(ы)", reply_markup=cancel_keyboard())
        return

    current = await db.get_user_tracking_count(uid)
    mx = get_limit(user.get("tier", ""))
    tracking = await db.get_user_tracking(uid)
    existing = {t["twitter_username"] for t in tracking}

    # Если один username — старое поведение (быстрое)
    if len(parsed) == 1:
        username = parsed[0]
        if username in existing:
            await message.answer(
                get_text("account_already_tracking", username=username),
                reply_markup=cancel_keyboard(), parse_mode="HTML"
            )
            return

        if current >= mx:
            await state.clear()
            await message.answer(get_text("account_limit_reached", max=mx))
            return

        status_msg = await message.answer("⏳ Проверяю...")
        try:
            exists, _ = await twitter_service.check_user_exists(username)
        except:
            exists = False

        if not exists:
            await status_msg.edit_text(
                get_text("account_not_found", username=username),
                reply_markup=cancel_keyboard(), parse_mode="HTML"
            )
            return

        if await db.add_tracking(uid, username):
            await state.clear()
            accounts = await db.get_user_tracking(uid)
            can_add = len(accounts) < mx
            text = get_text("account_added", username=username)
            text += "\n\n" + get_text("accounts_list", current=len(accounts), max=mx)
            await status_msg.edit_text(
                text, reply_markup=accounts_keyboard(accounts, can_add), parse_mode="HTML"
            )
        return

    # ===== BATCH MODE: несколько username =====
    await state.clear()
    status_msg = await message.answer(
        f"⏳ Обрабатываю {len(parsed)} аккаунтов..."
    )

    added = []
    already = []
    not_found = []
    limit_hit = []
    added_count = 0

    for username in parsed:
        # Проверяем лимит
        if current + added_count >= mx:
            limit_hit.append(username)
            continue

        # Уже отслеживается?
        if username in existing:
            already.append(username)
            continue

        # Проверяем существование
        try:
            exists, _ = await twitter_service.check_user_exists(username)
        except:
            exists = False

        if not exists:
            not_found.append(username)
            continue

        # Добавляем
        if await db.add_tracking(uid, username):
            added.append(username)
            existing.add(username)
            added_count += 1

    # Формируем отчёт
    details_parts = []
    for u in added:
        details_parts.append(get_text("batch_added", username=u))
    for u in already:
        details_parts.append(get_text("batch_already", username=u))
    for u in not_found:
        details_parts.append(get_text("batch_not_found", username=u))
    for u in limit_hit:
        details_parts.append(get_text("batch_limit", username=u))

    details = "\n".join(details_parts)
    text = get_text("batch_results",
                    added=len(added), total=len(parsed), details=details)

    accounts = await db.get_user_tracking(uid)
    can_add = len(accounts) < mx
    text += "\n\n" + get_text("accounts_list", current=len(accounts), max=mx)

    await status_msg.edit_text(
        text, reply_markup=accounts_keyboard(accounts, can_add), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("del_"))
async def cb_delete(callback: CallbackQuery):
    username = callback.data.replace("del_", "")
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user:
        return

    await db.remove_tracking(uid, username)

    accounts = await db.get_user_tracking(uid)
    mx = get_limit(user.get("tier", ""))
    can_add = len(accounts) < mx and await is_active(user)

    text = get_text("account_removed", username=username) + "\n\n"
    text += get_text(
        "accounts_list" if accounts else "accounts_empty",
        current=len(accounts), max=mx
    )
    await callback.message.edit_text(
        text, reply_markup=accounts_keyboard(accounts, can_add), parse_mode="HTML"
    )
    await callback.answer()


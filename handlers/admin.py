"""
Админ-команды (расширенные)
- Поддержка ID и @username
- /help для админа
- /broadcast рассылка
- /user детальная инфа
- /ban_inactive бан неактивных
- Логирование действий
"""
from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command
from database import db
from locales import get_text
from config import ADMIN_ID
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)
router = Router()


async def resolve_user(identifier: str):
    """Находит юзера по @username или ID"""
    identifier = identifier.strip().lstrip("@")
    
    # Пробуем как ID
    try:
        user_id = int(identifier)
        user = await db.get_user(user_id)
        if user:
            return user
    except ValueError:
        pass
    
    # Пробуем как username
    user = await db.get_user_by_username(identifier)
    return user


def format_user_link(user: dict) -> str:
    """Форматирует ссылку на юзера"""
    uid = user["user_id"]
    uname = user.get("username")
    if uname:
        return f"@{uname} (ID: {uid})"
    return f"ID: {uid}"


# ==================== HELP ====================

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка для админа"""
    if message.from_user.id != ADMIN_ID:
        return
    
    text = """🔧 <b>Админ-команды:</b>

<b>📊 Статистика:</b>
/admin — общая статистика бота

<b>👤 Юзеры:</b>
/user @username или ID — детальная инфа
/give @username 50 USDT — выдать баланс
/take @username 50 USDT — забрать баланс
/ban @username или ID — забанить
/unban @username или ID — разбанить

<b>📢 Рассылка:</b>
/broadcast Текст — отправить всем активным

<b>🧹 Модерация:</b>
/ban_inactive 30 — бан неактивных N дней

<b>🌐 Веб-панель:</b>
http://IP:8081/admin — полная БД с фильтрами
(запусти admin_panel.py отдельно)

<i>Все команды принимают @username или числовой ID</i>"""
    
    await message.answer(text, parse_mode="HTML")


# ==================== STATS ====================

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    stats = await db.get_admin_stats()
    await message.answer(get_text("admin_stats", **stats), parse_mode="HTML")


# ==================== USER INFO ====================

@router.message(Command("user"))
async def cmd_user(message: Message):
    """Детальная инфа по юзеру: /user @username или /user 123456"""
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /user @username или /user 123456789")
        return
    
    user = await resolve_user(args[1])
    if not user:
        await message.answer("❌ Юзер не найден")
        return
    
    uid = user["user_id"]
    
    # Основная инфа
    uname = user.get("username") or "—"
    tier = user.get("tier") or "нет"
    until = user.get("subscription_until")
    if until:
        if isinstance(until, str):
            until = datetime.fromisoformat(until)
        until_str = until.strftime("%d.%m.%Y")
    else:
        until_str = "—"
    
    banned = "🚫 ДА" if user.get("banned") else "нет"
    bal_ton = user.get("balance_ton", 0)
    bal_usdt = user.get("balance_usdt", 0)
    created = user.get("created_at", "—")
    
    # Реферал
    referred_by = user.get("referred_by")
    if referred_by:
        referrer = await db.get_user(referred_by)
        ref_str = format_user_link(referrer) if referrer else f"ID: {referred_by}"
    else:
        ref_str = "—"
    
    # Рефералы юзера
    ref_stats = await db.get_referral_stats(uid)
    
    # Отслеживаемые аккаунты
    tracking = await db.get_user_tracking(uid)
    tracking_count = len(tracking)
    tracking_list = ", ".join([f"@{t['twitter_username']}" for t in tracking[:10]])
    if tracking_count > 10:
        tracking_list += f" (+{tracking_count - 10})"
    
    # Платежи
    payments = await db.get_user_payments(uid)
    total_paid = sum(p.get("amount", 0) for p in payments if p.get("status") == "paid")
    
    # Выводы
    withdrawals = await db.get_user_withdrawals(uid)
    total_withdrawn = sum(w.get("amount", 0) for w in withdrawals)
    
    text = f"""👤 <b>Юзер:</b> @{uname}
🆔 ID: <code>{uid}</code>
📅 Регистрация: {created}
🚫 Бан: {banned}

<b>💎 Подписка:</b>
├ Тариф: {tier}
└ До: {until_str}

<b>💰 Баланс:</b>
├ TON: {bal_ton:.4f}
└ USDT: {bal_usdt:.2f}

<b>👥 Рефералка:</b>
├ Пригласил: {ref_str}
├ Привёл: {ref_stats['invited']} чел
├ Оплатили: {ref_stats['paid']} чел
├ Заработал TON: {ref_stats['earned_ton']}
└ Заработал USDT: {ref_stats['earned_usdt']}

<b>💳 Платежи:</b>
├ Всего оплат: {len([p for p in payments if p.get('status') == 'paid'])}
└ Сумма: ~${total_paid:.2f}

<b>📤 Выводы:</b>
├ Всего: {len(withdrawals)}
└ Сумма: ~${total_withdrawn:.2f}

<b>📋 Отслеживает ({tracking_count}):</b>
{tracking_list or '—'}
"""
    
    await message.answer(text, parse_mode="HTML")


# ==================== GIVE / TAKE ====================

@router.message(Command("give"))
async def cmd_give(message: Message):
    """Выдать баланс: /give @username 50 USDT или /give 123456 50 TON"""
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 4:
        await message.answer("Использование: /give @username 50 USDT")
        return
    
    user = await resolve_user(args[1])
    if not user:
        await message.answer("❌ Юзер не найден")
        return
    
    try:
        amount = float(args[2])
    except:
        await message.answer("❌ Неверная сумма")
        return
    
    currency = args[3].upper()
    if currency == "TON":
        currency = "TONCOIN"
    if currency not in ["TONCOIN", "USDT"]:
        await message.answer("❌ Валюта: USDT или TON")
        return
    
    await db.add_balance(user["user_id"], currency, amount)
    await db.log_admin_action(ADMIN_ID, "give", user["user_id"], f"{amount} {currency}")
    
    cur_label = "TON" if currency == "TONCOIN" else "USDT"
    await message.answer(f"✅ {format_user_link(user)}: +{amount} {cur_label}", parse_mode="HTML")
    logger.info(f"Admin give: {user['user_id']} +{amount} {currency}")


@router.message(Command("take"))
async def cmd_take(message: Message):
    """Забрать баланс: /take @username 50 USDT"""
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 4:
        await message.answer("Использование: /take @username 50 USDT")
        return
    
    user = await resolve_user(args[1])
    if not user:
        await message.answer("❌ Юзер не найден")
        return
    
    try:
        amount = float(args[2])
    except:
        await message.answer("❌ Неверная сумма")
        return
    
    currency = args[3].upper()
    if currency == "TON":
        currency = "TONCOIN"
    if currency not in ["TONCOIN", "USDT"]:
        await message.answer("❌ Валюта: USDT или TON")
        return
    
    field = "balance_ton" if currency == "TONCOIN" else "balance_usdt"
    current = user.get(field, 0)
    to_take = min(current, amount)
    
    if to_take <= 0:
        await message.answer(f"❌ У юзера нет {currency}")
        return
    
    await db.deduct_balance(user["user_id"], currency, to_take)
    await db.log_admin_action(ADMIN_ID, "take", user["user_id"], f"{to_take} {currency}")
    
    cur_label = "TON" if currency == "TONCOIN" else "USDT"
    await message.answer(f"✅ {format_user_link(user)}: -{to_take} {cur_label} (было: {current})", parse_mode="HTML")
    logger.info(f"Admin take: {user['user_id']} -{to_take} {currency}")


# ==================== BAN / UNBAN ====================

@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /ban @username или /ban 123456")
        return
    
    user = await resolve_user(args[1])
    if not user:
        await message.answer("❌ Юзер не найден")
        return
    
    await db.ban_user(user["user_id"])
    await db.log_admin_action(ADMIN_ID, "ban", user["user_id"])
    
    await message.answer(f"🚫 {format_user_link(user)} забанен", parse_mode="HTML")
    logger.info(f"Admin ban: {user['user_id']}")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /unban @username или /unban 123456")
        return
    
    user = await resolve_user(args[1])
    if not user:
        await message.answer("❌ Юзер не найден")
        return
    
    await db.unban_user(user["user_id"])
    await db.log_admin_action(ADMIN_ID, "unban", user["user_id"])
    
    await message.answer(f"✅ {format_user_link(user)} разбанен", parse_mode="HTML")
    logger.info(f"Admin unban: {user['user_id']}")


# ==================== BROADCAST ====================

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    """Рассылка всем активным: /broadcast Текст сообщения"""
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Использование: /broadcast Текст сообщения")
        return
    
    # Получаем всех активных юзеров
    users = await db.get_all_active_users()
    
    status = await message.answer(f"📢 Рассылка {len(users)} юзерам...")
    
    sent = 0
    failed = 0
    
    for user in users:
        try:
            await bot.send_message(user["user_id"], text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # Антифлуд
        except Exception as e:
            failed += 1
            logger.debug(f"Broadcast to {user['user_id']} failed: {e}")
    
    await db.log_admin_action(ADMIN_ID, "broadcast", None, f"sent={sent}, failed={failed}")
    
    await status.edit_text(f"✅ Рассылка завершена\n\n📤 Отправлено: {sent}\n❌ Ошибок: {failed}")
    logger.info(f"Broadcast: sent={sent}, failed={failed}")


# ==================== BAN INACTIVE ====================

@router.message(Command("ban_inactive"))
async def cmd_ban_inactive(message: Message):
    """Бан неактивных: /ban_inactive 30 (дней)"""
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /ban_inactive 30 (дней без активности)")
        return
    
    try:
        days = int(args[1])
    except:
        await message.answer("❌ Укажите число дней")
        return
    
    if days < 7:
        await message.answer("❌ Минимум 7 дней")
        return
    
    # Находим неактивных
    inactive = await db.get_inactive_users(days)
    
    if not inactive:
        await message.answer(f"✅ Нет неактивных юзеров (>{days} дней)")
        return
    
    await message.answer(f"⚠️ Найдено {len(inactive)} неактивных юзеров. Баним...")
    
    banned = 0
    for user in inactive:
        await db.ban_user(user["user_id"])
        banned += 1
    
    await db.log_admin_action(ADMIN_ID, "ban_inactive", None, f"days={days}, banned={banned}")
    
    await message.answer(f"✅ Забанено {banned} неактивных юзеров (>{days} дней)")
    logger.info(f"Ban inactive: {banned} users (>{days} days)")


""" Локализация бота (русский) """

TEXTS = {
    "welcome_new": """👋 Привет!

Я отслеживаю Twitter аккаунты и мгновенно отправляю тебе новые твиты прямо в Telegram!

⚡️ Как это работает:
1. Добавляешь Twitter аккаунты
2. Получаешь уведомления за секунды

🎁 Попробуй бесплатный триал на 1 день!""",

    "welcome_subscribed": """🏠 <b>Главное меню</b>

📊 Подписка: <b>{tier}</b>
⏰ Активна до: <b>{until}</b>
👥 Аккаунтов: <b>{current}/{max}</b>
""",

    "welcome_expired": """⚠️ <b>Подписка истекла</b>

Отслеживание приостановлено.
Оформи подписку!""",

    "banned": "🚫 Аккаунт заблокирован.",

    "trial_activated": """✅ <b>Триал активирован!</b>

📅 Действует: 1 день
👤 Лимит: 1 аккаунт
""",

    "trial_already_used": "❌ Вы уже использовали пробный период.",

    "accounts_list": """📋 <b>Мои аккаунты ({current}/{max})</b>

Нажмите на аккаунт для настройки фильтров:""",

    "accounts_empty": """📋 <b>Мои аккаунты ({current}/{max})</b>

У вас пока нет отслеживаемых аккаунтов.""",

    "account_settings": """⚙️ <b>Настройки @{username}</b>

🔄 Ретвиты: {rt}
💬 Ответы: {rp}
🌐 Перевод на русский: {tr}
🔗 Ссылка на пост: {lk}""",

    "account_added": "✅ Аккаунт <b>@{username}</b> добавлен!",

    "account_removed": "🗑 Аккаунт <b>@{username}</b> удалён.",

    "account_not_found": "❌ Twitter аккаунт <b>@{username}</b> не найден.",

    "account_already_tracking": "⚠️ Вы уже отслеживаете <b>@{username}</b>.",

    "account_limit_reached": "❌ Достигнут лимит ({max}). Повысьте тариф.",

    "enter_username": "📝 Введите Twitter username (или несколько через пробел/запятую):",

    "no_subscription": "❌ Нужна подписка.",

    "filter_updated": "✅ Фильтр обновлён!",

    "subscription_choose": """💎 <b>Выберите тариф</b>

⭐ Base — $10/мес (30 аккаунтов)
💎 Pro — $40/мес (200 аккаунтов)""",

    "subscription_active": """💎 <b>Ваша подписка</b>

📊 Тариф: <b>{tier}</b>
💰 Цена: <b>${price}/мес</b>
👥 Лимит: <b>{max}</b> аккаунтов
⏰ До: <b>{until}</b>
📅 Осталось: <b>{days_left}</b> дн.
""",

    "choose_currency": "💳 Выберите валюту оплаты:",

    "invoice_created": """💳 <b>Счёт создан</b>

💰 Сумма: <b>{amount} {currency}</b>
📊 Тариф: <b>{tier}</b>
""",

    "payment_success": """✅ <b>Оплата успешна!</b>

📊 Тариф: <b>{tier}</b>
⏰ До: <b>{until}</b>

Спасибо! 🎉""",

    "referral_menu": """👥 <b>Реферальная программа</b>

30% от каждой оплаты друзей навсегда!

🔗 Ссылка: <code>{link}</code>

📊 Приглашено: <b>{invited}</b> | Оплатили: <b>{paid}</b>
💎 Заработано TON: <b>{earned_ton}</b>
💵 Заработано USDT: <b>{earned_usdt}</b>

💰 Доступно для вывода:
💎 TON: <b>{balance_ton}</b>
💵 USDT: <b>{balance_usdt}</b>
""",

    "help": """❓ <b>Помощь</b>

1. Оформите подписку или триал
2. Добавьте Twitter аккаунты
3. Настройте фильтры для каждого
4. Получайте уведомления!

Вопросы: @{support}""",

    "alert_new_post": "📝 <b>Новый пост от @{username}</b>",
    "alert_retweet": "🔄 <b>Ретвит от @{username}</b>",
    "alert_reply": "💬 <b>Ответ от @{username}</b>",

    "reminder_3_days": "⏰ Подписка истекает через <b>3 дня</b>!",
    "reminder_2_days": "⏰ Осталось <b>2 дня</b>!",
    "reminder_1_day": "🚨 Подписка истекает <b>ЗАВТРА</b>!",
    "subscription_expired": "❌ Подписка истекла. Отслеживание приостановлено.",

    "admin_stats": """📊 <b>Статистика</b>

👥 Юзеров: {total_users}
💎 Подписок: {active_subs} (Base: {base}, Pro: {pro})
💰 Доход: ${total_income} (мес: ${month_income})
🔄 Акков: {tracking} | 🚫 Бан: {banned}
""",

    "admin_balance_given": "✅ @{username}: + ${amount}",
    "admin_user_banned": "🚫 @{username} забанен",
    "admin_user_unbanned": "✅ @{username} разбанен",
    "admin_user_not_found": "❌ Юзер не найден",

    # Новые тексты для batch-добавления
    "batch_results": """📋 <b>Результат добавления ({added}/{total})</b>

{details}""",

    "batch_added": "✅ @{username}",
    "batch_already": "⚠️ @{username} — уже отслеживается",
    "batch_not_found": "❌ @{username} — не найден",
    "batch_limit": "🚫 @{username} — лимит достигнут",
    "batch_invalid": "❌ «{raw}» — невалидный username",
}


def get_text(key: str, **kwargs) -> str:
    text = TEXTS.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text


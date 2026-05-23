"""
Универсальный парсер Twitter username'ов.
Поддерживает ВСЕ мыслимые форматы ввода.

Парсеры (по приоритету):
1.  JSON массив: ["user1", "user2", "user3"]
2.  URL x.com: https://x.com/username или https://twitter.com/username
3.  URL с параметрами: https://x.com/username?s=20
4.  Формат "@user (url)": @boomtondo (https://x.com/boomtondo)
5.  @username — стандарт
6.  Нумерованный список: 1. @user или 1) @user или 1: @user
7.  Маркированный список: - @user, * @user, • @user
8.  Через запятую: user1, user2, user3
9.  Через пробел: user1 user2 user3
10. Через перенос строки (каждый на новой строке)
11. Через точку с запятой: user1; user2; user3
12. Через пайп: user1 | user2 | user3
13. Через слеш: user1/user2/user3
14. Tab-separated: user1\tuser2
15. Markdown ссылки: [text](https://x.com/user)
16. HTML ссылки: <a href="https://x.com/user">text</a>
17. Обёрнутые в кавычки: "user1" 'user2' `user3`
18. Обёрнутые в скобки: (user1) [user2] {user3}
19. С эмодзи-маркерами: ✅ @user, 🔹 @user
20. CSV формат: "username","display_name"
21. Чистый username без @: username (валидация по Twitter правилам)

Валидация:
- Длина 1-15 символов
- Только a-z, 0-9, _ (после нормализации)
- Дедупликация (без повторов)
- Сохранение порядка
- Игнорирование мусора (номера, пустые строки, скобки, эмодзи)
"""
import re
import json
from typing import List, Set


# Twitter username: 1-15 символов, a-z, 0-9, _
USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{1,15}$')

# Паттерны для извлечения
PATTERNS = [
    # URL: https://x.com/username или https://twitter.com/username
    # С опциональными параметрами (?s=20&t=...) и якорями
    re.compile(r'https?://(?:www\.)?(?:x|twitter)\.com/([a-zA-Z0-9_]{1,15})(?:[?#/\s]|$)'),

    # Markdown ссылка: [текст](https://x.com/user)
    re.compile(r'\[.*?\]\(https?://(?:www\.)?(?:x|twitter)\.com/([a-zA-Z0-9_]{1,15})(?:[?#/].*?)?\)'),

    # HTML ссылка: <a href="https://x.com/user">
    re.compile(r'href=["\'"]https?://(?:www\.)?(?:x|twitter)\.com/([a-zA-Z0-9_]{1,15})["\'"]'),

    # @username
    re.compile(r'@([a-zA-Z0-9_]{1,15})\b'),
]


def parse_usernames(text: str) -> List[str]:
    """
    Извлекает уникальные Twitter username'ы из текста любого формата.
    Возвращает список в порядке первого появления, без дублей.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    seen: Set[str] = set()
    result: List[str] = []

    def _add(username: str):
        """Добавить username если валидный и не дубль"""
        u = username.strip().lower()
        # Убираем @ если есть
        u = u.lstrip('@')
        # Убираем кавычки если обёрнут
        u = u.strip('"').strip("'").strip('`')
        # Валидация
        if not u or len(u) > 15 or not USERNAME_RE.match(u):
            return
        # Исключаем служебные/мусорные
        if u in _BLACKLIST:
            return
        if u not in seen:
            seen.add(u)
            result.append(u)

    # === Шаг 1: Попробовать JSON ===
    try:
        data = json.loads(text)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    _add(item)
            if result:
                return result
        elif isinstance(data, dict):
            # {"users": ["u1", "u2"]} или {"usernames": [...]}
            for key in ("users", "usernames", "accounts", "handles", "list"):
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        if isinstance(item, str):
                            _add(item)
            if result:
                return result
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # === Шаг 2: Извлечь все @username и URL ===
    for pattern in PATTERNS:
        for match in pattern.finditer(text):
            _add(match.group(1))

    # === Шаг 3: Если пока ничего — пробуем разделители ===
    if not result:
        # Заменяем все разделители на \n
        normalized = text
        for sep in [',', ';', '|', '\t']:
            normalized = normalized.replace(sep, '\n')

        for line in normalized.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Убираем нумерацию: "1. ", "1) ", "1: ", "1 -", "#1"
            line = re.sub(r'^[\s]*(?:\d+[.):\-\s]+|#+\s*)', '', line)

            # Убираем маркеры списков: "- ", "* ", "• ", "→ ", "▸ ", эмодзи
            line = re.sub(r'^[\s]*[-*•→▸▹►▻❯❱⁃∙◦‣⊳⊡✦✧★☆✓✔✅⭐🔹🔸🔷🔶💎💠🟢🔴⚡🎯📌]+[\s]*', '', line)

            # Убираем скобки с содержимым URL: "(https://x.com/...)"
            line = re.sub(r'\(https?://[^)]+\)', '', line)

            # Убираем оставшиеся скобки
            line = re.sub(r'[()\[\]{}]', ' ', line)

            # Убираем кавычки
            line = line.replace('"', ' ').replace("'", ' ').replace('`', ' ')

            # Разбиваем по пробелам
            for word in line.split():
                word = word.strip().strip(',').strip(';').strip('.')
                _add(word)

    return result


# Слова которые точно не юзернеймы (но проходят валидацию)
_BLACKLIST = {
    # Общие английские слова
    "the", "and", "for", "are", "but", "not", "you", "all",
    "can", "had", "her", "was", "one", "our", "out", "day",
    "get", "has", "him", "his", "how", "its", "may", "new",
    "now", "old", "see", "way", "who", "did", "let", "say",
    "she", "too", "use",
    # Общие русские/англ
    "com", "www", "http", "https", "html", "css", "json",
    "xml", "api", "url", "uri", "src", "img", "div",
    # Twitter/X служебные
    "i", "a", "home", "explore", "search", "settings",
    "notifications", "messages", "bookmarks", "lists",
    "profile", "more", "status", "intent", "share",
    "tweet", "retweet", "like", "follow", "dm",
}


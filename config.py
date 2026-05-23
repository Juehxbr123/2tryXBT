"""
Конфигурация бота из .env файла
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Tuple, Optional

BOT_DIR = Path(__file__).parent.absolute()
load_dotenv(BOT_DIR / ".env")

# Telegram
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "support")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не задан в .env")
    sys.exit(1)

if not ADMIN_ID:
    print("❌ ADMIN_ID не задан в .env")
    sys.exit(1)

# xRocket Pay
XROCKET_TOKEN: str = os.getenv("XROCKET_TOKEN", "")
XROCKET_API_URL: str = "https://pay.xrocket.tg/"

if not XROCKET_TOKEN:
    print("⚠️ XROCKET_TOKEN не задан, оплата не будет работать")

# Минимальная сумма вывода рефералки
MIN_WITHDRAW_TON: float = float(os.getenv("MIN_WITHDRAW_TON", "0.5"))
MIN_WITHDRAW_USDT: float = float(os.getenv("MIN_WITHDRAW_USDT", "1"))

# Twitter аккаунты (до 50)
def get_twitter_accounts() -> List[Tuple[str, str]]:
    accounts = []
    main_auth = os.getenv("TWITTER_AUTH_TOKEN")
    main_ct0 = os.getenv("TWITTER_CT0")
    if main_auth and main_ct0:
        accounts.append((main_auth, main_ct0))
    for i in range(1, 51):
        auth = os.getenv(f"TWITTER_ACCOUNT_{i}_AUTH")
        ct0 = os.getenv(f"TWITTER_ACCOUNT_{i}_CT0")
        if auth and ct0:
            accounts.append((auth, ct0))
    return accounts

TWITTER_ACCOUNTS: List[Tuple[str, str]] = get_twitter_accounts()

if not TWITTER_ACCOUNTS:
    print("⚠️ Twitter аккаунты не настроены, будет только Nitter")

PROXY: Optional[str] = os.getenv("PROXY")

# Twitter API
TWITTER_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
TWITTER_GRAPHQL_USER = "https://x.com/i/api/graphql/IGgvgiOx4QZndDHuD3x9TQ/UserByScreenName"
TWITTER_GRAPHQL_TWEETS = "https://x.com/i/api/graphql/r4C5KgRvWxMOHyE4sZRmzg/UserTweets"

NITTER_MIRRORS = [
    # Tier 1: Высокий uptime, RSS работает
    "https://xcancel.com",
    "https://nitter.privacyredirect.com",
    "https://nitter.poast.org",
    "https://nitter.net",
    # Tier 2: Хороший uptime
    "https://nitter.privacydev.net",
    "https://lightbrd.com",
    "https://nitter.space",
    "https://nuku.trabun.org",
    # Tier 3: Дополнительные
    "https://nitter.catsarch.com",
    "https://nitter.tiekoetter.com",
    "https://twiiit.com",
    "https://nitter.pek.li",
    "https://nitter.10qt.net",
]

# Тарифы
TIERS = {
    "base": {"price": 10, "accounts": 30, "name": "Base"},
    "pro": {"price": 40, "accounts": 200, "name": "Pro"},
}

TRIAL_DAYS = 1
TRIAL_ACCOUNTS = 1
REFERRAL_PERCENT = 30
DATABASE_PATH = str(BOT_DIR / "bot_database.db")
LOGS_DIR = BOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)


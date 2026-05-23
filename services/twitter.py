"""
Twitter MEGA Parser — все источники данных:
1. GraphQL API (с auth токенами, если есть)
2. Syndication API (бесплатно, без лимитов)
3. Nitter RSS (15+ зеркал с автофейловером)
4. FxTwitter API (проверка существования)

Все источники работают ПАРАЛЛЕЛЬНО — кто первый ответил, того и берём.
"""
import httpx
import asyncio
import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET
from config import (
    TWITTER_BEARER, TWITTER_GRAPHQL_USER, TWITTER_GRAPHQL_TWEETS,
    TWITTER_ACCOUNTS, PROXY
)
import logging

logger = logging.getLogger(__name__)


@dataclass
class TwitterAccount:
    auth_token: str
    ct0: str
    rate_limited_until: float = 0
    request_count: int = 0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.rate_limited_until

    def mark_rate_limited(self, seconds: int = 900):
        self.rate_limited_until = time.time() + seconds

    def increment_count(self):
        self.request_count += 1


@dataclass
class Tweet:
    id: str
    text: str
    created_at: datetime
    author_username: str
    url: str
    is_retweet: bool = False
    is_reply: bool = False
    retweeted_from: str = None
    media_url: str = None


NITTER_MIRRORS = [
    # Tier 1: Высокий uptime (>90%), RSS работает
    "https://xcancel.com",            # 97% uptime, RSS ✅, 493 аккаунтов
    "https://nitter.privacyredirect.com",  # 91% uptime, RSS ✅
    "https://nitter.poast.org",       # 86% uptime, RSS ✅, 100+ аккаунтов
    "https://nitter.net",             # 94% uptime, RSS ✅ (оригинал)
    # Tier 2: Хороший uptime (>85%)
    "https://nitter.privacydev.net",  # работает стабильно
    "https://lightbrd.com",           # 95% uptime, NSFW support
    "https://nitter.space",           # 96% uptime
    "https://nuku.trabun.org",        # 95% uptime
    # Tier 3: Дополнительные зеркала
    "https://nitter.catsarch.com",
    "https://nitter.tiekoetter.com",
    "https://twiiit.com",
    "https://nitter.pek.li",
    "https://nitter.aishiteiru.moe",
    "https://nitter.aosus.link",
    "https://nitter.10qt.net",
]

# FxTwitter API — бесплатный, без лимитов, без API ключей!
FXTWITTER_API = "https://api.fxtwitter.com"
VXTWITTER_API = "https://api.vxtwitter.com"

SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{}"


class TwitterService:
    USER_FEATURES = {
        "hidden_profile_subscriptions_enabled": True,
        "rweb_tipjar_consumption_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "verified_phone_label_enabled": False,
        "subscriptions_verification_info_is_identity_verified_enabled": True,
        "highlights_tweets_tab_ui_enabled": True,
        "creator_subscriptions_tweet_preview_api_enabled": True,
    }
    TWEETS_FEATURES = {
        **USER_FEATURES,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "freedom_of_speech_not_reach_fetch_enabled": True,
    }

    def __init__(self):
        self.accounts = [TwitterAccount(a, c) for a, c in TWITTER_ACCOUNTS]
        self.client = httpx.AsyncClient(
            timeout=15.0, proxy=PROXY, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        self._nitter_fails: Dict[str, float] = {}
        self._user_id_cache: Dict[str, str] = {}

    def _get_best_account(self) -> Optional[TwitterAccount]:
        avail = [a for a in self.accounts if a.is_available]
        return min(avail, key=lambda a: a.request_count) if avail else None

    def get_available_accounts_count(self) -> int:
        return len([a for a in self.accounts if a.is_available])

    def all_rate_limited(self) -> bool:
        return not self.accounts or all(not a.is_available for a in self.accounts)

    def _headers(self, acc: TwitterAccount) -> dict:
        return {
            "authorization": f"Bearer {TWITTER_BEARER}",
            "x-csrf-token": acc.ct0,
            "cookie": f"auth_token={acc.auth_token}; ct0={acc.ct0}",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def _working_mirrors(self) -> List[str]:
        now = time.time()
        w = [m for m in NITTER_MIRRORS if now - self._nitter_fails.get(m, 0) > 300]
        return w or NITTER_MIRRORS

    # ==================== CHECK USER ====================
    async def check_user_exists(self, username: str) -> Tuple[bool, Optional[str]]:
        username = username.lstrip("@").lower()
        if username in self._user_id_cache:
            return True, self._user_id_cache[username]

        # Syndication
        try:
            r = await self.client.get(SYNDICATION_URL.format(username), timeout=8.0)
            if r.status_code == 200 and len(r.text) > 200:
                return True, None
        except:
            pass

        # GraphQL
        acc = self._get_best_account()
        if acc:
            try:
                r = await self.client.get(TWITTER_GRAPHQL_USER,
                    headers=self._headers(acc),
                    params={"variables": json.dumps({"screen_name": username}),
                            "features": json.dumps(self.USER_FEATURES)})
                acc.increment_count()
                if r.status_code == 429:
                    reset = int(r.headers.get("x-rate-limit-reset", 0))
                    acc.mark_rate_limited(max(60, reset - int(time.time())) if reset else 900)
                elif r.status_code == 200:
                    u = r.json().get("data", {}).get("user", {}).get("result", {})
                    if u and u.get("__typename") not in ("UserUnavailable", None):
                        uid = u.get("rest_id")
                        if uid:
                            self._user_id_cache[username] = uid
                        return True, uid
                    return False, None
            except Exception as e:
                logger.error(f"GraphQL check @{username}: {e}")

        # Nitter (пробуем все 15+ зеркал)
        for m in self._working_mirrors():
            try:
                r = await self.client.get(f"{m}/{username}/rss", timeout=8.0)
                if r.status_code == 200 and len(r.text) > 100:
                    return True, None
            except:
                self._nitter_fails[m] = time.time()
        
        # FxTwitter как последний fallback
        try:
            if await self.check_user_via_fxtwitter(username):
                return True, None
        except:
            pass
        
        return False, None

    # ==================== SYNDICATION ====================
    async def _fetch_syndication(self, username: str) -> Optional[List[Tweet]]:
        try:
            r = await self.client.get(SYNDICATION_URL.format(username), timeout=10.0)
            if r.status_code != 200 or len(r.text) < 200:
                return None
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">\s*({.+?})\s*</script>', r.text, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group(1))
            entries = data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
            tweets = []
            for e in entries[:10]:
                c = e.get("content", {})
                td = c.get("tweet", c)
                if not td or not td.get("id_str"):
                    continue
                tid = td["id_str"]
                text = td.get("text", "")
                try:
                    ca = datetime.strptime(td.get("created_at", ""), "%a %b %d %H:%M:%S %z %Y")
                except:
                    ca = datetime.now(timezone.utc)
                is_rt = "retweeted_tweet" in td
                rt_from = None
                if is_rt:
                    rt = td.get("retweeted_tweet", {})
                    rt_from = rt.get("user", {}).get("screen_name")
                    text = rt.get("text", text)
                is_rp = td.get("in_reply_to_status_id_str") is not None
                mu = None
                for md in td.get("mediaDetails", []):
                    if md.get("type") == "photo":
                        mu = md.get("media_url_https")
                        break
                tweets.append(Tweet(id=tid, text=text, created_at=ca,
                    author_username=username,
                    url=f"https://x.com/{username}/status/{tid}",
                    is_retweet=is_rt, is_reply=is_rp,
                    retweeted_from=rt_from, media_url=mu))
            if tweets:
                logger.info(f"Syndication: {len(tweets)} @{username}")
            return tweets or None
        except:
            return None

    # ==================== GRAPHQL ====================
    async def _fetch_graphql(self, username: str) -> Optional[List[Tweet]]:
        acc = self._get_best_account()
        if not acc:
            return None
        uid = self._user_id_cache.get(username)
        if not uid:
            ok, uid = await self.check_user_exists(username)
            if not ok or not uid:
                return None
        try:
            r = await self.client.get(TWITTER_GRAPHQL_TWEETS,
                headers=self._headers(acc),
                params={
                    "variables": json.dumps({"userId": uid, "count": 10,
                        "includePromotedContent": False, "withVoice": True}),
                    "features": json.dumps(self.TWEETS_FEATURES),
                    "fieldToggles": json.dumps({"withArticlePlainText": False})
                })
            acc.increment_count()
            if r.status_code == 429:
                reset = int(r.headers.get("x-rate-limit-reset", 0))
                acc.mark_rate_limited(max(60, reset - int(time.time())) if reset else 900)
                return None
            if r.status_code != 200:
                return None
            data = r.json()
            tweets = []
            for instr in data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", []):
                if instr.get("type") == "TimelineAddEntries":
                    for entry in instr.get("entries", []):
                        t = self._parse_gql(entry, username)
                        if t:
                            tweets.append(t)
            if tweets:
                logger.info(f"GraphQL: {len(tweets)} @{username}")
            return tweets or None
        except Exception as e:
            logger.error(f"GraphQL @{username}: {e}")
            return None

    def _parse_gql(self, entry: dict, username: str) -> Optional[Tweet]:
        try:
            c = entry.get("content", {})
            if c.get("entryType") != "TimelineTimelineItem":
                return None
            it = c.get("itemContent", {})
            if it.get("itemType") != "TimelineTweet":
                return None
            res = it.get("tweet_results", {}).get("result", {})
            if not res or res.get("__typename") == "TweetTombstone":
                return None
            if res.get("__typename") == "TweetWithVisibilityResults":
                res = res.get("tweet", res)
            lg = res.get("legacy", {})
            if not lg:
                return None
            is_rt = "retweeted_status_result" in lg
            rf = None
            if is_rt:
                rt = lg["retweeted_status_result"].get("result", {})
                if rt.get("__typename") == "TweetWithVisibilityResults":
                    rt = rt.get("tweet", rt)
                rl = rt.get("legacy", {})
                ru = rt.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                rf = ru.get("screen_name")
                text = rl.get("full_text", "")
                media = rl.get("extended_entities", {}).get("media", [])
            else:
                text = lg.get("full_text", "")
                media = lg.get("extended_entities", {}).get("media", [])
            is_rp = lg.get("in_reply_to_status_id_str") is not None
            mu = None
            for m in media:
                if m.get("type") == "photo":
                    mu = m.get("media_url_https")
                    break
            try:
                ca = datetime.strptime(lg.get("created_at", ""), "%a %b %d %H:%M:%S %z %Y")
            except:
                ca = datetime.now(timezone.utc)
            tid = lg.get("id_str", res.get("rest_id", ""))
            if not tid:
                return None
            return Tweet(id=tid, text=text, created_at=ca,
                author_username=username, url=f"https://x.com/{username}/status/{tid}",
                is_retweet=is_rt, is_reply=is_rp, retweeted_from=rf, media_url=mu)
        except:
            return None

    # ==================== NITTER ====================
    async def _fetch_nitter_single(self, username: str, mirror: str) -> Optional[List[Tweet]]:
        """Один запрос к одному зеркалу"""
        try:
            r = await self.client.get(f"{mirror}/{username}/rss", timeout=8.0)
            if r.status_code != 200:
                self._nitter_fails[mirror] = time.time()
                return None
            txt = r.text.strip()
            if not txt or len(txt) < 100:
                return None
            root = ET.fromstring(txt)
            items = root.findall(".//item")
            if not items:
                return None
            tweets = []
            for item in items[:10]:
                t = self._parse_nitter(item, username, mirror)
                if t:
                    tweets.append(t)
            if tweets:
                logger.info(f"Nitter ({mirror}): {len(tweets)} @{username}")
                return tweets
        except Exception as e:
            self._nitter_fails[mirror] = time.time()
        return None

    async def _fetch_nitter(self, username: str) -> Optional[List[Tweet]]:
        """Параллельно запрашивает ТОП-3 зеркала — кто первый ответил, того и берём"""
        mirrors = self._working_mirrors()[:3]  # Берём 3 лучших
        if not mirrors:
            return None
        
        tasks = [asyncio.create_task(self._fetch_nitter_single(username, m)) for m in mirrors]
        
        result = None
        done_set = set()
        try:
            while tasks:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=8.0)
                if not done:
                    break
                for task in done:
                    done_set.add(task)
                    try:
                        r = task.result()
                        if r:
                            result = r
                            break
                    except:
                        pass
                if result:
                    break
                tasks = [t for t in tasks if t not in done_set]
        finally:
            for t in tasks:
                if t not in done_set:
                    t.cancel()
        return result

    def _parse_nitter(self, item, username: str, mirror: str) -> Optional[Tweet]:
        try:
            te = item.find("title")
            le = item.find("link")
            de = item.find("description")
            pe = item.find("pubDate")
            if te is None or le is None:
                return None
            title = te.text or ""
            link = le.text or ""
            desc = de.text if de is not None else ""
            pub = pe.text if pe is not None else ""
            m = re.search(r"/status/(\d+)", link)
            tid = m.group(1) if m else ""
            if not tid:
                return None
            is_rt = title.startswith("RT by")
            is_rp = title.startswith("R to")
            rf = None
            if is_rt:
                rm = re.search(r"RT by @\w+: (@(\w+))?", title)
                if rm and rm.group(2):
                    rf = rm.group(2)
            text = re.sub(r"<[^>]+>", "", desc or "").strip()
            mu = None
            if desc:
                im = re.search(r'<img src="([^"]+)"', desc)
                if im:
                    mu = im.group(1)
                    if mu.startswith("/"):
                        mu = f"{mirror}{mu}"
            try:
                ca = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
                ca = ca.replace(tzinfo=timezone.utc)
            except:
                ca = datetime.now(timezone.utc)
            return Tweet(id=tid, text=text, created_at=ca,
                author_username=username,
                url=f"https://x.com/{username}/status/{tid}",
                is_retweet=is_rt, is_reply=is_rp,
                retweeted_from=rf, media_url=mu)
        except:
            return None

    # ==================== FXTWITTER API ====================
    async def _fetch_fxtwitter(self, username: str, last_tweet_id: str = None) -> Optional[List[Tweet]]:
        """
        FxTwitter/vxTwitter API — бесплатный, без ключей, без жёстких лимитов!
        Используется для получения данных конкретного твита.
        Примечание: API работает по ID твита, не по timeline пользователя.
        Используем для проверки существования и как fallback.
        """
        # FxTwitter не даёт timeline, но можно использовать для проверки юзера
        # и как дополнительный источник данных о твите
        try:
            # Пробуем получить последний известный твит через FxTwitter
            if last_tweet_id:
                for api_base in [FXTWITTER_API, VXTWITTER_API]:
                    try:
                        url = f"{api_base}/{username}/status/{last_tweet_id}"
                        r = await self.client.get(url, timeout=8.0)
                        if r.status_code == 200:
                            data = r.json()
                            if data.get("code") == 200 and data.get("tweet"):
                                # Успешно — API работает
                                logger.debug(f"FxTwitter API works for @{username}")
                                return None  # Нет timeline, только подтверждение
                    except:
                        continue
        except Exception as e:
            logger.debug(f"FxTwitter @{username}: {e}")
        return None

    async def check_user_via_fxtwitter(self, username: str) -> bool:
        """Быстрая проверка существования через FixTweet embed"""
        try:
            # Пробуем получить любой контент юзера
            r = await self.client.get(
                f"https://fxtwitter.com/{username}",
                timeout=5.0,
                follow_redirects=False
            )
            # Если не 404 — юзер существует
            return r.status_code != 404
        except:
            return False

    # ==================== FETCH ====================
    async def fetch_tweets(self, username: str, use_graphql: bool = True) -> List[Tweet]:
        """
        Запускает ВСЕ источники ПАРАЛЛЕЛЬНО:
        1. GraphQL (если есть аккаунты и не rate limited)
        2. Syndication (бесплатно, без лимитов)
        3. Nitter RSS (15+ зеркал, автоматический failover)
        
        Кто первый вернул данные — того и берём.
        """
        username = username.lstrip("@").lower()
        tasks = []
        
        # GraphQL — только для платных и если есть аккаунты
        if use_graphql and not self.all_rate_limited():
            tasks.append(asyncio.create_task(self._fetch_graphql(username)))
        
        # Syndication — всегда (бесплатно, без лимитов)
        tasks.append(asyncio.create_task(self._fetch_syndication(username)))
        
        # Nitter RSS — всегда (15+ зеркал с автофейловером)
        tasks.append(asyncio.create_task(self._fetch_nitter(username)))

        if not tasks:
            return []

        result = None
        done_tasks = set()
        try:
            while tasks:
                done, tasks_set = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED, timeout=15.0)
                if not done:
                    break
                for task in done:
                    done_tasks.add(task)
                    try:
                        r = task.result()
                        if r:
                            result = r
                            break
                    except:
                        pass
                if result:
                    break
                tasks = [t for t in tasks if t not in done_tasks]
        finally:
            for t in tasks:
                if t not in done_tasks:
                    t.cancel()
                    try:
                        await t
                    except:
                        pass
        return result or []

    async def close(self):
        await self.client.aclose()


twitter_service = TwitterService()


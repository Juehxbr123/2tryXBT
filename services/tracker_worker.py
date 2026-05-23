"""
Воркер отслеживания Twitter
- Фикс: не шлёт старые посты при перезапуске
- Фикс: фильтрует Twitter Spaces (не твиты)
- Фикс: кнопка @username не заменяет алерт
- Фикс: чистит мусор Nitter из текста
- Ускорен интервал опроса
"""
import asyncio
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Set
from aiogram import Bot
from database import db
from services.twitter import twitter_service, Tweet
from services.translator import translate_to_russian
from keyboards import tweet_keyboard
from locales import get_text
import logging

logger = logging.getLogger(__name__)
MSK = timezone(timedelta(hours=3))
CAPTION_LIMIT = 1024
MSG_LIMIT = 4096


class TrackerWorker:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self._task: asyncio.Task = None
        self._last_ids: Dict[str, str] = {}
        self._trial_targets: Set[str] = set()
        self._initialized: Set[str] = set()  # Флаг первого запуска для каждого юзера

    def calculate_interval(self, n: int) -> float:
        """Интервал опроса — ускорен!"""
        a = twitter_service.get_available_accounts_count()
        if a < 1:
            # Без GraphQL аккаунтов — только Nitter/Syndication
            return max(15, 60 / max(n, 1))  # Было 30/120, стало 15/60
        return max(3, n / max(a, 1))  # Было 5/(n*2), стало 3/n

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Tracker worker started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Tracker worker stopped")

    async def _load_trial_targets(self):
        try:
            async with db._connection.execute(
                """SELECT DISTINCT t.twitter_username FROM tracking t
                   JOIN users u ON t.user_id = u.user_id
                   WHERE u.banned = 0 AND u.tier NOT IN ('trial')
                   AND u.subscription_until > datetime('now')""") as c:
                paid = {r["twitter_username"] for r in await c.fetchall()}
            async with db._connection.execute(
                """SELECT DISTINCT t.twitter_username FROM tracking t
                   JOIN users u ON t.user_id = u.user_id
                   WHERE u.banned = 0 AND u.tier = 'trial'
                   AND u.subscription_until > datetime('now')""") as c:
                trial = {r["twitter_username"] for r in await c.fetchall()}
            self._trial_targets = trial - paid
        except:
            self._trial_targets = set()

    async def _loop(self):
        cycle = 0
        while self.running:
            try:
                targets = await db.get_all_tracking_targets()
                if not targets:
                    await asyncio.sleep(5)
                    continue

                cycle += 1
                if cycle % 10 == 1:
                    await self._load_trial_targets()

                interval = self.calculate_interval(len(targets))
                if cycle % 20 == 1:
                    logger.info(
                        f"Цикл #{cycle} | Целей: {len(targets)} "
                        f"| Акков: {twitter_service.get_available_accounts_count()}"
                        f"/{len(twitter_service.accounts)} | {interval:.1f}с"
                    )

                start = time.time()
                await asyncio.gather(*[self._process(u) for u in targets])
                await asyncio.sleep(max(1.0, interval - (time.time() - start)))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker: {e}")
                await asyncio.sleep(5)

    async def _process(self, username: str):
        try:
            use_gql = username not in self._trial_targets
            tweets = await twitter_service.fetch_tweets(username, use_graphql=use_gql)
            if not tweets:
                return

            # Фильтруем Twitter Spaces — это не твиты!
            tweets = [t for t in tweets if "/spaces/" not in t.url.lower() and "/spaces/" not in t.text.lower()]
            if not tweets:
                return

            last_id = self._last_ids.get(username)
            if last_id is None:
                last_id = await db.get_tracking_last_tweet_id(username)
                if last_id:
                    self._last_ids[username] = last_id

            new = []
            for t in tweets:
                try:
                    if last_id and int(t.id) <= int(last_id):
                        continue
                except:
                    pass
                new.append(t)

            if not new:
                return

            new.sort(key=lambda t: int(t.id))
            latest_id = new[-1].id
            self._last_ids[username] = latest_id
            await db.update_last_tweet_id(username, latest_id)

            # ФИКС: При первом запуске НЕ слать старые посты!
            # Просто запоминаем последний ID и выходим
            if not last_id:
                logger.info(f"@{username}: initialized, skipping {len(new)} old tweets")
                return

            # Ещё один чек — если юзер только добавлен
            if username not in self._initialized:
                self._initialized.add(username)
                # Первый цикл после добавления — не шлём
                if len(new) > 3:
                    logger.info(f"@{username}: first cycle, skipping {len(new)} tweets")
                    return

            subs = await db.get_subscribers_for_target(username)
            if not subs:
                return

            # Шлём максимум 3 последних твита (не 5)
            for tweet in new[:3]:
                # Параллельная доставка всем подписчикам!
                await asyncio.gather(*[
                    self._safe_notify(sub, tweet) for sub in subs
                ])

        except Exception as e:
            logger.error(f"Process @{username}: {e}")

    async def _safe_notify(self, sub: dict, tweet: Tweet):
        """Обёртка для параллельной доставки — ловит все ошибки"""
        try:
            await self._notify(sub, tweet)
        except Exception as e:
            logger.error(f"Notify {sub['user_id']}: {e}")

    async def _notify(self, sub: dict, tweet: Tweet):
        if tweet.is_retweet and not sub.get("filter_retweets"):
            return
        if tweet.is_reply and not sub.get("filter_replies"):
            return

        link = tweet.url if sub.get("filter_link") else None

        # Сначала шлём БЕЗ перевода (мгновенно!)
        msg = self._format(tweet, link, None)
        kb = tweet_keyboard(tweet.author_username)

        sent_msg = None

        try:
            if tweet.media_url:
                caption = msg[:CAPTION_LIMIT]
                sent_msg = await self.bot.send_photo(
                    chat_id=sub["user_id"],
                    photo=tweet.media_url,
                    caption=caption,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            else:
                sent_msg = await self.bot.send_message(
                    chat_id=sub["user_id"],
                    text=msg[:MSG_LIMIT],
                    reply_markup=kb,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
        except Exception as e:
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                logger.warning(f"User {sub['user_id']} blocked bot")
            else:
                raise
            return

        # Перевод — делаем ПОСЛЕ отправки, потом редактируем сообщение
        if sub.get("filter_translate") and sent_msg and not tweet.media_url:
            try:
                tr = await translate_to_russian(tweet.text)
                if tr:
                    msg_with_tr = self._format(tweet, link, tr)
                    await sent_msg.edit_text(
                        msg_with_tr[:MSG_LIMIT],
                        reply_markup=kb,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
            except Exception:
                pass  # Перевод не критичен

    @staticmethod
    def _clean_text(text: str) -> str:
        """Убирает мусор Nitter из текста твита"""
        # Убираем ссылки на nitter зеркала
        text = re.sub(
            r'https?://(?:nitter\.net|xcancel\.com|nitter\.poast\.org|'
            r'nitter\.privacyredirect\.com|nitter\.privacydev\.net|'
            r'lightbrd\.com|nitter\.space|nuku\.trabun\.org|'
            r'nitter\.catsarch\.com|nitter\.tiekoetter\.com|'
            r'twiiit\.com|nitter\.pek\.li|nitter\.10qt\.net|'
            r'nitter\.aishiteiru\.moe|nitter\.aosus\.link)'
            r'/[^\s]*',
            '', text
        )
        # Убираем "— " в начале строки (nitter ставит перед ссылкой)
        text = re.sub(r'\n—\s*\n', '\n', text)
        text = re.sub(r'\n—\s*$', '', text)
        # Убираем лишние пустые строки подряд
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _format(self, t: Tweet, link: str = None, tr: str = None) -> str:
        if t.is_retweet:
            h = get_text("alert_retweet", username=t.author_username)
            if t.retweeted_from:
                h += f"\n<i>Оригинал: @{t.retweeted_from}</i>"
        elif t.is_reply:
            h = get_text("alert_reply", username=t.author_username)
        else:
            h = get_text("alert_new_post", username=t.author_username)

        # Чистим текст от мусора Nitter
        clean = self._clean_text(t.text)

        mx = 400 if t.media_url else 800
        txt = clean[:mx] + ("..." if len(clean) > mx else "")
        dt = t.created_at.astimezone(MSK).strftime("%d.%m.%Y %H:%M")

        msg = f"{h}\n\n{txt}\n\n🕐 {dt} МСК"
        if link:
            msg += f' • <a href="{link}">ссылка</a>'
        if tr:
            # Чистим перевод тоже
            tr = self._clean_text(tr)
            tmx = 300 if t.media_url else 600
            msg += f"\n\n🌐 <b>Перевод:</b>\n<i>{tr[:tmx]}{'...' if len(tr) > tmx else ''}</i>"
        return msg


tracker_worker: TrackerWorker = None


def init_tracker_worker(bot: Bot) -> TrackerWorker:
    global tracker_worker
    tracker_worker = TrackerWorker(bot)
    return tracker_worker


"""
База данных SQLite с aiosqlite
+ Автоматические миграции (не нужно удалять БД при патчах!)
"""
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from config import DATABASE_PATH
import asyncio
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()
        await self._run_migrations()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self):
        if self._connection:
            await self._connection.close()

    async def _create_tables(self):
        await self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                tier TEXT DEFAULT NULL,
                subscription_until TIMESTAMP DEFAULT NULL,
                trial_used INTEGER DEFAULT 0,
                referred_by INTEGER DEFAULT NULL,
                balance_ton REAL DEFAULT 0,
                balance_usdt REAL DEFAULT 0,
                banned INTEGER DEFAULT 0,
                reminder_3_sent INTEGER DEFAULT 0,
                reminder_2_sent INTEGER DEFAULT 0,
                reminder_1_sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                twitter_username TEXT NOT NULL,
                last_tweet_id TEXT,
                filter_retweets INTEGER DEFAULT 1,
                filter_replies INTEGER DEFAULT 1,
                filter_translate INTEGER DEFAULT 1,
                filter_link INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, twitter_username)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                tier TEXT NOT NULL,
                invoice_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                payment_amount REAL NOT NULL,
                payment_currency TEXT NOT NULL,
                commission REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tracking_user ON tracking(user_id);
            CREATE INDEX IF NOT EXISTS idx_tracking_username ON tracking(twitter_username);
            CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
            CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);

            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self._connection.commit()

    # ============ МИГРАЦИИ (автоматически добавляют недостающие колонки) ============

    async def _run_migrations(self):
        """
        Безопасные миграции — проверяем существование колонок
        и добавляем если их нет. Данные НЕ теряются!
        """
        logger.info("Running database migrations...")

        # Получаем список колонок каждой таблицы
        users_cols = await self._get_columns("users")
        tracking_cols = await self._get_columns("tracking")
        payments_cols = await self._get_columns("payments")

        migrations_applied = 0

        # --- users migrations ---
        user_migrations = {
            "balance_ton": "REAL DEFAULT 0",
            "balance_usdt": "REAL DEFAULT 0",
            "banned": "INTEGER DEFAULT 0",
            "reminder_3_sent": "INTEGER DEFAULT 0",
            "reminder_2_sent": "INTEGER DEFAULT 0",
            "reminder_1_sent": "INTEGER DEFAULT 0",
            "referred_by": "INTEGER DEFAULT NULL",
        }
        for col, col_type in user_migrations.items():
            if col not in users_cols:
                await self._connection.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                migrations_applied += 1
                logger.info(f"  Migration: users.{col} added")

        # --- tracking migrations ---
        tracking_migrations = {
            "filter_retweets": "INTEGER DEFAULT 1",
            "filter_replies": "INTEGER DEFAULT 1",
            "filter_translate": "INTEGER DEFAULT 1",
            "filter_link": "INTEGER DEFAULT 1",
        }
        for col, col_type in tracking_migrations.items():
            if col not in tracking_cols:
                await self._connection.execute(f"ALTER TABLE tracking ADD COLUMN {col} {col_type}")
                migrations_applied += 1
                logger.info(f"  Migration: tracking.{col} added")

        # --- payments migrations ---
        payment_migrations = {
            "paid_at": "TIMESTAMP DEFAULT NULL",
        }
        for col, col_type in payment_migrations.items():
            if col not in payments_cols:
                await self._connection.execute(f"ALTER TABLE payments ADD COLUMN {col} {col_type}")
                migrations_applied += 1
                logger.info(f"  Migration: payments.{col} added")

        if migrations_applied:
            await self._connection.commit()
            logger.info(f"  Applied {migrations_applied} migration(s)")
        else:
            logger.info("  No migrations needed")

    async def _get_columns(self, table_name: str) -> set:
        """Получить множество имён колонок таблицы"""
        async with self._connection.execute(f"PRAGMA table_info({table_name})") as cursor:
            rows = await cursor.fetchall()
            return {row[1] for row in rows}  # row[1] = column name

    # ============ USERS ============

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self._connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(self, user_id: int, username: str = None, referred_by: int = None) -> Dict[str, Any]:
        await self._connection.execute(
            "INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
            (user_id, username, referred_by))
        await self._connection.commit()
        return await self.get_user(user_id)

    async def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [user_id]
        await self._connection.execute(f"UPDATE users SET {fields} WHERE user_id = ?", values)
        await self._connection.commit()

    async def activate_trial(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if user and user["trial_used"]:
            return False
        until = datetime.now() + timedelta(days=1)
        await self._connection.execute(
            "UPDATE users SET tier = 'trial', subscription_until = ?, trial_used = 1 WHERE user_id = ?",
            (until, user_id))
        await self._connection.commit()
        return True

    async def activate_subscription(self, user_id: int, tier: str, extend: bool = False):
        user = await self.get_user(user_id)
        now = datetime.now()
        if extend and user.get("subscription_until"):
            cu = user["subscription_until"]
            if isinstance(cu, str):
                cu = datetime.fromisoformat(cu)
            base = cu if cu > now else now
        else:
            base = now
        until = base + timedelta(days=30)
        await self._connection.execute(
            """UPDATE users SET tier = ?, subscription_until = ?,
               reminder_3_sent = 0, reminder_2_sent = 0, reminder_1_sent = 0
               WHERE user_id = ?""", (tier, until, user_id))
        await self._connection.commit()

    async def expire_subscription(self, user_id: int):
        await self._connection.execute(
            "UPDATE users SET tier = NULL, subscription_until = NULL WHERE user_id = ?", (user_id,))
        await self._connection.commit()

    async def ban_user(self, user_id: int):
        async with self._lock:
            await self._connection.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (user_id,))
            await self._connection.execute("DELETE FROM tracking WHERE user_id = ?", (user_id,))
            await self._connection.commit()

    async def unban_user(self, user_id: int):
        await self._connection.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))
        await self._connection.commit()

    async def add_balance(self, user_id: int, currency: str, amount: float):
        async with self._lock:
            field = "balance_ton" if currency == "TONCOIN" else "balance_usdt"
            await self._connection.execute(f"UPDATE users SET {field} = {field} + ? WHERE user_id = ?", (amount, user_id))
            await self._connection.commit()

    async def deduct_balance(self, user_id: int, currency: str, amount: float) -> float:
        async with self._lock:
            field = "balance_ton" if currency == "TONCOIN" else "balance_usdt"
            user = await self.get_user(user_id)
            current = user.get(field, 0)
            deducted = min(current, amount)
            if deducted > 0:
                await self._connection.execute(f"UPDATE users SET {field} = {field} - ? WHERE user_id = ?", (deducted, user_id))
                await self._connection.commit()
            return deducted

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        async with self._connection.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    # ============ TRACKING ============

    async def add_tracking(self, user_id: int, twitter_username: str) -> bool:
        try:
            await self._connection.execute(
                "INSERT INTO tracking (user_id, twitter_username) VALUES (?, ?)",
                (user_id, twitter_username))
            await self._connection.commit()
            return True
        except:
            return False

    async def remove_tracking(self, user_id: int, twitter_username: str):
        await self._connection.execute(
            "DELETE FROM tracking WHERE user_id = ? AND twitter_username = ?",
            (user_id, twitter_username))
        await self._connection.commit()

    async def get_user_tracking(self, user_id: int) -> List[Dict[str, Any]]:
        async with self._connection.execute(
            "SELECT * FROM tracking WHERE user_id = ? ORDER BY added_at", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_user_tracking_count(self, user_id: int) -> int:
        async with self._connection.execute(
            "SELECT COUNT(*) as cnt FROM tracking WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_tracking_entry(self, user_id: int, twitter_username: str) -> Optional[Dict[str, Any]]:
        async with self._connection.execute(
            "SELECT * FROM tracking WHERE user_id = ? AND twitter_username = ?",
            (user_id, twitter_username)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_tracking_filter(self, user_id: int, twitter_username: str, field: str, value: int):
        await self._connection.execute(
            f"UPDATE tracking SET {field} = ? WHERE user_id = ? AND twitter_username = ?",
            (value, user_id, twitter_username))
        await self._connection.commit()

    async def update_all_tracking_filters(self, user_id: int, field: str, value: int):
        await self._connection.execute(
            f"UPDATE tracking SET {field} = ? WHERE user_id = ?",
            (value, user_id))
        await self._connection.commit()

    async def get_first_tracking_entry(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self._connection.execute(
            "SELECT * FROM tracking WHERE user_id = ? LIMIT 1", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_tracking_targets(self) -> List[str]:
        async with self._connection.execute(
            """SELECT DISTINCT t.twitter_username FROM tracking t
               JOIN users u ON t.user_id = u.user_id
               WHERE u.banned = 0 AND u.tier IS NOT NULL
               AND u.subscription_until > datetime('now')"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def get_tracking_last_tweet_id(self, twitter_username: str) -> Optional[str]:
        async with self._connection.execute(
            "SELECT last_tweet_id FROM tracking WHERE twitter_username = ? AND last_tweet_id IS NOT NULL LIMIT 1",
            (twitter_username,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def update_last_tweet_id(self, twitter_username: str, tweet_id: str):
        await self._connection.execute(
            "UPDATE tracking SET last_tweet_id = ? WHERE twitter_username = ?",
            (tweet_id, twitter_username))
        await self._connection.commit()

    async def get_subscribers_for_target(self, twitter_username: str) -> List[Dict[str, Any]]:
        async with self._connection.execute(
            """SELECT t.*, u.tier FROM tracking t
               JOIN users u ON t.user_id = u.user_id
               WHERE t.twitter_username = ? AND u.banned = 0
               AND u.tier IS NOT NULL AND u.subscription_until > datetime('now')""",
            (twitter_username,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ============ PAYMENTS ============

    async def create_payment(self, user_id: int, amount: float, currency: str, tier: str, invoice_id: str):
        await self._connection.execute(
            "INSERT INTO payments (user_id, amount, currency, tier, invoice_id) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, currency, tier, invoice_id))
        await self._connection.commit()

    async def get_payment_by_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        async with self._connection.execute(
            "SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def complete_payment(self, invoice_id: str):
        await self._connection.execute(
            "UPDATE payments SET status = 'paid', paid_at = ? WHERE invoice_id = ?",
            (datetime.now(), invoice_id))
        await self._connection.commit()

    async def expire_payment(self, invoice_id: str):
        await self._connection.execute(
            "UPDATE payments SET status = 'expired' WHERE invoice_id = ?", (invoice_id,))
        await self._connection.commit()

    # ============ REFERRALS ============

    async def add_referral_commission(self, referrer_id: int, referred_id: int,
                                       amount: float, currency: str, commission: float):
        await self._connection.execute(
            "INSERT INTO referrals (referrer_id, referred_id, payment_amount, payment_currency, commission) VALUES (?, ?, ?, ?, ?)",
            (referrer_id, referred_id, amount, currency, commission))
        field = "balance_ton" if currency == "TONCOIN" else "balance_usdt"
        await self._connection.execute(
            f"UPDATE users SET {field} = {field} + ? WHERE user_id = ?",
            (commission, referrer_id))
        await self._connection.commit()

    async def get_referral_stats(self, user_id: int) -> Dict[str, Any]:
        async with self._connection.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as c:
            invited = (await c.fetchone())[0]
        async with self._connection.execute(
            """SELECT COUNT(DISTINCT referred_id) FROM referrals
               WHERE referrer_id = ?""", (user_id,)) as c:
            paid = (await c.fetchone())[0]
        async with self._connection.execute(
            """SELECT COALESCE(SUM(CASE WHEN payment_currency='TONCOIN' THEN commission ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN payment_currency='USDT' THEN commission ELSE 0 END), 0)
               FROM referrals WHERE referrer_id = ?""", (user_id,)) as c:
            row = await c.fetchone()
            earned_ton = round(row[0], 4)
            earned_usdt = round(row[1], 2)
        return {"invited": invited, "paid": paid, "earned_ton": earned_ton, "earned_usdt": earned_usdt}

    async def get_user_referrals(self, user_id: int) -> List[Dict[str, Any]]:
        async with self._connection.execute(
            """SELECT u.user_id, u.username,
                      CASE WHEN EXISTS(SELECT 1 FROM referrals WHERE referred_id = u.user_id) THEN 1 ELSE 0 END as has_paid
               FROM users u WHERE u.referred_by = ? ORDER BY u.created_at DESC""",
            (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ============ ADMIN ============

    async def get_admin_stats(self) -> Dict[str, Any]:
        async with self._connection.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with self._connection.execute(
            "SELECT COUNT(*) FROM users WHERE tier IS NOT NULL AND subscription_until > datetime('now')") as c:
            active_subs = (await c.fetchone())[0]
        async with self._connection.execute(
            "SELECT COUNT(*) FROM users WHERE tier = 'base' AND subscription_until > datetime('now')") as c:
            base = (await c.fetchone())[0]
        async with self._connection.execute(
            "SELECT COUNT(*) FROM users WHERE tier = 'pro' AND subscription_until > datetime('now')") as c:
            pro = (await c.fetchone())[0]
        async with self._connection.execute("SELECT COUNT(*) FROM tracking") as c:
            tracking = (await c.fetchone())[0]
        async with self._connection.execute("SELECT COUNT(*) FROM users WHERE banned = 1") as c:
            banned = (await c.fetchone())[0]
        async with self._connection.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'") as c:
            total_income = round((await c.fetchone())[0], 2)
        async with self._connection.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM payments
               WHERE status = 'paid' AND paid_at > datetime('now', '-30 days')""") as c:
            month_income = round((await c.fetchone())[0], 2)
        return {
            "total_users": total_users, "active_subs": active_subs,
            "base": base, "pro": pro, "tracking": tracking,
            "banned": banned, "total_income": total_income, "month_income": month_income
        }

    async def get_expiring_users(self, days: int) -> List[Dict[str, Any]]:
        now = datetime.now()
        target = now + timedelta(days=days)
        async with self._connection.execute(
            """SELECT * FROM users WHERE tier IS NOT NULL
               AND subscription_until > ? AND subscription_until <= ?""",
            (now, target)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_expired_users(self) -> List[Dict[str, Any]]:
        async with self._connection.execute(
            """SELECT * FROM users WHERE tier IS NOT NULL
               AND subscription_until <= datetime('now')""") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def create_withdrawal(self, user_id: int, amount: float, currency: str):
        await self._connection.execute(
            "INSERT INTO withdrawals (user_id, amount, currency) VALUES (?, ?, ?)",
            (user_id, amount, currency))
        await self._connection.commit()

    # ============ ADMIN: Новые методы ============

    async def get_user_payments(self, user_id: int) -> List[Dict[str, Any]]:
        """Все платежи юзера"""
        async with self._connection.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_user_withdrawals(self, user_id: int) -> List[Dict[str, Any]]:
        """Все выводы юзера"""
        async with self._connection.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_all_active_users(self) -> List[Dict[str, Any]]:
        """Все активные (не забаненные) юзеры"""
        async with self._connection.execute(
            "SELECT * FROM users WHERE banned = 0") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_inactive_users(self, days: int) -> List[Dict[str, Any]]:
        """Юзеры без активной подписки, которые не заходили N дней"""
        async with self._connection.execute(
            """SELECT * FROM users 
               WHERE banned = 0 
               AND (subscription_until IS NULL OR subscription_until < datetime('now'))
               AND created_at < datetime('now', ? || ' days')""",
            (f"-{days}",)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def log_admin_action(self, admin_id: int, action: str, target_user_id: int = None, details: str = None):
        """Логирует админское действие"""
        await self._connection.execute(
            """INSERT INTO admin_logs (admin_id, action, target_user_id, details)
               VALUES (?, ?, ?, ?)""",
            (admin_id, action, target_user_id, details))
        await self._connection.commit()

    async def get_all_users_paginated(self, offset: int = 0, limit: int = 50, 
                                       search: str = None, tier_filter: str = None) -> Tuple[List[Dict], int]:
        """Все юзеры с пагинацией и фильтрами (для веб-панели)"""
        conditions = []
        params = []
        
        if search:
            conditions.append("(username LIKE ? OR CAST(user_id AS TEXT) LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        if tier_filter:
            if tier_filter == "active":
                conditions.append("tier IS NOT NULL AND subscription_until > datetime('now')")
            elif tier_filter == "expired":
                conditions.append("tier IS NOT NULL AND subscription_until <= datetime('now')")
            elif tier_filter == "banned":
                conditions.append("banned = 1")
            elif tier_filter == "trial":
                conditions.append("tier = 'trial'")
            else:
                conditions.append("tier = ?")
                params.append(tier_filter)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Считаем общее количество
        async with self._connection.execute(f"SELECT COUNT(*) FROM users {where}", params) as c:
            total = (await c.fetchone())[0]
        
        # Получаем страницу
        async with self._connection.execute(
            f"""SELECT * FROM users {where} 
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset]) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows], total


db = Database()

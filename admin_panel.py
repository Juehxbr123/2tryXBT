"""
Веб-панель администратора
Запускать отдельно: python admin_panel.py
Доступ: http://IP:8081/admin

Требует: pip install fastapi uvicorn aiosqlite
"""
import asyncio
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional
import os
import json

try:
    from fastapi import FastAPI, Request, Query, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    print("Установите зависимости: pip install fastapi uvicorn")
    exit(1)

# Конфигурация
BOT_DIR = Path(__file__).parent.absolute()
DATABASE_PATH = str(BOT_DIR / "bot_database.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change_me_please")  # Задай в .env!
PORT = int(os.getenv("ADMIN_PORT", "8081"))

app = FastAPI(title="Twitter Tracker Admin")


async def get_db():
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db


def check_auth(request: Request):
    """Простая проверка токена"""
    token = request.query_params.get("token") or request.headers.get("X-Admin-Token")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


# ==================== API ====================

@app.get("/api/users")
async def api_users(
    request: Request,
    offset: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    tier: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc"
):
    check_auth(request)
    db = await get_db()
    
    try:
        conditions = []
        params = []
        
        if search:
            conditions.append("(username LIKE ? OR CAST(user_id AS TEXT) LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        if tier:
            if tier == "active":
                conditions.append("tier IS NOT NULL AND subscription_until > datetime('now')")
            elif tier == "expired":
                conditions.append("(tier IS NULL OR subscription_until <= datetime('now'))")
            elif tier == "banned":
                conditions.append("banned = 1")
            else:
                conditions.append("tier = ?")
                params.append(tier)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Всего
        async with db.execute(f"SELECT COUNT(*) FROM users {where}", params) as c:
            total = (await c.fetchone())[0]
        
        # Данные
        allowed_sorts = ["created_at", "user_id", "username", "tier", "subscription_until"]
        sort_col = sort if sort in allowed_sorts else "created_at"
        order_dir = "DESC" if order.lower() == "desc" else "ASC"
        
        async with db.execute(
            f"SELECT * FROM users {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
            params + [limit, offset]
        ) as cursor:
            users = [dict(r) for r in await cursor.fetchall()]
        
        # Добавляем доп. инфу
        for user in users:
            uid = user["user_id"]
            async with db.execute(
                "SELECT COUNT(*) FROM tracking WHERE user_id = ?", (uid,)
            ) as c:
                user["tracking_count"] = (await c.fetchone())[0]
        
        return {"users": users, "total": total, "offset": offset, "limit": limit}
    finally:
        await db.close()


@app.get("/api/user/{user_id}")
async def api_user_detail(user_id: int, request: Request):
    check_auth(request)
    db = await get_db()
    
    try:
        # Юзер
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            user = dict(row)
        
        # Отслеживаемые
        async with db.execute(
            "SELECT * FROM tracking WHERE user_id = ?", (user_id,)
        ) as c:
            user["tracking"] = [dict(r) for r in await c.fetchall()]
        
        # Платежи
        async with db.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ) as c:
            user["payments"] = [dict(r) for r in await c.fetchall()]
        
        # Выводы
        async with db.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ) as c:
            user["withdrawals"] = [dict(r) for r in await c.fetchall()]
        
        # Рефералы
        async with db.execute(
            "SELECT * FROM users WHERE referred_by = ?", (user_id,)
        ) as c:
            user["referrals"] = [dict(r) for r in await c.fetchall()]
        
        # Реферальные комиссии
        async with db.execute(
            "SELECT * FROM referrals WHERE referrer_id = ? ORDER BY created_at DESC", (user_id,)
        ) as c:
            user["commissions"] = [dict(r) for r in await c.fetchall()]
        
        return user
    finally:
        await db.close()


@app.get("/api/stats")
async def api_stats(request: Request):
    check_auth(request)
    db = await get_db()
    
    try:
        stats = {}
        
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            stats["total_users"] = (await c.fetchone())[0]
        
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE tier IS NOT NULL AND subscription_until > datetime('now')"
        ) as c:
            stats["active_subs"] = (await c.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM users WHERE banned = 1") as c:
            stats["banned"] = (await c.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM tracking") as c:
            stats["total_tracking"] = (await c.fetchone())[0]
        
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'"
        ) as c:
            stats["total_revenue"] = round((await c.fetchone())[0], 2)
        
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM withdrawals"
        ) as c:
            stats["total_withdrawn"] = round((await c.fetchone())[0], 2)
        
        return stats
    finally:
        await db.close()


@app.get("/api/logs")
async def api_logs(request: Request, limit: int = 100):
    check_auth(request)
    db = await get_db()
    
    try:
        async with db.execute(
            "SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as c:
            logs = [dict(r) for r in await c.fetchall()]
        return {"logs": logs}
    finally:
        await db.close()


# ==================== HTML ПАНЕЛЬ ====================

ADMIN_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .loader { border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-8">🐦 Twitter Tracker Admin</h1>
        
        <!-- Stats -->
        <div id="stats" class="grid grid-cols-2 md:grid-cols-6 gap-4 mb-8"></div>
        
        <!-- Filters -->
        <div class="flex flex-wrap gap-4 mb-4">
            <input type="text" id="search" placeholder="Поиск по username/ID..." 
                   class="bg-gray-800 border border-gray-700 rounded px-4 py-2 w-64">
            <select id="tierFilter" class="bg-gray-800 border border-gray-700 rounded px-4 py-2">
                <option value="">Все</option>
                <option value="active">Активные</option>
                <option value="expired">Истекшие</option>
                <option value="trial">Триал</option>
                <option value="base">Base</option>
                <option value="pro">Pro</option>
                <option value="banned">Забаненные</option>
            </select>
            <button onclick="loadUsers()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded">🔍 Найти</button>
        </div>
        
        <!-- Users Table -->
        <div class="overflow-x-auto bg-gray-800 rounded-lg">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="px-4 py-3 text-left">ID</th>
                        <th class="px-4 py-3 text-left">Username</th>
                        <th class="px-4 py-3 text-left">Тариф</th>
                        <th class="px-4 py-3 text-left">До</th>
                        <th class="px-4 py-3 text-left">Баланс</th>
                        <th class="px-4 py-3 text-left">Трекинг</th>
                        <th class="px-4 py-3 text-left">Бан</th>
                        <th class="px-4 py-3 text-left">Регистрация</th>
                    </tr>
                </thead>
                <tbody id="usersTable"></tbody>
            </table>
        </div>
        
        <!-- Pagination -->
        <div id="pagination" class="flex justify-center gap-2 mt-4"></div>
        
        <!-- User Modal -->
        <div id="modal" class="fixed inset-0 bg-black bg-opacity-50 hidden flex items-center justify-center p-4">
            <div class="bg-gray-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xl font-bold">Детали пользователя</h2>
                    <button onclick="closeModal()" class="text-gray-400 hover:text-white text-2xl">&times;</button>
                </div>
                <div id="modalContent"></div>
            </div>
        </div>
    </div>
    
    <script>
        const TOKEN = new URLSearchParams(window.location.search).get('token') || '';
        let currentPage = 0;
        const LIMIT = 50;
        
        async function api(endpoint) {
            const res = await fetch(endpoint + (endpoint.includes('?') ? '&' : '?') + 'token=' + TOKEN);
            if (!res.ok) throw new Error('API Error');
            return res.json();
        }
        
        async function loadStats() {
            const stats = await api('/api/stats');
            document.getElementById('stats').innerHTML = Object.entries({
                '👥 Юзеров': stats.total_users,
                '💎 Активных': stats.active_subs,
                '🚫 Бан': stats.banned,
                '📋 Трекинг': stats.total_tracking,
                '💰 Доход': '$' + stats.total_revenue,
                '📤 Выводы': '$' + stats.total_withdrawn
            }).map(([k, v]) => '<div class="bg-gray-800 rounded-lg p-4"><div class="text-gray-400 text-sm">' + k + '</div><div class="text-2xl font-bold">' + v + '</div></div>').join('');
        }
        
        async function loadUsers() {
            const search = document.getElementById('search').value;
            const tier = document.getElementById('tierFilter').value;
            const data = await api('/api/users?offset=' + (currentPage * LIMIT) + '&limit=' + LIMIT + 
                                    '&search=' + encodeURIComponent(search) + '&tier=' + tier);
            
            document.getElementById('usersTable').innerHTML = data.users.map(u => 
                '<tr class="border-t border-gray-700 hover:bg-gray-750 cursor-pointer" onclick="showUser(' + u.user_id + ')">' +
                '<td class="px-4 py-3">' + u.user_id + '</td>' +
                '<td class="px-4 py-3">@' + (u.username || '-') + '</td>' +
                '<td class="px-4 py-3"><span class="px-2 py-1 rounded text-sm ' + 
                    (u.tier === 'pro' ? 'bg-purple-600' : u.tier === 'base' ? 'bg-blue-600' : u.tier === 'trial' ? 'bg-yellow-600' : 'bg-gray-600') + '">' + 
                    (u.tier || '-') + '</span></td>' +
                '<td class="px-4 py-3">' + (u.subscription_until ? u.subscription_until.split('T')[0] : '-') + '</td>' +
                '<td class="px-4 py-3">' + (u.balance_ton?.toFixed(2) || 0) + ' TON / ' + (u.balance_usdt?.toFixed(2) || 0) + ' USDT</td>' +
                '<td class="px-4 py-3">' + u.tracking_count + '</td>' +
                '<td class="px-4 py-3">' + (u.banned ? '🚫' : '✅') + '</td>' +
                '<td class="px-4 py-3">' + (u.created_at || '-').split('T')[0] + '</td>' +
                '</tr>'
            ).join('');
            
            // Pagination
            const totalPages = Math.ceil(data.total / LIMIT);
            document.getElementById('pagination').innerHTML = Array.from({length: Math.min(totalPages, 10)}, (_, i) => 
                '<button onclick="goPage(' + i + ')" class="px-3 py-1 rounded ' + (i === currentPage ? 'bg-blue-600' : 'bg-gray-700') + '">' + (i + 1) + '</button>'
            ).join('');
        }
        
        function goPage(page) { currentPage = page; loadUsers(); }
        
        async function showUser(userId) {
            const u = await api('/api/user/' + userId);
            
            // Кто пригласил
            var refBy = '-';
            if (u.referred_by) {
                refBy = '<a href="#" onclick="showUser(' + u.referred_by + '); return false;" class="text-blue-400 hover:underline">ID:' + u.referred_by + '</a>';
            }
            
            // Трекинг — кликабельные ссылки на Twitter
            var trackHtml = u.tracking.map(function(t) {
                return '<a href="https://x.com/' + t.twitter_username + '" target="_blank" class="text-blue-400 hover:underline">@' + t.twitter_username + '</a>';
            }).join(', ') || '-';
            
            // Рефералы — кликабельные
            var refsHtml = u.referrals.map(function(r) {
                var name = r.username ? '@' + r.username : 'ID:' + r.user_id;
                return '<a href="#" onclick="showUser(' + r.user_id + '); return false;" class="text-blue-400 hover:underline block py-1">' + name + '</a>';
            }).join('') || '-';
            
            // Платежи
            var paysHtml = u.payments.map(function(p) {
                var d = p.created_at ? p.created_at.split('T')[0] : '-';
                var st = p.status === 'paid' ? '✅' : p.status === 'expired' ? '❌' : '⏳';
                return '<div class="py-1 text-sm">' + st + ' ' + d + ' — ' + p.amount + ' ' + p.currency + '</div>';
            }).join('') || '-';
            
            // Выводы
            var wdsHtml = u.withdrawals.map(function(w) {
                var d = w.created_at ? w.created_at.split('T')[0] : '-';
                var st = w.status === 'completed' ? '✅' : w.status === 'pending' ? '⏳' : '📤';
                return '<div class="py-1 text-sm">' + st + ' ' + d + ' — ' + w.amount + ' ' + w.currency + '</div>';
            }).join('') || '-';
            
            // Комиссии
            var comHtml = u.commissions.map(function(c) {
                var d = c.created_at ? c.created_at.split('T')[0] : '-';
                return '<div class="py-1 text-sm">💰 ' + d + ' — +' + c.commission + ' ' + c.payment_currency + ' (от ID:' + c.referred_id + ')</div>';
            }).join('') || '-';
            
            document.getElementById('modalContent').innerHTML = 
                '<div class="grid md:grid-cols-2 gap-6">' +
                
                '<div class="bg-gray-700 rounded-lg p-4">' +
                '<h3 class="font-bold mb-3 text-lg">👤 Основное</h3>' +
                '<p class="py-1">🆔 ID: <code class="bg-gray-600 px-2 rounded">' + u.user_id + '</code></p>' +
                '<p class="py-1">📛 Username: <b>' + (u.username ? '@' + u.username : '-') + '</b></p>' +
                '<p class="py-1">📊 Тариф: <b>' + (u.tier || '-') + '</b></p>' +
                '<p class="py-1">⏰ До: ' + (u.subscription_until || '-') + '</p>' +
                '<p class="py-1">💎 TON: <b>' + (u.balance_ton || 0) + '</b></p>' +
                '<p class="py-1">💵 USDT: <b>' + (u.balance_usdt || 0) + '</b></p>' +
                '<p class="py-1">🚫 Бан: ' + (u.banned ? '<span class="text-red-400">ДА</span>' : '<span class="text-green-400">Нет</span>') + '</p>' +
                '<p class="py-1">👥 Пригласил: ' + refBy + '</p>' +
                '<p class="py-1">📅 Регистрация: ' + (u.created_at || '-') + '</p>' +
                '</div>' +
                
                '<div class="bg-gray-700 rounded-lg p-4">' +
                '<h3 class="font-bold mb-3 text-lg">📋 Трекинг (' + u.tracking.length + ')</h3>' +
                '<div class="flex flex-wrap gap-2">' + trackHtml + '</div>' +
                '</div>' +
                
                '<div class="bg-gray-700 rounded-lg p-4">' +
                '<h3 class="font-bold mb-3 text-lg">💳 Платежи (' + u.payments.length + ')</h3>' +
                paysHtml + '</div>' +
                
                '<div class="bg-gray-700 rounded-lg p-4">' +
                '<h3 class="font-bold mb-3 text-lg">📤 Выводы (' + u.withdrawals.length + ')</h3>' +
                wdsHtml + '</div>' +
                
                '<div class="bg-gray-700 rounded-lg p-4">' +
                '<h3 class="font-bold mb-3 text-lg">👥 Рефералы (' + u.referrals.length + ')</h3>' +
                refsHtml + '</div>' +
                
                '<div class="bg-gray-700 rounded-lg p-4">' +
                '<h3 class="font-bold mb-3 text-lg">💰 Комиссии (' + u.commissions.length + ')</h3>' +
                comHtml + '</div>' +
                
                '</div>';
            document.getElementById('modal').classList.remove('hidden');
        }
        
        function closeModal() { document.getElementById('modal').classList.add('hidden'); }
        document.getElementById('modal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });
        
        // Init
        loadStats();
        loadUsers();
        document.getElementById('search').addEventListener('keypress', e => { if (e.key === 'Enter') loadUsers(); });
    </script>
</body>
</html>
'''

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    check_auth(request)
    return ADMIN_HTML


@app.get("/")
async def root():
    return {"message": "Admin API. Go to /admin?token=YOUR_TOKEN"}


if __name__ == "__main__":
    print(f"Starting admin panel on port {PORT}...")
    print(f"Access: http://localhost:{PORT}/admin?token={ADMIN_TOKEN}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)


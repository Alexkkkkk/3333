import asyncpg
import os
import json
import asyncio
import random
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# --- ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ---
app = FastAPI(title="Quantum Singularity Engine")

# CORS для стабильной работы твоего дизайна Quantum Protocol
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный пул соединений
_pool = None

# --- МЕНЕДЖЕР REAL-TIME СОЕДИНЕНИЙ ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Рассылка данных всем подключенным клиентам (фронтенду)."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

# --- РАБОТА С БАЗОЙ ДАННЫХ (HIGH-LOAD) ---
async def get_pool():
    global _pool
    db_url = os.getenv('DATABASE_URL')
    if _pool is None:
        if not db_url:
            raise ValueError("🚨 DATABASE_URL is not set!")
        # Лимиты оптимизированы под Pro-тариф Bothost
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=10, 
            max_size=30,
            command_timeout=60,
            max_queries=100000,
            max_inactive_connection_lifetime=300.0
        )
    return _pool

async def init_db():
    """Полная инициализация всех 6 таблиц Квантовой Архитектуры."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        queries = [
            # 1. Геном (Конфигурации)
            '''CREATE TABLE IF NOT EXISTS quantum_genome (key TEXT PRIMARY KEY, val JSONB, is_shadow BOOLEAN DEFAULT FALSE, fitness_score FLOAT DEFAULT 0.0, updated_at TIMESTAMP DEFAULT NOW())''',
            # 2. Кошельки (Узлы системы)
            '''CREATE TABLE IF NOT EXISTS quantum_wallets (address TEXT PRIMARY KEY, balance_ton DOUBLE PRECISION DEFAULT 0.0, equity_qc DOUBLE PRECISION DEFAULT 0.0, network TEXT DEFAULT 'MAINNET', status TEXT DEFAULT 'ACTIVE', last_seen TIMESTAMP DEFAULT NOW())''',
            # 3. Нейро-логи (Опыт AI)
            '''CREATE TABLE IF NOT EXISTS neural_mm_logs (id SERIAL PRIMARY KEY, cmd TEXT NOT NULL, amount DOUBLE PRECISION DEFAULT 0.0, urgency INT DEFAULT 1, reason TEXT, market_snapshot JSONB, reward_score DOUBLE PRECISION DEFAULT 0.0, timestamp TIMESTAMP DEFAULT NOW())''',
            # 4. Визиты (Аналитика трафика)
            '''CREATE TABLE IF NOT EXISTS site_visits (id SERIAL PRIMARY KEY, ip_hash TEXT, user_agent TEXT, timestamp TIMESTAMP DEFAULT NOW())''',
            # 5. Распределение прибыли
            '''CREATE TABLE IF NOT EXISTS profit_distribution (id SERIAL PRIMARY KEY, total_amount DOUBLE PRECISION NOT NULL, holders_share DOUBLE PRECISION, staking_share DOUBLE PRECISION, liquidity_share DOUBLE PRECISION, treasury_share DOUBLE PRECISION, timestamp TIMESTAMP DEFAULT NOW())''',
            # 6. Вывод средств
            '''CREATE TABLE IF NOT EXISTS withdrawal_requests (id SERIAL PRIMARY KEY, address TEXT NOT NULL, amount_ton DOUBLE PRECISION NOT NULL, status TEXT DEFAULT 'PENDING', tx_hash TEXT, created_at TIMESTAMP DEFAULT NOW(), processed_at TIMESTAMP)'''
        ]
        for q in queries:
            await conn.execute(q)
        
        # Индексы для ускорения аналитики
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_neural_ts ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_wallets_qc ON quantum_wallets(equity_qc DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_profit_ts ON profit_distribution(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_withdraw_status ON withdrawal_requests(status)')
        
        # Дефолтные настройки ядра
        default_val = {"ai_strategy_level": 10, "yield_percentage": 75.0, "referral_commission": 15.0, "gas_limit_min": 0.2}
        await conn.execute("INSERT INTO quantum_genome (key, val) VALUES ('active_core', $1) ON CONFLICT DO NOTHING", json.dumps(default_val))
        
    print("🌌 [DATABASE] Nexus Singularity Core Synchronized.")

# --- УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ ---

async def load_remote_config():
    pool = await get_pool()
    val = await pool.fetchval("SELECT val FROM quantum_genome WHERE key = 'active_core'")
    if val:
        return json.loads(val) if isinstance(val, str) else val
    return {}

async def update_remote_config(data: dict):
    pool = await get_pool()
    current = await load_remote_config()
    current.update(data)
    await pool.execute('''
        INSERT INTO quantum_genome (key, val) 
        VALUES ('active_core', $1) 
        ON CONFLICT (key) DO UPDATE SET val = $1, updated_at = NOW()
    ''', json.dumps(current))
    return True

# --- УЧЕТ ПОСЕТИТЕЛЕЙ И КОШЕЛЬКОВ ---

async def register_visit(ip: str, user_agent: str):
    pool = await get_pool()
    await pool.execute('INSERT INTO site_visits (ip_hash, user_agent) VALUES (MD5($1), $2)', ip, user_agent)

async def save_wallet_state(address: str, balance: float, qc: float, network: str = 'MAINNET'):
    pool = await get_pool()
    await pool.execute('''
        INSERT INTO quantum_wallets (address, balance_ton, equity_qc, network, last_seen)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (address) DO UPDATE SET balance_ton = EXCLUDED.balance_ton, equity_qc = EXCLUDED.equity_qc, last_seen = NOW(), status = 'ACTIVE'
    ''', address, float(balance), float(qc), network)

async def get_user_balance(address: str):
    pool = await get_pool()
    res = await pool.fetchval('SELECT balance_ton FROM quantum_wallets WHERE address = $1', address)
    return float(res) if res else 0.0

# --- СИСТЕМА ВЫВОДА ---

async def create_withdrawal_request(address: str, amount: float):
    pool = await get_pool()
    active = await pool.fetchval("SELECT id FROM withdrawal_requests WHERE address = $1 AND status = 'PENDING'", address)
    if active:
        return False, "Активная заявка уже существует"
    
    await pool.execute('INSERT INTO withdrawal_requests (address, amount_ton) VALUES ($1, $2)', address, float(amount))
    return True, "Заявка создана"

# --- АНАЛИТИКА И СТАТИСТИКА (FIXED) ---

async def calculate_roi_stats():
    pool = await get_pool()
    total = await pool.fetchval('SELECT SUM(equity_qc) FROM quantum_wallets') or 1.0
    p24 = await pool.fetchval("SELECT SUM(total_amount) FROM profit_distribution WHERE timestamp > NOW() - INTERVAL '24 hours'") or 0.0
    return round((float(p24) / float(total)) * 100, 2)

async def get_stats_for_web():
    """Сбор статистики с использованием пула для предотвращения InterfaceError."""
    pool = await get_pool()
    try:
        # Используем pool напрямую вместо захвата одного коннекта для параллелизма
        online_t = pool.fetchval("SELECT COUNT(DISTINCT ip_hash) FROM site_visits WHERE timestamp > NOW() - INTERVAL '30 minutes'")
        total_qc_t = pool.fetchval("SELECT SUM(equity_qc) FROM quantum_wallets")
        total_w_t = pool.fetchval("SELECT COUNT(*) FROM quantum_wallets")
        rows_t = pool.fetch("SELECT address, balance_ton as amount, equity_qc as qc, status FROM quantum_wallets ORDER BY last_seen DESC LIMIT 10")
        
        # asyncio.gather теперь безопасно берет разные соединения из пула
        online, total_qc, total_w, rows = await asyncio.gather(online_t, total_qc_t, total_w_t, rows_t)
        roi = await calculate_roi_stats()

        return {
            "connections": int(total_w or 0),
            "qc_balance": round(float(total_qc or 0), 2),
            "traffic": int((online or 1) * 8), # Визуальный множитель
            "roi_24h": roi,
            "recent_actions": [dict(r) for r in rows],
            "system": {"cpu": random.randint(18, 35), "ram": f"{random.randint(150, 175)}MB"}
        }
    except Exception as e:
        print(f"🚨 [STATS ERROR] {e}")
        return {"error": "Stats temporary unavailable"}

# --- КВАНТОВЫЙ ОРКЕСТРАТОР (ФОНОВЫЕ ЗАДАЧИ) ---
class QuantumOrchestrator:
    @staticmethod
    async def start():
        asyncio.create_task(QuantumOrchestrator.pulse())
        asyncio.create_task(QuantumOrchestrator.cleanup())

    @staticmethod
    async def pulse():
        while True:
            try:
                stats = await get_stats_for_web()
                await manager.broadcast({"event": "CORE_PULSE", "data": stats})
            except: pass
            await asyncio.sleep(3)

    @staticmethod
    async def cleanup():
        while True:
            await asyncio.sleep(43200) # Раз в 12 часов
            pool = await get_pool()
            await pool.execute("DELETE FROM site_visits WHERE timestamp < NOW() - INTERVAL '24 hours'")
            await pool.execute("DELETE FROM neural_mm_logs WHERE timestamp < NOW() - INTERVAL '7 days'")

# --- API ЭНДПОИНТЫ ---

@app.websocket("/ws/stats")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        data = await get_stats_for_web()
        await websocket.send_json({"event": "INITIAL_SYNC", "data": data})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    await init_db()
    await QuantumOrchestrator.start()

# Методы для внешней интеграции
async def sync_wallet_data(data: dict):
    address = data.get('address')
    if address:
        await save_wallet_state(address, data.get('balance', 0.0), data.get('qc', 0.0))
        return True
    return False

async def log_ai_action(strategy, market, success_metric=0.0):
    pool = await get_pool()
    await pool.execute('''
        INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot, reward_score) 
        VALUES ($1, $2, $3, $4, $5, $6)
    ''', strategy.get('cmd'), float(strategy.get('amount', 0)), 
         int(strategy.get('urgency', 1)), strategy.get('reason'), 
         json.dumps(market), float(success_metric))

import asyncio
import os
import json
import time
import sys
import random
import hashlib
import traceback
from datetime import datetime
from typing import List
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, Response, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Загружаем переменные окружения
load_dotenv()

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TONAPI_KEY = os.getenv("TONAPI_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 3000))

# Проверка psutil для системных данных
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Импорт функций БД
try:
    from database import (
        init_db, get_stats_for_web, register_visit, 
        save_wallet_state, log_ai_action, update_remote_config, 
        load_remote_config
    )
except ImportError:
    print("\033[91m[ERROR] Файл database.py не найден!\033[0m")
    sys.exit(1)

# --- ЛОГИРОВАНИЕ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARNING": "\033[93m", "ERROR": "\033[91m", "CORE": "\033[95m"}
    reset = "\033[0m"
    print(f"{colors.get(level, reset)}[{timestamp}] [{level}] {message}{reset}", flush=True)

# --- TON CORE ---
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V4.1 REAL-TIME <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    TON_ENABLED = True
except ImportError:
    log("pytoniq не найден!", "ERROR")
    TON_ENABLED = False

# --- МЕНЕДЖЕР WEB-SOCKET СОЕДИНЕНИЙ ---
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
        """Отправка данных всем подключенным пользователям"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Если соединение битое, оно удалится при disconnect
                pass

manager = ConnectionManager()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"QC-CORE-{os.urandom(2).hex().upper()}"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0
        self.processed_txs = set()
        self.pending_withdrawals = []

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "static")

overlord = OmniNeuralOverlord()
static_dir = overlord.get_static_path()

async def sync_config():
    try:
        cfg = await load_remote_config()
        if cfg and cfg.get('mnemonic'):
            overlord.mnemonic = cfg['mnemonic'].strip()
            return True
    except Exception as e:
        log(f"Sync Config Fail: {e}", "ERROR")
    return False

# --- ЛОГИКА ПУЛА ---
async def process_pool_inflow(wallet):
    if not TON_ENABLED: return
    try:
        txs = await wallet.client.get_transactions(wallet.address, limit=5)
        for tx in txs:
            tx_hash = tx.hash.hex()
            if tx_hash in overlord.processed_txs: continue
            if tx.in_msg and tx.in_msg.value > 0:
                amount = tx.in_msg.value / 1e9
                sender = tx.in_msg.source.to_str() if tx.in_msg.source else "UNKNOWN"
                log(f"POOL: Депозит {amount} TON", "SUCCESS")
                await log_ai_action({'cmd': 'DEPOSIT', 'amount': amount}, {'status': 'active'})
                # Уведомляем фронтенд о новом депозите
                await manager.broadcast({"type": "EVENT", "event": "deposit", "amount": amount})
            overlord.processed_txs.add(tx_hash)
    except Exception as e:
        log(f"Pool Sync Error: {e}", "CORE")

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("SYS: Nexus DB Connect...", "INFO")
    await init_db()
    await sync_config()
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()
    log("SYS: Ядро остановлено", "CORE")

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- API ROUTES ---

@app.get("/")
@app.get("/index.html")
async def read_index(request: Request):
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/api/stats")
async def get_stats():
    db_stats = await get_stats_for_web() or {}
    cpu = psutil.cpu_percent() if PSUTIL_AVAILABLE else random.randint(1, 10)
    return {
        "balance": round(overlord.current_balance, 2),
        "qc_balance": round(overlord.current_balance * 137.5, 2),
        "cpu_load": cpu,
        "engine": {"core_id": overlord.core_id, "status": overlord.last_status}
    }

# --- WEBSOCKET ENDPOINT ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # При входе отправляем текущее состояние
        await websocket.send_json({
            "type": "INIT",
            "balance": round(overlord.current_balance, 2),
            "qc_balance": round(overlord.current_balance * 137.5, 2),
            "status": overlord.last_status
        })
        while True:
            await websocket.receive_text() # Поддерживаем соединение
    except WebSocketDisconnect:
        manager.disconnect(websocket)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{path:path}")
async def catch_all(path: str):
    file_path = os.path.join(static_dir, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(static_dir, "index.html"))

# --- CORE WORKER ---
async def core_worker():
    log("CORE: Воркер запущен", "INFO")
    while overlord.is_active:
        try:
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "STANDBY"
                await asyncio.sleep(10)
                await sync_config()
                continue

            async with LiteClient.from_mainnet_config() as client:
                wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                overlord.last_status = "ACTIVE"
                
                while overlord.is_active:
                    # 1. Синхронизация баланса
                    raw_balance = await wallet.get_balance()
                    new_balance = raw_balance / 1e9
                    
                    # 2. Если баланс изменился — рассылаем всем мгновенно
                    if new_balance != overlord.current_balance:
                        overlord.current_balance = new_balance
                        await manager.broadcast({
                            "type": "UPDATE",
                            "balance": round(overlord.current_balance, 2),
                            "qc_balance": round(overlord.current_balance * 137.5, 2),
                            "status": overlord.last_status
                        })

                    # 3. Депозиты и выплата
                    await process_pool_inflow(wallet)
                    
                    if overlord.pending_withdrawals:
                        task = overlord.pending_withdrawals.pop(0)
                        log(f"CORE: Выплата {task['amount']} TON", "CORE")
                        # Логика транзакции здесь
                    
                    await save_wallet_state(str(wallet.address), overlord.current_balance, overlord.current_balance*137.5)
                    
                    await asyncio.sleep(10) # Проверка каждые 10 сек для высокой точности
                    if not await sync_config(): break 

        except Exception as e:
            log(f"Worker Loop Error: {e}", "ERROR")
            await asyncio.sleep(5)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")

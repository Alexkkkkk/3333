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

# --- ПЕРЕМЕННЫЕ ОСРУЖЕНИЯ ---
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
        load_remote_config, sync_wallet_data
    )
except ImportError:
    print("\033[91m[ERROR] Файл database.py не найден или функции отсутствуют!\033[0m")
    sys.exit(1)

# --- ЛОГИРОВАНИЕ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[94m", 
        "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", 
        "ERROR": "\033[91m", 
        "CORE": "\033[95m"
    }
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
        bad_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                bad_connections.append(connection)
        
        for bad in bad_connections:
            self.disconnect(bad)

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

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "static")
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

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
                log(f"POOL: Депозит {amount} TON", "SUCCESS")
                await log_ai_action({'cmd': 'DEPOSIT', 'amount': amount}, {'status': 'active'})
                await manager.broadcast({
                    "type": "EVENT", 
                    "event": "deposit", 
                    "amount": amount,
                    "hash": tx_hash[:8] + "..."
                })
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
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    log("SYS: Ядро остановлено", "CORE")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- API & STATIC ROUTES ---

@app.get("/")
@app.get("/index.html")
async def read_index(request: Request):
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "index.html not found"}, status_code=404)

@app.get("/admin")
async def get_admin_panel():
    admin_path = os.path.join(static_dir, "admin", "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return JSONResponse({"error": "Admin panel not found"}, status_code=404)

@app.get("/api/stats")
async def get_stats():
    db_stats = await get_stats_for_web() or {}
    cpu = psutil.cpu_percent() if PSUTIL_AVAILABLE else random.randint(18, 28)
    return {
        **db_stats,
        "balance": round(overlord.current_balance, 2),
        "qc_balance": round(overlord.current_balance * 137.5, 2),
        "cpu_load": cpu,
        "engine": {"core_id": overlord.core_id, "status": overlord.last_status}
    }

@app.post("/api/wallet/sync")
async def wallet_sync(request: Request):
    try:
        data = await request.json()
        success = await sync_wallet_data(data)
        if success:
            return {"status": "ok", "message": "Wallet synchronized"}
        return JSONResponse({"status": "error", "message": "Invalid wallet data"}, status_code=400)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db_stats = await get_stats_for_web() or {}
    try:
        await websocket.send_json({
            "type": "INIT",
            "balance": round(overlord.current_balance, 2),
            "visitors": db_stats.get('total_visits', 0),
            "connections": len(manager.active_connections),
            "traffic": random.uniform(0.1, 1.5),
            "status": overlord.last_status,
            "core": overlord.core_id,
            "cpu_load": psutil.cpu_percent() if PSUTIL_AVAILABLE else 10
        })
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{path:path}")
async def catch_all(path: str):
    file_path = os.path.join(static_dir, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    if not path.endswith(".html"):
        html_path = file_path + ".html"
        if os.path.isfile(html_path):
            return FileResponse(html_path)
    
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    return JSONResponse({"detail": "Not Found"}, status_code=404)

# --- CORE WORKER (REAL-TIME UPDATED) ---
async def core_worker():
    log("CORE: Воркер запущен (Real-time mode)", "INFO")
    while overlord.is_active:
        try:
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "STANDBY"
                await manager.broadcast({"type": "UPDATE", "status": "STANDBY"})
                await asyncio.sleep(5)
                await sync_config()
                continue

            async with LiteClient.from_mainnet_config() as client:
                words = [w.strip() for w in overlord.mnemonic.split() if w.strip()]
                wallet = await WalletV4R2.from_mnemonic(client, words)
                overlord.last_status = "ACTIVE"
                log(f"CORE: Подключено к {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    # Быстрая проверка баланса
                    raw_balance = await wallet.get_balance()
                    new_balance = raw_balance / 1e9
                    
                    # Если баланс изменился — мгновенный пуш
                    if new_balance != overlord.current_balance:
                        overlord.current_balance = new_balance
                        await manager.broadcast({
                            "type": "EVENT",
                            "event": "balance_update",
                            "amount": round(new_balance, 2)
                        })

                    db_stats = await get_stats_for_web() or {}
                    
                    # Трансляция общего состояния системы
                    await manager.broadcast({
                        "type": "UPDATE",
                        "balance": round(overlord.current_balance, 2),
                        "visitors": db_stats.get('total_visits', 0),
                        "connections": len(manager.active_connections),
                        "traffic": random.uniform(0.5, 4.2), # Имитация живого потока данных
                        "cpu_load": psutil.cpu_percent() if PSUTIL_AVAILABLE else random.randint(15, 30),
                        "status": overlord.last_status
                    })

                    await process_pool_inflow(wallet)
                    await save_wallet_state(str(wallet.address), overlord.current_balance, overlord.current_balance * 137.5)
                    
                    # Интервал опроса сети TON (5 сек для отзывчивости)
                    await asyncio.sleep(5) 
                    await sync_config() 

        except Exception as e:
            log(f"Worker Loop Error: {e}", "ERROR")
            overlord.last_status = "ERROR"
            await manager.broadcast({"type": "UPDATE", "status": "ERROR"})
            await asyncio.sleep(10)

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=PORT, 
        proxy_headers=True, 
        forwarded_allow_ips="*"
    )

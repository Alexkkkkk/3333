import asyncio
import os
import json
import time
import sys
import random
from urllib.parse import parse_qs
from datetime import datetime
from typing import List
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Загружаем переменные окружения
load_dotenv()

"""
🧬 QUANTUM CORE 4.5.0 | FULL NATURAL MONITORING
STRUCTURE:
/ (root)
├── main.py
├── database.py
└── static/
"""

# --- ИМПОРТ ФУНКЦИЙ БД ---
try:
    from database import (
        init_db, get_stats_for_web, register_visit, 
        save_wallet_state, log_ai_action, load_remote_config,
        manager, get_pool, close_pool, QuantumOrchestrator
    )
except ImportError:
    print("\033[91m[ERROR] Critical Failure: database.py missing or contains errors!\033[0m")
    sys.exit(1)

# --- КОНФИГУРАЦИЯ ---
PORT = int(os.getenv("PORT", 3000))
TON_ENABLED = False

# Проверка psutil для РЕАЛЬНОЙ телеметрии
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Импорт TON библиотек
try:
    from pytoniq import LiteClient, WalletV4R2
    TON_ENABLED = True
except ImportError:
    TON_ENABLED = False
    print("\033[93m[WARNING] TON libs not found. Network monitoring limited.\033[0m")

# --- ЛОГИРОВАНИЕ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARNING": "\033[93m", "ERROR": "\033[91m", "CORE": "\033[95m"}
    print(f"{colors.get(level, '')}[{timestamp}] [{level}] {message}\033[0m", flush=True)

# --- ЯДРО НАТУРАЛЬНОЙ ТЕЛЕМЕТРИИ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.boot_time = time.time()
        self.core_id = "QN-NATURAL-ULTRA-4.5.0"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0
        
        if PSUTIL_AVAILABLE:
            self.net_old = psutil.net_io_counters()
            self.disk_old = psutil.disk_io_counters()
            self.last_check_time = time.time()

    def get_uptime(self):
        return int(time.time() - self.boot_time)

    def get_real_metrics(self):
        if not PSUTIL_AVAILABLE:
            return {"error": "psutil_unavailable"}
        
        now = time.time()
        diff = max(now - self.last_check_time, 0.1)
        self.last_check_time = now

        # Расчет скорости сети (KB/s)
        net_now = psutil.net_io_counters()
        download_speed = (net_now.bytes_recv - self.net_old.bytes_recv) / diff / 1024
        upload_speed = (net_now.bytes_sent - self.net_old.bytes_sent) / diff / 1024
        self.net_old = net_now

        # Память системы
        mem = psutil.virtual_memory()
        
        # Дисковая активность
        disk_now = psutil.disk_io_counters()
        read_kb = (disk_now.read_bytes - self.disk_old.read_bytes) / diff / 1024
        self.disk_old = disk_now

        # Данные процесса
        proc = psutil.Process()

        return {
            "cpu": {
                "percent": psutil.cpu_percent(interval=None),
                "freq": round(psutil.cpu_freq().current if psutil.cpu_freq() else 0, 2),
                "threads": proc.num_threads()
            },
            "ram": {
                "percent": mem.percent,
                "used_gb": round(mem.used / (1024**3), 2),
                "total_gb": round(mem.total / (1024**3), 2)
            },
            "network": {
                "down_kbs": round(download_speed, 2),
                "up_kbs": round(upload_speed, 2)
            },
            "disk": {
                "usage_percent": psutil.disk_usage('/').percent,
                "read_kbs": round(read_kb, 2)
            },
            "app_memory_mb": round(proc.memory_info().rss / (1024*1024), 2)
        }

overlord = OmniNeuralOverlord()

# --- ФОНОВЫЙ ВОРКЕР (SUPER MONITORING) ---
async def core_worker():
    log("CORE: Система супер-мониторинга активирована", "SUCCESS")
    while overlord.is_active:
        try:
            # 1. Загрузка конфигурации
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()

            # 2. Сбор метрик
            db_stats = await get_stats_for_web()
            sys_metrics = overlord.get_real_metrics()
            
            # Проверка БД пула
            pool = get_pool()
            db_alive = pool is not None and not pool._closed

            # 3. TON Телеметрия
            ton_metrics = {"status": "OFFLINE", "block": 0}
            if overlord.mnemonic and TON_ENABLED:
                try:
                    async with LiteClient.from_mainnet_config() as client:
                        master_info = await client.get_masterchain_info()
                        wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                        
                        raw_bal = await wallet.get_balance()
                        new_balance = raw_bal / 1e9
                        
                        if new_balance > overlord.current_balance and overlord.current_balance > 0:
                            diff = round(new_balance - overlord.current_balance, 2)
                            await log_ai_action("DEPOSIT", diff, f"Received {diff} TON")
                        
                        overlord.current_balance = new_balance
                        overlord.last_status = "ACTIVE"
                        ton_metrics = {
                            "status": "ONLINE",
                            "block": master_info['last']['seqno'],
                            "wallet_preview": str(wallet.address)[:10] + "..."
                        }
                except Exception as ton_e:
                    log(f"TON Sync Error: {ton_e}", "WARNING")
                    overlord.last_status = "SYNC_LAG"
            else:
                overlord.last_status = "STANDBY"

            # 4. ВЕЩАНИЕ (WebSocket)
            await manager.broadcast({
                "type": "UPDATE",
                "data": {
                    "balance": round(overlord.current_balance, 2),
                    "traffic": db_stats.get('traffic', 0),
                    "connections": db_stats.get('connections', 0),
                    "qc_balance": db_stats.get('qc_balance', 0),
                    "system": sys_metrics,
                    "db_online": db_alive,
                    "ton": ton_metrics,
                    "ws_clients": len(manager.active_connections),
                    "status": overlord.last_status,
                    "uptime": overlord.get_uptime(),
                    "recent_actions": db_stats.get('recent_actions', []),
                    "ts": int(time.time() * 1000)
                }
            })

            await asyncio.sleep(2) # Натуральное обновление каждые 2 секунды

        except Exception as e:
            log(f"Critical Monitoring Error: {e}", "ERROR")
            await asyncio.sleep(10)

# --- LIFESPAN (Жизненный цикл приложения) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(">>> 🌌 QUANTUM HYBRID CORE STARTING <<<", "CORE")
    await init_db()
    QuantumOrchestrator.start_background_tasks()
    worker_task = asyncio.create_task(core_worker())
    yield
    log("🔌 Shutdown sequence initiated...", "WARNING")
    overlord.is_active = False
    worker_task.cancel()
    await close_pool()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- РОУТИНГ ---

@app.post("/api/track-visit")
async def api_register_visit(data: dict = Body(...), request: Request = None):
    init_data_raw = data.get("initData")
    try:
        parsed = parse_qs(init_data_raw)
        user_info = json.loads(parsed.get("user", ["{}"])[0])
    except:
        user_info = {"id": "Unknown", "username": "Guest"}

    await register_visit(
        request.client.host if request else "0.0.0.0", 
        f"TG:{user_info.get('id')} | {data.get('platform', 'unknown')}"
    )
    return {"status": "ok", "monitored": True}

@app.get("/")
@app.get("/index.html")
async def read_root(request: Request):
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    return FileResponse("static/index.html")

@app.get("/admin")
@app.get("/admin/admin.html")
async def get_admin_root():
    return FileResponse("static/admin/admin.html")

@app.get("/admin/{file_path:path}")
async def get_admin_pages(file_path: str):
    path = f"static/admin/{file_path}"
    if not path.endswith(".html") and not os.path.isdir(path):
        path += ".html"
    return FileResponse(path) if os.path.exists(path) else FileResponse("static/admin/admin.html")

# --- WEBSOCKET (REAL-TIME STREAM) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db_stats = await get_stats_for_web()
    try:
        # Первичный пакет (Handshake)
        await websocket.send_json({
            "type": "INIT",
            "data": {
                "balance": round(overlord.current_balance, 2),
                "traffic": db_stats.get('traffic', 0),
                "system": overlord.get_real_metrics(),
                "status": overlord.last_status,
                "uptime": overlord.get_uptime(),
                "core": overlord.core_id
            }
        })
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Подключение статики
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")

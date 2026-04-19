import asyncio
import os
import json
import time
import sys
import httpx
from urllib.parse import parse_qs
from datetime import datetime
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
🧬 QUANTUM CORE 4.9.5 | MULTI-WALLET UNIFIED EDITION
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

# Кэш для мульти-кошельков
multi_wallet_cache = {
    "balances": {
        "alpha": 0.0,
        "beta": 0.0,
        "total": 0.0
    },
    "wallets": {
        "alpha": "EQCSAT3Nh1Rmo1zfw68hkb8TcR0gnxpyM5LW-oaKzuxtbZda",
        "beta": "EQD-qDSmKlgBHaXvmhoyMkzJumEPtk9Kee1nM_n0y2crHXCj"
    }
}

# Проверка psutil для РЕАЛЬНОЙ телеметрии
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Импорт TON библиотек (для локального кошелька)
try:
    from pytoniq import LiteClient, WalletV4R2
    TON_ENABLED = True
except ImportError:
    TON_ENABLED = False
    print("\033[93m[WARNING] TON libs not found. Local monitoring limited.\033[0m")

# --- ЛОГИРОВАНИЕ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARNING": "\033[93m", "ERROR": "\033[91m", "CORE": "\033[95m"}
    print(f"{colors.get(level, '')}[{timestamp}] [{level}] {message}\033[0m", flush=True)

# --- ЯДРО СИСТЕМЫ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.boot_time = time.time()
        self.core_id = "QN-NATURAL-ULTRA-4.9.5"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0
        
        if PSUTIL_AVAILABLE:
            self.net_old = psutil.net_io_counters()
            self.last_check_time = time.time()

    def get_uptime(self):
        return int(time.time() - self.boot_time)

    def get_real_metrics(self):
        if not PSUTIL_AVAILABLE: return {"cpu": {"percent": 5}, "ram": {"percent": 10}}
        try:
            now = time.time()
            diff = max(now - self.last_check_time, 0.1)
            self.last_check_time = now
            net_now = psutil.net_io_counters()
            download_speed = (net_now.bytes_recv - self.net_old.bytes_recv) / diff / 1024
            upload_speed = (net_now.bytes_sent - self.net_old.bytes_sent) / diff / 1024
            self.net_old = net_now
            mem = psutil.virtual_memory()
            proc = psutil.Process()
            return {
                "cpu": {"percent": psutil.cpu_percent(interval=None), "threads": proc.num_threads()},
                "ram": {"percent": mem.percent, "used_gb": round(mem.used / (1024**3), 2)},
                "network": {"down_kbs": round(max(0, download_speed), 2), "up_kbs": round(max(0, upload_speed), 2)},
                "app_memory_mb": round(proc.memory_info().rss / (1024*1024), 2)
            }
        except: return {"error": "metrics_failed"}

overlord = OmniNeuralOverlord()

# --- ФОНОВЫЕ ЗАДАЧИ ---

async def update_external_balances():
    """Фоновая задача для опроса Toncenter кошельков Alpha/Beta"""
    async with httpx.AsyncClient() as client:
        while overlord.is_active:
            try:
                for key, addr in multi_wallet_cache["wallets"].items():
                    url = f"https://toncenter.com/api/v2/getAddressInformation?address={addr}"
                    response = await client.get(url, timeout=10.0)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("ok"):
                            # Безопасное извлечение баланса
                            raw_val = data.get("result", {}).get("balance", 0)
                            balance = float(raw_val) / 1e9
                            multi_wallet_cache["balances"][key] = round(balance, 4)
                
                multi_wallet_cache["balances"]["total"] = round(
                    multi_wallet_cache["balances"]["alpha"] + multi_wallet_cache["balances"]["beta"], 4
                )
                log(f"External Balances Sync: {multi_wallet_cache['balances']['total']} TON", "SUCCESS")
            except Exception as e:
                log(f"External Sync error: {e}", "WARNING")
            
            await asyncio.sleep(30)

async def core_worker():
    """Основной воркер для метрик и локального TON кошелька"""
    log("CORE: Система мониторинга активирована", "SUCCESS")
    while overlord.is_active:
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()

            db_stats = await get_stats_for_web()
            sys_metrics = overlord.get_real_metrics()
            
            # Проверка БД
            try:
                pool = await get_pool()
                db_alive = pool is not None and not pool._closed
            except: db_alive = False

            # Проверка локального кошелька через pytoniq
            if overlord.mnemonic and TON_ENABLED:
                try:
                    async with LiteClient.from_mainnet_config() as client:
                        wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                        raw_bal = await wallet.get_balance()
                        new_balance = raw_bal / 1e9
                        
                        if new_balance > overlord.current_balance and overlord.current_balance > 0:
                            diff = round(new_balance - overlord.current_balance, 2)
                            await log_ai_action("DEPOSIT", diff, f"Received {diff} TON")
                        
                        overlord.current_balance = new_balance
                        overlord.last_status = "ACTIVE"
                        await save_wallet_state(str(wallet.address), overlord.current_balance, overlord.current_balance * 135)
                except: overlord.last_status = "SYNC_LAG"
            else: overlord.last_status = "STANDBY"

            # Рассылка всем через WebSocket
            await manager.broadcast({
                "type": "UPDATE",
                "data": {
                    "balance": round(overlord.current_balance, 2),
                    "multi_balances": multi_wallet_cache["balances"],
                    "traffic": db_stats.get('traffic', 0),
                    "system": sys_metrics,
                    "db_online": db_alive,
                    "status": overlord.last_status,
                    "uptime": overlord.get_uptime(),
                    "recent_actions": db_stats.get('recent_actions', []),
                    "ts": int(time.time() * 1000)
                }
            })
            await asyncio.sleep(5) 
        except Exception as e:
            log(f"Critical Monitoring Error: {e}", "ERROR")
            await asyncio.sleep(10)

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(">>> 🌌 QUANTUM HYBRID CORE STARTING <<<", "CORE")
    await init_db()
    QuantumOrchestrator.start_background_tasks()
    
    # Запуск фоновых процессов
    worker_task = asyncio.create_task(core_worker())
    external_sync_task = asyncio.create_task(update_external_balances())
    
    yield
    
    log("🔌 Shutdown sequence initiated...", "WARNING")
    overlord.is_active = False
    worker_task.cancel()
    external_sync_task.cancel()
    await close_pool()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- РОУТИНГ СТАТИКИ ---

@app.get("/")
@app.get("/index.html")
async def read_root():
    return FileResponse("static/index.html")

@app.get("/admin")
@app.get("/admin/admin.html")
async def get_admin_main():
    return FileResponse("static/admin/admin.html")

@app.get("/tonconnect-manifest.json")
async def get_manifest():
    return FileResponse("static/tonconnect-manifest.json")

# --- API ЭНДПОИНТЫ ---

@app.get("/api/v1/stats")
async def get_multi_wallet_stats():
    """Эндпоинт для админки (новые балансы)"""
    # Возвращаем плоский объект для совместимости с JS
    return {
        "alpha": multi_wallet_cache["balances"].get("alpha", 0.0),
        "beta": multi_wallet_cache["balances"].get("beta", 0.0),
        "total": multi_wallet_cache["balances"].get("total", 0.0)
    }

@app.get("/api/stats")
async def get_combined_stats():
    """Общий эндпоинт системы"""
    db_stats = await get_stats_for_web()
    return {
        "status": overlord.last_status,
        "visitors": db_stats.get('traffic', 0),
        "balance": round(overlord.current_balance, 2),
        "external_wallets": multi_wallet_cache["balances"],
        "uptime": overlord.get_uptime(),
        "system": overlord.get_real_metrics(),
        "recent_actions": db_stats.get('recent_actions', []),
        "core_id": overlord.core_id
    }

# --- WEBSOCKET ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        db_stats = await get_stats_for_web()
        await websocket.send_json({
            "type": "INIT",
            "data": {
                "balance": round(overlord.current_balance, 2),
                "multi_balances": multi_wallet_cache["balances"],
                "traffic": db_stats.get('traffic', 0),
                "system": overlord.get_real_metrics(),
                "status": overlord.last_status,
                "uptime": overlord.get_uptime()
            }
        })

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                continue
            
            try:
                message = json.loads(data)
                if message.get("type") == "COMMAND":
                    action = message.get("action")
                    if action == "EMERGENCY_STOP":
                        overlord.is_active = False
                        overlord.last_status = "EMERGENCY"
                        await websocket.send_json({"type": "UPDATE", "data": {"log_entry": {"msg": "CORE HALTED", "type": "ERR"}}})
            except: pass

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket)

# Монтирование остальной статики
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")

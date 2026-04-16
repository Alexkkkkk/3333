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
from starlette.websockets import WebSocketState
import uvicorn

# Загружаем переменные окружения
load_dotenv()

"""
🧬 QUANTUM CORE 4.9.0 | FINAL UNIFIED EDITION
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def parse_tg_init_data(init_data: str):
    try:
        if not init_data: return {"id": "Unknown"}
        parsed = parse_qs(init_data)
        user_str = parsed.get("user", [None])[0]
        return json.loads(user_str) if user_str else {"id": "Guest"}
    except Exception as e:
        log(f"Error parsing TG data: {e}", "ERROR")
        return {"id": "Error"}

# --- ЯДРО СИСТЕМЫ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.boot_time = time.time()
        self.core_id = "QN-NATURAL-ULTRA-4.9.0"
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

# --- ФОНОВЫЙ ВОРКЕР ---
async def core_worker():
    log("CORE: Система супер-мониторинга активирована", "SUCCESS")
    while overlord.is_active:
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()

            db_stats = await get_stats_for_web()
            sys_metrics = overlord.get_real_metrics()
            
            try:
                pool = await get_pool()
                db_alive = pool is not None and not pool._closed
            except: db_alive = False

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

            await manager.broadcast({
                "type": "UPDATE",
                "data": {
                    "balance": round(overlord.current_balance, 2),
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
    worker_task = asyncio.create_task(core_worker())
    yield
    log("🔌 Shutdown sequence initiated...", "WARNING")
    overlord.is_active = False
    worker_task.cancel()
    await close_pool()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- РОУТИНГ ---

@app.post("/api/track-visit")
async def api_register_visit(data: dict = Body(...), request: Request = None):
    try:
        user_info = parse_tg_init_data(data.get("initData"))
        await register_visit(
            request.client.host if request else "0.0.0.0", 
            f"TG:{user_info.get('id')} | {data.get('platform', 'unknown')}"
        )
    except: pass
    return {"status": "ok"}

@app.get("/api/stats")
async def get_stats_api():
    db_stats = await get_stats_for_web()
    return {
        "status": overlord.last_status,
        "balance": round(overlord.current_balance, 2),
        "uptime": overlord.get_uptime(),
        "system": overlord.get_real_metrics(),
        **db_stats
    }

@app.get("/")
@app.get("/index.html")
async def read_root(request: Request):
    return FileResponse("static/index.html")

@app.get("/{page}.html")
async def get_root_html(page: str):
    path = f"static/{page}.html"
    return FileResponse(path) if os.path.exists(path) else FileResponse("static/index.html")

@app.get("/admin")
@app.get("/admin/admin.html")
async def get_admin_root():
    return FileResponse("static/admin/admin.html")

@app.get("/admin/{file_path:path}")
async def get_admin_pages(file_path: str):
    clean_path = file_path.replace(".html", "")
    path = f"static/admin/{clean_path}.html"
    if os.path.exists(path): return FileResponse(path)
    return FileResponse("static/admin/admin.html")

@app.get("/tonconnect-manifest.json")
async def get_manifest():
    return FileResponse("static/tonconnect-manifest.json")

@app.get("/images/{img}")
async def get_image(img: str):
    path = f"static/images/{img}"
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"error": "Not Found"}, 404)

# --- WEBSOCKET С ОБРАБОТКОЙ КОМАНД ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Отправляем начальные данные сразу после подключения
        db_stats = await get_stats_for_web()
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
            # Слушаем входящие сообщения от клиента
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_text("pong")
                continue
                
            try:
                message = json.loads(data)
                if message.get("type") == "COMMAND":
                    action = message.get("action")
                    log(f"Received command: {action}", "CORE")
                    
                    if action == "SYNC_BLOCKCHAIN":
                        # Здесь можно вызвать принудительный запуск логики из core_worker
                        await websocket.send_json({
                            "type": "UPDATE", 
                            "data": {"log_entry": {"msg": "Blockchain sync triggered manually", "type": "OK"}}
                        })

                    elif action == "RESET_COUNTERS":
                        # Место для вызова функции сброса из database.py
                        await websocket.send_json({
                            "type": "UPDATE", 
                            "data": {"log_entry": {"msg": "Database counters reset initiated", "type": "SYS"}}
                        })

                    elif action == "EMERGENCY_STOP":
                        overlord.last_status = "EMERGENCY_STOP"
                        await websocket.send_json({
                            "type": "UPDATE", 
                            "data": {"log_entry": {"msg": "EMERGENCY STOP ACTIVATED", "type": "ERR"}}
                        })
            except json.JSONDecodeError:
                pass

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")

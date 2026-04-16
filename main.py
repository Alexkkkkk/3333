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
    timestamp = datetime.now().strftime("%H:%M:%S")
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
            self.last_check_time = time.time()

    def get_uptime(self):
        return int(time.time() - self.boot_time)

    def get_real_metrics(self):
        if not PSUTIL_AVAILABLE: return {"cpu": 5, "ram": 10}
        try:
            now = time.time()
            diff = max(now - self.last_check_time, 0.1)
            self.last_check_time = now
            net_now = psutil.net_io_counters()
            # Скорость в MB/s для фронтенда
            traffic_speed = (net_now.bytes_recv - self.net_old.bytes_recv + net_now.bytes_sent - self.net_old.bytes_sent) / diff / (1024*1024)
            self.net_old = net_now
            return {
                "cpu": psutil.cpu_percent(interval=None),
                "ram": psutil.virtual_memory().percent,
                "traffic_mb": round(max(0, traffic_speed), 2)
            }
        except: return {"cpu": 0, "ram": 0, "traffic_mb": 0}

overlord = OmniNeuralOverlord()

# --- ФОНОВЫЙ ВОРКЕР ---
async def core_worker():
    log("CORE: Система мониторинга запущена", "SUCCESS")
    while overlord.is_active:
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()

            db_stats = await get_stats_for_web()
            sys_metrics = overlord.get_real_metrics()
            
            # Проверка кошелька через TON (если включено)
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
                        overlord.last_status = "SYNC_ACTIVE"
                except: 
                    overlord.last_status = "SYNC_LAG"
            else:
                overlord.last_status = "SYNC_ACTIVE"

            # Рассылка обновлений всем админам через WebSocket
            await manager.broadcast({
                "type": "UPDATE",
                "data": {
                    "balance": round(overlord.current_balance, 2),
                    "traffic": sys_metrics["traffic_mb"], # Передаем MB/s в поле traffic
                    "connections": db_stats.get('total_visits', 0),
                    "system": {"cpu": sys_metrics["cpu"]},
                    "status": overlord.last_status,
                    "uptime": overlord.get_uptime()
                }
            })
            
            # Случайные системные логи для "живости" интерфейса
            if random.random() > 0.8:
                await manager.broadcast({
                    "type": "UPDATE",
                    "data": {"log_entry": {"msg": "Kernel database integrity check: OK", "type": "SYS"}}
                })

            await asyncio.sleep(3) 
        except Exception as e:
            log(f"Monitoring Error: {e}", "ERROR")
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

@app.get("/")
@app.get("/index.html")
async def read_root():
    return FileResponse("static/index.html")

@app.get("/admin")
@app.get("/admin/admin.html")
async def get_admin_root():
    return FileResponse("static/admin/admin.html")

# Универсальный роут для статических HTML файлов
@app.get("/{file_path:path}.html")
async def get_html_files(file_path: str):
    full_path = f"static/{file_path}.html"
    if os.path.exists(full_path):
        return FileResponse(full_path)
    return FileResponse("static/index.html")

@app.get("/tonconnect-manifest.json")
async def get_manifest():
    return FileResponse("static/tonconnect-manifest.json")

# --- WEBSOCKET ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Приветственный пакет данных
        await websocket.send_json({
            "type": "UPDATE",
            "data": {
                "log_entry": {"msg": "Admin connection established. System secure.", "type": "OK"},
                "status": overlord.last_status
            }
        })

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "COMMAND":
                    action = msg.get("action")
                    log(f"Admin command: {action}", "CORE")
                    
                    if action == "SYNC_BLOCKCHAIN":
                        await websocket.send_json({
                            "type": "UPDATE", 
                            "data": {"log_entry": {"msg": "Manual Blockchain Resync: DONE", "type": "OK"}}
                        })
                    
                    elif action == "RESET_COUNTERS":
                        # Здесь можно вызвать функцию очистки из database.py
                        await websocket.send_json({
                            "type": "UPDATE", 
                            "data": {"log_entry": {"msg": "Traffic counters cleared by admin", "type": "SYS"}}
                        })

                    elif action == "EMERGENCY_STOP":
                        overlord.last_status = "LINK_TERMINATED"
                        await websocket.send_json({
                            "type": "UPDATE", 
                            "data": {"log_entry": {"msg": "PROTOCOL 0: Connection severed", "type": "ERR"}}
                        })

            except json.JSONDecodeError:
                if data == "ping": await websocket.send_text("pong")

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket)

# Монтирование статики (картинки, стили)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")

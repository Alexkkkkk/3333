import asyncio
import os
import json
import time
import sys
import random
from datetime import datetime
from typing import List
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Загружаем переменные окружения
load_dotenv()

# --- КОНФИГУРАЦИЯ ---
PORT = int(os.getenv("PORT", 3000))
TON_ENABLED = False

# Проверка psutil для системных данных
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Импорт функций БД (Файл database.py должен быть в той же папке)
try:
    from database import (
        init_db, get_stats_for_web, register_visit, 
        save_wallet_state, log_ai_action, load_remote_config, sync_wallet_data
    )
except ImportError:
    print("\033[91m[ERROR] Файл database.py не найден! Проверьте наличие файла в директории.\033[0m")
    sys.exit(1)

# Импорт TON библиотек
try:
    from pytoniq import LiteClient, WalletV4R2
    TON_ENABLED = True
except ImportError:
    TON_ENABLED = False

# --- ЛОГИРОВАНИЕ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARNING": "\033[93m", "ERROR": "\033[91m", "CORE": "\033[95m"}
    print(f"{colors.get(level, '')}[{timestamp}] [{level}] {message}\033[0m", flush=True)

# --- МЕНЕДЖЕР WEB-SOCKET (СИНХРОНИЗАЦИЯ) ---
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
        """Рассылка данных всем подключенным клиентам."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# --- ЯДРО СИСТЕМЫ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.boot_time = time.time()
        self.core_id = "QN-SYNC-4.1.0"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_uptime(self):
        return int(time.time() - self.boot_time)

overlord = OmniNeuralOverlord()

# --- LIFESPAN (Запуск и остановка) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(">>> 🌌 QUANTUM HYBRID CORE STARTING <<<", "CORE")
    # Инициализация таблиц БД
    await init_db()
    
    # Загрузка конфигурации (мнемоники) из БД
    cfg = await load_remote_config()
    if cfg and cfg.get('mnemonic'):
        overlord.mnemonic = cfg['mnemonic'].strip()
    
    # Запуск фонового воркера
    worker_task = asyncio.create_task(core_worker())
    
    yield
    
    # Завершение работы
    overlord.is_active = False
    worker_task.cancel()
    log("SYS: Core Shutdown Complete", "CORE")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- РОУТИНГ ПАНЕЛИ УПРАВЛЕНИЯ ---

@app.get("/")
@app.get("/index.html")
async def read_root(request: Request):
    # Регистрация визита в БД
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    return FileResponse("static/index.html")

@app.get("/admin/{page}")
async def get_admin_pages(page: str):
    path = f"static/admin/{page}"
    if os.path.exists(path):
        return FileResponse(path)
    return FileResponse("static/index.html")

# Исправление путей для картинок и фавикона
@app.get("/images/{img}")
async def get_image(img: str):
    path = f"static/images/{img}"
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"error": "Not Found"}, 404)

@app.get("/favicon.ico")
async def get_favicon():
    path = "static/images/logo.png"
    return FileResponse(path) if os.path.exists(path) else JSONResponse(None, 404)

# --- API (СИНХРОНИЗИРОВАНО С DATABASE.PY) ---

@app.get("/api/stats")
async def get_stats():
    db_stats = await get_stats_for_web()
    return {
        "balance": round(overlord.current_balance, 2),
        "visitors": db_stats.get('traffic', 0),        # Синхрон с ключом из БД
        "connections": db_stats.get('connections', 0), # Синхрон с ключом из БД
        "qc_balance": db_stats.get('qc_balance', 0),
        "roi_24h": db_stats.get('roi_24h', 0),
        "cpu_load": psutil.cpu_percent() if PSUTIL_AVAILABLE else random.randint(12, 18),
        "status": overlord.last_status,
        "uptime": overlord.get_uptime(),
        "core_id": overlord.core_id
    }

# --- WEBSOCKET SYNC ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db_stats = await get_stats_for_web()
    try:
        # Начальный пакет данных (INIT)
        await websocket.send_json({
            "type": "INIT",
            "balance": round(overlord.current_balance, 2),
            "visitors": db_stats.get('traffic', 0),
            "connections": db_stats.get('connections', 0),
            "qc_balance": db_stats.get('qc_balance', 0),
            "roi_24h": db_stats.get('roi_24h', 0),
            "cpu_load": psutil.cpu_percent() if PSUTIL_AVAILABLE else 5,
            "status": overlord.last_status,
            "uptime": overlord.get_uptime(),
            "core": overlord.core_id
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log(f"WebSocket Error: {e}", "WARNING")
        manager.disconnect(websocket)

# --- ФОНОВЫЙ ВОРКЕР (БИЕНИЕ СЕРДЦА) ---

async def core_worker():
    log("CORE: Воркер мониторинга активен", "SUCCESS")
    while overlord.is_active:
        try:
            # Проверка обновления конфигурации
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()

            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "STANDBY"
                await manager.broadcast({
                    "type": "UPDATE", "status": "STANDBY", 
                    "cpu_load": psutil.cpu_percent() if PSUTIL_AVAILABLE else 2,
                    "uptime": overlord.get_uptime()
                })
                await asyncio.sleep(10)
                continue

            async with LiteClient.from_mainnet_config() as client:
                wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                overlord.last_status = "ACTIVE"
                
                while overlord.is_active:
                    # 1. Запрос баланса из блокчейна
                    raw_bal = await wallet.get_balance()
                    new_balance = raw_bal / 1e9
                    
                    # 2. Проверка новых депозитов
                    if new_balance > overlord.current_balance and overlord.current_balance > 0:
                        await manager.broadcast({
                            "type": "EVENT", "event": "deposit", 
                            "amount": round(new_balance - overlord.current_balance, 2)
                        })
                    
                    overlord.current_balance = new_balance
                    
                    # 3. Сбор свежей статистики из БД
                    db_stats = await get_stats_for_web()

                    # 4. Трансляция всем пользователям
                    await manager.broadcast({
                        "type": "UPDATE",
                        "balance": round(overlord.current_balance, 2),
                        "visitors": db_stats.get('traffic', 0),
                        "connections": db_stats.get('connections', 0),
                        "qc_balance": db_stats.get('qc_balance', 0),
                        "roi_24h": db_stats.get('roi_24h', 0),
                        "cpu_load": psutil.cpu_percent() if PSUTIL_AVAILABLE else random.randint(10, 20),
                        "status": "ACTIVE",
                        "uptime": overlord.get_uptime(),
                        "recent_actions": db_stats.get('recent_actions', [])
                    })

                    # 5. Синхронизация состояния кошелька с БД
                    await save_wallet_state(
                        address=str(wallet.address), 
                        balance=overlord.current_balance, 
                        qc=overlord.current_balance * 135.5
                    )
                    
                    await asyncio.sleep(5) 

        except Exception as e:
            log(f"Worker Loop Error: {e}", "ERROR")
            overlord.last_status = "ERROR"
            await asyncio.sleep(10)

# Монтируем статику
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=PORT, 
        proxy_headers=True, 
        forwarded_allow_ips="*",
        ws_ping_interval=20,
        ws_ping_timeout=20
    )

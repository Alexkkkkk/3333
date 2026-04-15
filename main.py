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
🧬 PROJECT MAP / СТРУКТУРА ПРОЕКТА (DO NOT CHANGE):
/ (root)
├── main.py                     # Основной сервер (этот файл)
├── database.py                 # Логика БД (asyncpg)
├── requirements.txt            # Зависимости
├── Dockerfile                  # Контейнер
└── static/                     # Статические ресурсы
    ├── index.html              # Главная страница (Quantum Protocol)
    ├── tonconnect-manifest.json
    ├── style.css
    ├── images/                 # Лого и картинки
    │   └── logo.png
    └── admin/                  # Панель управления
        ├── admin.html          # Главная админки
        ├── wallets.html        # Управление кошельками
        └── settings.html       # Настройки ядра
"""

# --- ИМПОРТ ФУНКЦИЙ БД ---
try:
    from database import (
        init_db, get_stats_for_web, register_visit, 
        save_wallet_state, log_ai_action, load_remote_config,
        manager, get_pool, close_pool, QuantumOrchestrator
    )
except ImportError:
    print("\033[91m[ERROR] Файл database.py не найден или содержит ошибки!\033[0m")
    sys.exit(1)

# --- КОНФИГУРАЦИЯ ---
PORT = int(os.getenv("PORT", 3000))
TON_ENABLED = False

# Проверка psutil для системных данных
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
    print("\033[93m[WARNING] Библиотеки TON не найдены. Работа в режиме STANDBY.\033[0m")

# --- ЛОГИРОВАНИЕ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARNING": "\033[93m", "ERROR": "\033[91m", "CORE": "\033[95m"}
    print(f"{colors.get(level, '')}[{timestamp}] [{level}] {message}\033[0m", flush=True)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def parse_tg_init_data(init_data: str):
    """Парсит строку initData из Telegram WebApp"""
    try:
        if not init_data:
            return {"id": "Unknown"}
        parsed = parse_qs(init_data)
        user_str = parsed.get("user", [None])[0]
        if user_str:
            return json.loads(user_str)
        return {"id": "Guest"}
    except Exception as e:
        log(f"Error parsing TG data: {e}", "ERROR")
        return {"id": "Error"}

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

# --- ФОНОВЫЙ ВОРКЕР (БИЕНИЕ СЕРДЦА) ---
async def core_worker():
    log("CORE: Воркер мониторинга активен и синхронизирован", "SUCCESS")
    while overlord.is_active:
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()

            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "STANDBY"
                # Периодическая рассылка даже в Standby
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
                    raw_bal = await wallet.get_balance()
                    new_balance = raw_bal / 1e9
                    
                    if new_balance > overlord.current_balance and overlord.current_balance > 0:
                        diff = round(new_balance - overlord.current_balance, 2)
                        await log_ai_action("DEPOSIT", diff, f"Received {diff} TON")
                        await manager.broadcast({
                            "type": "EVENT", "event": "deposit", 
                            "amount": diff
                        })
                    
                    overlord.current_balance = new_balance
                    db_stats = await get_stats_for_web()

                    # Основной широковещательный пакет данных
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

# --- LIFESPAN (Управление запуском и остановкой) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(">>> 🌌 QUANTUM HYBRID CORE STARTING <<<", "CORE")
    
    # 1. Инициализация БД (Таблицы и индексы)
    await init_db()
    
    # 2. Запуск фоновых задач оркестратора (Пульс и Очистка)
    QuantumOrchestrator.start_background_tasks()
    
    # 3. Запуск основного TON воркера
    worker_task = asyncio.create_task(core_worker())
    
    yield
    
    # --- SHUTDOWN ---
    log("🔌 Завершение работы системы...", "WARNING")
    overlord.is_active = False
    worker_task.cancel()
    
    # Закрываем пул соединений БД
    await close_pool()
    log("SYS: Core Shutdown Complete", "CORE")

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
    user_info = parse_tg_init_data(init_data_raw)
    
    await register_visit(
        request.client.host if request else "0.0.0.0", 
        f"TG_ID:{user_info.get('id')} | {data.get('platform', 'unknown')}"
    )
    
    log(f"VISIT: Пользователь {user_info.get('username', user_info.get('id'))} вошел в терминал", "SUCCESS")
    return {"status": "ok", "core_sync": True}

@app.get("/")
@app.get("/index.html")
async def read_root(request: Request):
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    return FileResponse("static/index.html")

@app.get("/admin")
@app.get("/admin/")
@app.get("/admin/admin.html")
async def get_admin_root():
    return FileResponse("static/admin/admin.html")

@app.get("/admin/{file_path:path}")
async def get_admin_pages(file_path: str):
    path = f"static/admin/{file_path}"
    if not path.endswith(".html") and not os.path.isdir(path):
        path += ".html"
    if os.path.exists(path):
        return FileResponse(path)
    return FileResponse("static/admin/admin.html")

@app.get("/tonconnect-manifest.json")
async def get_manifest():
    return FileResponse("static/tonconnect-manifest.json")

@app.get("/api/stats")
async def get_stats():
    db_stats = await get_stats_for_web()
    return JSONResponse({
        "status": overlord.last_status,
        "balance": round(overlord.current_balance, 2),
        "uptime": overlord.get_uptime(),
        "core_id": overlord.core_id,
        **db_stats
    })

@app.get("/{page}.html")
async def get_static_html(page: str):
    path = f"static/{page}.html"
    if os.path.exists(path):
        return FileResponse(path)
    return FileResponse("static/index.html")

@app.get("/images/{img}")
async def get_image(img: str):
    path = f"static/images/{img}"
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"error": "Not Found"}, 404)

@app.get("/favicon.ico")
async def get_favicon():
    path = "static/images/logo.png"
    return FileResponse(path) if os.path.exists(path) else JSONResponse(None, 404)

# --- WEBSOCKET ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db_stats = await get_stats_for_web()
    try:
        await websocket.send_json({
            "type": "INIT",
            "balance": round(overlord.current_balance, 2),
            **db_stats,
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

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")

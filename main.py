import asyncio
import os
import json
import time
import sys
import random
import traceback
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Импорт функций из твоего модуля database.py
from database import (
    init_db, get_stats_for_web, register_visit, 
    save_wallet_state, log_ai_action, update_remote_config, 
    load_remote_config
)

load_dotenv()

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", "ERROR": "\033[91m", 
        "CORE": "\033[95m", "TRACE": "\033[90m"
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    log_msg = f"[{timestamp}] [{level}] {message}"
    print(f"{color}{log_msg}{reset}", flush=True)

# --- ИНИЦИАЛИЗАЦИЯ TON ЯДРА ---
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V4.1 + POSTGRES ANALYTICS <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    log("L1: Библиотеки TON (pytoniq) загружены", "SUCCESS")
    TON_ENABLED = True
except ImportError:
    log("Критическая ошибка: pytoniq не найден! Работа в режиме эмуляции.", "ERROR")
    TON_ENABLED = False

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        # Генерация уникального ID ядра для сессии
        self.core_id = f"QC-CORE-{os.urandom(2).hex().upper()}"
        
        self.admin_login = os.getenv("ADMIN_LOGIN", "admin")
        self.admin_pass = os.getenv("ADMIN_PASS", "quantum2026")
        
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_static_path(self):
        """Интеллектуальный поиск папки static."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        paths_to_check = [
            os.path.join(base_dir, "static"),
            "./static",
            "/app/static"
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                return os.path.abspath(p)
        return base_dir

overlord = OmniNeuralOverlord()

async def sync_config():
    """Синхронизация параметров между БД и памятью приложения."""
    try:
        cfg = await load_remote_config()
        if cfg and cfg.get('mnemonic'):
            overlord.mnemonic = cfg['mnemonic'].strip()
            return True
    except Exception as e:
        log(f"Sync Config Fail: {e}", "TRACE")
    return False

# --- LIFESPAN (Управление жизненным циклом) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("SYS: Подключение к PostgreSQL Nexus...", "INFO")
    try:
        await init_db()
        await sync_config()
        # Запуск фонового потока мониторинга TON
        worker_task = asyncio.create_task(core_worker())
        log("SYS: Quantum Core Online", "SUCCESS")
        yield
    finally:
        overlord.is_active = False
        worker_task.cancel()
        log("SYS: Ядро деактивировано", "CORE")

app = FastAPI(lifespan=lifespan)

# Настройка CORS
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- ROUTES ---

@app.get("/")
@app.get("/index.html")
async def read_index(request: Request):
    # Регистрируем визит в БД
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    
    path = os.path.join(overlord.get_static_path(), "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Index not found"}, status_code=404)

@app.get("/api/stats")
async def get_stats(request: Request):
    """Основной эндпоинт для обновления данных на фронтенде."""
    try:
        # Трекинг активности
        await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))

        # Получаем данные из аналитики БД
        db_stats = await get_stats_for_web()
        current_cfg = await load_remote_config()
        
        # Форматируем последние действия для таблицы
        raw_actions = db_stats.get('recent_actions', [])
        formatted_actions = []
        
        for item in raw_actions:
            bal = float(item.get("amount", 0))
            formatted_actions.append({
                "address": item.get("address", "Unknown Node"),
                "amount": bal,
                "qc": float(item.get("qc", bal * 137.5)),
                "status": item.get("status", "ACTIVE"),
                "type": item.get("type", "MAINNET")
            })

        return {
            "balance": float(overlord.current_balance), 
            "qc_balance": float(overlord.current_balance * 137.5),
            "traffic": db_stats.get('traffic', 0), 
            "roi": db_stats.get('roi_24h', 0.0),
            "cpu": random.randint(32, 45),
            "connections": db_stats.get('connections', 0),
            "recent_actions": formatted_actions,
            "engine": {
                "core_id": overlord.core_id, 
                "status": overlord.last_status,
                "uptime": round(time.time() - overlord.session_start)
            },
            "config": {
                "yield": current_cfg.get('yield_percentage', 75),
                "ref": current_cfg.get('referral_commission', 15)
            }
        }
    except Exception as e:
        log(f"API Error: {e}", "ERROR")
        return {"status": "offline", "balance": 0.0, "recent_actions": []}

@app.post("/api/update_config")
async def handle_update_config(request: Request):
    """Обновление настроек из админ-панели."""
    try:
        data = await request.json()
        if await update_remote_config(data):
            await sync_config() 
            log("CONFIG: Ядро перенастроено", "SUCCESS")
            return {"status": "success"}
    except:
        pass
    return JSONResponse({"status": "error"}, status_code=500)

# Монтируем статику (стили, скрипты, манифест)
static_dir = overlord.get_static_path()
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{filename}")
async def serve_root_files(filename: str):
    """Маршрутизатор для файлов в корне, картинок и редиректов."""
    # 1. Поиск в корне папки static (index.html, manifest и т.д.)
    file_path = os.path.join(static_dir, filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # 2. Автоматический поиск в папке images
    img_path = os.path.join(static_dir, "images", filename)
    if os.path.isfile(img_path):
        return FileResponse(img_path)
    
    # 3. Fallback: если файл не найден, отдаем главную (для SPA)
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "Not Found"}, status_code=404)

# --- CORE WORKER (TON MONITORING) ---

async def core_worker():
    """Фоновый процесс связи с блокчейном TON."""
    log("CORE: Мониторинг TON запущен", "INFO")
    while overlord.is_active:
        try:
            await sync_config()
            
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "STANDBY"
                await asyncio.sleep(15)
                continue
            
            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    overlord.last_status = "MNEMONIC_ERR"
                    await asyncio.sleep(30); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                
                while overlord.is_active:
                    try:
                        # Получение реального баланса из сети
                        raw_bal = await wallet.get_balance()
                        overlord.current_balance = raw_bal / 1e9
                        
                        # Сохраняем состояние в PostgreSQL
                        await save_wallet_state(
                            address=str(wallet.address),
                            balance=overlord.current_balance,
                            qc=overlord.current_balance * 137.5 
                        )
                        
                        # Эмуляция обучения ИИ
                        if random.random() > 0.8:
                            await log_ai_action(
                                strategy={'cmd': 'SYNC', 'amt': overlord.current_balance, 'reason': 'Pulse Check'},
                                market={'status': 'stable', 'net': 'mainnet'}
                            )

                        # Проверка смены мнемоники
                        old_mne = overlord.mnemonic
                        await sync_config()
                        if overlord.mnemonic != old_mne:
                            log("CORE: Переподключение к новому кошельку...", "WARNING")
                            break
                            
                        await asyncio.sleep(20) 
                    except Exception as e:
                        log(f"Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Global Loop Error: {e}", "ERROR")
            overlord.last_status = "RECONNECTING"
            await asyncio.sleep(10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Сервер развернут на порту {port}", "CORE")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        proxy_headers=True, 
        forwarded_allow_ips="*"
    )

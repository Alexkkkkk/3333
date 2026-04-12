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

# Импорт функций из модуля database.py
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
        # Уникальный ID сессии для отладки
        self.core_id = f"QC-CORE-{os.urandom(2).hex().upper()}"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_static_path(self):
        """Интеллектуальный поиск папки static с авто-созданием."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        paths_to_check = [
            os.path.join(base_dir, "static"),
            "./static",
            "/app/static"
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                return os.path.abspath(p)
        
        static_p = os.path.join(base_dir, "static")
        os.makedirs(static_p, exist_ok=True)
        return static_p

overlord = OmniNeuralOverlord()
static_dir = overlord.get_static_path()

async def sync_config():
    """Синхронизация мнемоники и настроек из PostgreSQL в память RAM."""
    try:
        cfg = await load_remote_config()
        if cfg and cfg.get('mnemonic'):
            overlord.mnemonic = cfg['mnemonic'].strip()
            return True
    except Exception as e:
        log(f"Sync Config Fail: {e}", "TRACE")
    return False

# --- LIFESPAN (Жизненный цикл приложения) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("SYS: Подключение к PostgreSQL Nexus...", "INFO")
    try:
        await init_db()
        await sync_config()
        # Запуск фонового процесса мониторинга блокчейна
        worker_task = asyncio.create_task(core_worker())
        log(f"SYS: Quantum Core Online ({overlord.core_id})", "SUCCESS")
        yield
    finally:
        overlord.is_active = False
        worker_task.cancel()
        log("SYS: Ядро деактивировано", "CORE")

app = FastAPI(lifespan=lifespan)

# Настройка CORS для работы с внешними кошельками и запросами
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- API ROUTES ---

@app.get("/")
@app.get("/index.html")
async def read_index(request: Request):
    """Главная страница с регистрацией визита."""
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    path = os.path.join(static_dir, "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Index not found"}, status_code=404)

@app.get("/api/stats")
async def get_stats(request: Request):
    """Сбор всей аналитики для приборной панели (Dashboard)."""
    try:
        await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
        db_stats = await get_stats_for_web()
        current_cfg = await load_remote_config() or {}
        
        raw_actions = db_stats.get('recent_actions', [])
        formatted_actions = []
        
        for item in raw_actions:
            bal = float(item.get("amount", 0))
            formatted_actions.append({
                "address": item.get("address", "Unknown Node"),
                "amount": bal,
                "qc": float(item.get("qc", bal * 137.5)),
                "status": item.get("status", "SUCCESS"),
                "type": item.get("type", "MAINNET")
            })

        return {
            "balance": round(float(overlord.current_balance), 2), 
            "qc_balance": round(float(overlord.current_balance * 137.5), 2),
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

@app.post("/api/wallet/sync")
async def sync_wallet(request: Request):
    """Эндпоинт для мгновенного сохранения данных кошелька с фронтенда."""
    try:
        data = await request.json()
        await save_wallet_state(
            address=data.get("address"),
            balance=data.get("balance", 0.0),
            qc=data.get("qc", 0.0)
        )
        log(f"SYNC: Данные кошелька {data.get('address')[:8]}... обновлены", "SUCCESS")
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.post("/api/update_config")
async def handle_update_config(request: Request):
    """Обновление настроек системы (мнемоника, проценты) из админки."""
    try:
        data = await request.json()
        if await update_remote_config(data):
            await sync_config() 
            log("CONFIG: Ядро перенастроено", "SUCCESS")
            return {"status": "success"}
    except Exception as e:
        log(f"Config Update Error: {e}", "TRACE")
    return JSONResponse({"status": "error"}, status_code=500)

# --- РОУТИНГ СТАТИКИ И SPA ---

# Монтируем статику (стили, скрипты, манифест)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{path:path}")
async def serve_all_files(path: str):
    """Универсальный обработчик файлов и SPA-путей."""
    # 1. Простая проверка файла в static
    file_path = os.path.join(static_dir, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # 2. Поиск в images (поддержка коротких путей)
    if path.startswith("images/") or not "/" in path:
        img_name = path.replace("images/", "")
        img_path = os.path.join(static_dir, "images", img_name)
        if os.path.isfile(img_path):
            return FileResponse(img_path)
    
    # 3. Поддержка SPA (например, /swap отдаст swap.html)
    html_path = os.path.join(static_dir, f"{path}.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    
    # 4. Fallback: если путь не найден, отдаем главную (index.html)
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    return JSONResponse({"error": "Not Found"}, status_code=404)

# --- CORE WORKER (Фоновый мониторинг блокчейна) ---

async def core_worker():
    """Фоновый процесс связи с сетью TON Mainnet."""
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
                    await asyncio.sleep(30)
                    continue

                # Подключение к кошельку через мнемонику
                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE: Подключен системный узел {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        # Получение баланса и перевод из нано-токенов в TON
                        raw_bal = await wallet.get_balance()
                        overlord.current_balance = raw_bal / 1e9
                        
                        # Сохранение состояния в PostgreSQL для аналитики
                        await save_wallet_state(
                            address=str(wallet.address),
                            balance=overlord.current_balance,
                            qc=overlord.current_balance * 137.5 
                        )
                        
                        # Эмуляция активности ИИ-ядра
                        if random.random() > 0.85:
                            await log_ai_action(
                                strategy={'cmd': 'SYNC', 'amt': overlord.current_balance, 'reason': 'Pulse Check'},
                                market={'status': 'stable', 'net': 'mainnet'}
                            )

                        # Реакция на изменение настроек в БД
                        old_mne = overlord.mnemonic
                        await sync_config()
                        if overlord.mnemonic != old_mne:
                            log("CORE: Конфигурация изменена, перезапуск узла...", "WARNING")
                            break
                            
                        await asyncio.sleep(20) 
                    except Exception as e:
                        log(f"Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Global Loop Error: {e}", "ERROR")
            overlord.last_status = "RECONNECTING"
            await asyncio.sleep(10)

# --- ТОЧКА ВХОДА ---

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

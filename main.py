import asyncio
import os
import json
import time
import sys
import random
import hashlib
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

# Попытка импорта psutil (защита от ModuleNotFoundError на хостинге)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Импорт функций из модуля database.py (обновленного ранее)
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
        self.core_id = f"QC-CORE-{os.urandom(2).hex().upper()}"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_static_path(self):
        """Определяет корректный путь к папке static с учетом структуры Bothost."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        paths_to_check = [
            os.path.join(base_dir, "static"),
            "./static",
            "/app/static"
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                return os.path.abspath(p)
        
        # Если папки нет, создаем ее (безопасный режим)
        static_p = os.path.join(base_dir, "static")
        os.makedirs(static_p, exist_ok=True)
        return static_p

overlord = OmniNeuralOverlord()
static_dir = overlord.get_static_path()

async def sync_config():
    """Синхронизация локальных параметров с БД."""
    try:
        cfg = await load_remote_config()
        if cfg and cfg.get('mnemonic'):
            overlord.mnemonic = cfg['mnemonic'].strip()
            return True
    except Exception as e:
        log(f"Sync Config Fail: {e}", "TRACE")
    return False

# --- LIFESPAN (Запуск и Остановка) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("SYS: Подключение к Quancore Nexus DB...", "INFO")
    try:
        # Инициализация базы данных и пула
        await init_db()
        await sync_config()
        
        # Запуск фонового воркера мониторинга TON
        worker_task = asyncio.create_task(core_worker())
        log(f"SYS: Quantum Core Online ({overlord.core_id})", "SUCCESS")
        
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
    """Отдача статистики для фронтенда."""
    try:
        # Регистрируем активность в БД
        await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
        
        # Тянем данные из PostgreSQL
        db_stats = await get_stats_for_web()
        current_cfg = await load_remote_config() or {}
        
        # Форматируем лог последних действий
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

        # Нагрузка системы
        if PSUTIL_AVAILABLE:
            cpu_usage = psutil.cpu_percent()
        else:
            cpu_usage = random.randint(14, 26)

        return {
            "balance": round(float(overlord.current_balance), 2), 
            "qc_balance": round(float(overlord.current_balance * 137.5), 2),
            "traffic": round(db_stats.get('traffic', random.uniform(42.0, 48.0)), 2), 
            "roi": db_stats.get('roi_24h', 0.0),
            "cpu": cpu_usage,
            "visitors": db_stats.get('traffic', 1), # Используем трафик как счетчик
            "connections": db_stats.get('connections', random.randint(5, 12)),
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
        return {"status": "offline", "balance": 0.0, "visitors": 0, "recent_actions": []}

@app.post("/api/wallet/sync")
async def sync_wallet(request: Request):
    """Прием данных о кошельке от фронтенда."""
    try:
        data = await request.json()
        address = data.get("address")
        if address:
            await save_wallet_state(
                address=address,
                balance=data.get("balance", 0.0),
                qc=data.get("qc", 0.0)
            )
            log(f"SYNC: Node {address[:8]}... synchronized", "SUCCESS")
            return {"status": "success"}
        return JSONResponse({"status": "error"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# --- РОУТИНГ СТАТИКИ И ИЗОБРАЖЕНИЙ ---

# Монтируем папку static для доступа к CSS/JS
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{path:path}")
async def serve_all_files(path: str):
    """Интеллектуальный поиск файлов и изображений."""
    file_path = os.path.join(static_dir, path)
    
    # 1. Прямой поиск
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # 2. Поиск в images (если фронтенд просит images/logo.png напрямую)
    img_name = path.split("/")[-1]
    img_path = os.path.join(static_dir, "images", img_name)
    if os.path.isfile(img_path):
        return FileResponse(img_path)

    # 3. HTML Fallback
    html_path = os.path.join(static_dir, f"{path}.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    
    # 4. Возврат на главную
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path) if os.path.exists(index_path) else JSONResponse({"error": "Not Found"}, status_code=404)

# --- CORE WORKER (Блокчейн мониторинг) ---

async def core_worker():
    """Фоновый процесс работы с TON."""
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

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE: Узел активен {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        raw_bal = await wallet.get_balance()
                        overlord.current_balance = raw_bal / 1e9
                        
                        # Сохраняем баланс админ-кошелька
                        await save_wallet_state(
                            address=str(wallet.address),
                            balance=overlord.current_balance,
                            qc=overlord.current_balance * 137.5 
                        )
                        
                        # Редкое логирование действий ИИ (для логов в БД)
                        if random.random() > 0.95:
                            await log_ai_action(
                                strategy={'cmd': 'SCAN', 'bal': overlord.current_balance},
                                market={'status': 'stable'}
                            )

                        # Проверяем не сменилась ли мнемоника в БД
                        old_mne = overlord.mnemonic
                        await sync_config()
                        if overlord.mnemonic != old_mne: 
                            log("CORE: Мнемоника обновлена, перезагрузка кошелька...", "WARNING")
                            break
                            
                        await asyncio.sleep(30) 
                    except Exception as e:
                        log(f"Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Global Loop Error: {e}", "ERROR")
            await asyncio.sleep(10)

# --- ЗАПУСК СЕРВЕРА ---

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Запуск на порту {port}", "CORE")
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=port, 
        proxy_headers=True, 
        forwarded_allow_ips="*",
        reload=False 
    )

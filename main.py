import asyncio
import os
import json
import time
import openai
import sys
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
LOG_FILE = "quantum_system.log"

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
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except: pass

# --- ИНИЦИАЛИЗАЦИЯ TON ЯДРА ---
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V3.0 (FastAPI + AI) <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address, begin_cell as BeginCell
    log("L1: Библиотеки TON (pytoniq) загружены", "SUCCESS")
except ImportError:
    log("Критическая ошибка: pytoniq не найден!", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
except ImportError:
    log("L2 ERROR: Файл database.py не найден!", "ERROR")
    async def init_db(): pass
    async def log_ai_action(*args): pass
    async def get_market_state(): return {}
    async def get_stats_for_web(): return {}
    async def load_remote_config(): return {}
    async def update_remote_config(*args): pass

load_dotenv()

# --- УПРАВЛЕНИЕ ЯДРОМ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(32).hex() 
        
        self.pool_addr = None
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.current_balance = 0.0

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        check_paths = [
            os.path.join(base_dir, 'static'),
            os.path.join(os.getcwd(), 'static'),
            '/app/static'
        ]
        for p in check_paths:
            if os.path.exists(p): return p
        return "static"

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg:
                if cfg.get('mnemonic'):
                    self.mnemonic = " ".join(str(cfg.get('mnemonic')).replace('\n', ' ').split())
                self.ai_key = str(cfg.get('ai_api_key', '')).strip()
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                
                pool_raw = str(cfg.get('dedust_pool', cfg.get('token_pool_address', ''))).strip()
                if pool_raw and pool_raw != "None":
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Bad Pool Addr: {pool_raw}", "WARNING")
                return True
            return False
        except Exception as e:
            log(f"Config Sync Error: {e}", "ERROR")
            return False

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT", "reason": "No AI Key"}
        try:
            client = openai.AsyncOpenAI(api_key=self.ai_key)
            res = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                    {"role": "user", "content": json.dumps({"market": market_snapshot})}
                ],
                response_format={ "type": "json_object" },
                timeout=15
            )
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            log(f"AI Neural Error: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Error"}

overlord = OmniNeuralOverlord()

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- WEB ROUTES С ГЛУБОКИМ ЛОГИРОВАНИЕМ ---

@app.get("/")
@app.get("/index.html")
async def serve_index(request: Request):
    path = os.path.join(overlord.get_static_path(), "index.html")
    log(f"WEB: Запрос главной от {request.client.host}", "INFO")
    if os.path.exists(path):
        return FileResponse(path)
    log(f"WEB ERROR: index.html не найден по пути {path}", "ERROR")
    return JSONResponse({"error": "Index not found"}, status_code=404)

@app.get("/admin")
@app.get("/admin/")
@app.get("/admin.html")
async def serve_admin(request: Request):
    static_dir = overlord.get_static_path()
    admin_path = os.path.join(static_dir, "admin", "admin.html")
    
    log(f"WEB: Попытка входа в админку (IP: {request.client.host})", "CORE")
    log(f"TRACE: Проверка пути 1: {admin_path}", "TRACE")
    
    if os.path.exists(admin_path):
        log(f"WEB SUCCESS: Файл найден в static/admin/admin.html", "SUCCESS")
        return FileResponse(admin_path)
    
    fallback = os.path.join(static_dir, "admin.html")
    log(f"TRACE: Путь 1 не найден. Проверка пути 2: {fallback}", "TRACE")
    
    if os.path.exists(fallback):
        log(f"WEB SUCCESS: Файл найден в корне static", "SUCCESS")
        return FileResponse(fallback)
        
    log(f"WEB ERROR: admin.html ОТСУТСТВУЕТ!", "ERROR")
    return JSONResponse({
        "status": "error",
        "message": "Admin file not found",
        "debug_info": {
            "searched_paths": [admin_path, fallback],
            "cwd": os.getcwd(),
            "static_dir_exists": os.path.exists(static_dir)
        }
    }, status_code=404)

@app.get("/{filename}.html")
async def serve_any_html(filename: str, request: Request):
    static_dir = overlord.get_static_path()
    check_paths = [
        os.path.join(static_dir, f"{filename}.html"),
        os.path.join(static_dir, "admin", f"{filename}.html")
    ]
    log(f"WEB: Запрос файла {filename}.html от {request.client.host}", "INFO")
    for p in check_paths:
        if os.path.exists(p):
            return FileResponse(p)
    return JSONResponse({"detail": "Not found"}, status_code=404)

# --- API ---

@app.post("/api/login")
async def handle_login(request: Request):
    try:
        data = await request.json()
        log(f"API: Login attempt -> {data.get('login')}", "INFO")
        if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
            overlord.session_token = os.urandom(32).hex()
            res = JSONResponse({"status": "success"})
            res.set_cookie(key="auth_token", value=overlord.session_token, httponly=True)
            log("API SUCCESS: Авторизация успешна", "SUCCESS")
            return res
        log("API WARNING: Неверный логин или пароль", "WARNING")
        return JSONResponse({"status": "error"}, status_code=401)
    except Exception as e:
        log(f"API ERROR: Login process failed: {e}", "ERROR")
        return JSONResponse({"status": "error"}, status_code=400)

@app.get("/api/stats")
async def get_stats():
    try:
        db_stats = await get_stats_for_web()
        db_stats.update({
            'balance': f"{overlord.current_balance:.2f}",
            'engine': {
                "core_id": overlord.core_id,
                "uptime": round(time.time() - overlord.session_start),
                "status": overlord.last_status
            }
        })
        return db_stats
    except: return {"status": "error"}

# --- STATIC MOUNTING ---
static_path = overlord.get_static_path()
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/style.css")
async def serve_css():
    return FileResponse(os.path.join(static_path, "style.css"))

@app.get("/images/{img}")
async def serve_image(img: str):
    return FileResponse(os.path.join(static_path, "images", img))

# --- CORE WORKER ---
async def core_worker():
    while True:
        try:
            await init_db()
            log("DB: Connected", "SUCCESS")
            break
        except: 
            log("DB: Waiting connection...", "WARNING")
            await asyncio.sleep(5)

    while overlord.is_active:
        try:
            await overlord.update_config_from_db()
            if not overlord.mnemonic:
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10); continue

            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    log("КРИТИЧЕСКИЙ СБОЙ МНЕМОНИКИ", "ERROR")
                    await asyncio.sleep(20); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE: Кошелек готов -> {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        await client.reconnect()
                        overlord.current_balance = (await wallet.get_balance()) / 1e9
                        await asyncio.sleep(30)
                    except: break
        except Exception as e:
            log(f"Core Loop Error: {e}", "ERROR")
            await asyncio.sleep(10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Quantum Overlord запущен на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")

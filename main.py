import asyncio
import os
import json
import time
import openai
import sys
import random
import numpy as np
import traceback
import signal
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
import aiohttp_cors

# --- СИСТЕМА УЛЬТРА-ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", "ERROR": "\033[91m", 
        "CORE": "\033[95m", "TRACE": "\033[90m", "WEB": "\033[36m"
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

# --- ПРОВЕРКА ОКРУЖЕНИЯ ---
log(">>> ИНИЦИАЛИЗАЦИЯ NEURAL SENTINEL V3 <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    log("L1: Библиотеки TON загружены", "SUCCESS")
except ImportError as e:
    log(f"L1 ERROR: Ошибка pytoniq: {e}", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
except ImportError as e:
    log(f"L2 ERROR: Ошибка database.py: {e}", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"SENTINEL-{os.urandom(2).hex().upper()}"
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(16).hex() 
        
        self.mnemonic = None
        self.ai_key = None
        self.target_pool = None
        self.strategy_level = 10
        self.current_balance = 0.0
        self.total_ops = 0
        self.last_status = "BOOTING"
        self.runner = None
        
        log(f"Ядро {self.core_id} сконфигурировано", "CORE")

    def get_static_path(self):
        base = os.path.dirname(os.path.abspath(__file__))
        static_path = os.path.join(base, 'static')
        log(f"FS: Поиск статики в {static_path}", "TRACE")
        return static_path if os.path.exists(static_path) else None

    # --- WEB HANDLERS ---
    async def handle_index(self, request):
        log(f"WEB: Запрос {request.method} {request.path} от {request.remote}", "WEB")
        path = request.path.lower().strip('/')
        static_dir = self.get_static_path()
        if not static_dir: 
            log("WEB ERROR: Папка static не найдена", "ERROR")
            return web.Response(text="Static folder not found", status=404)

        if path == '' or path == 'index.html':
            target = os.path.join(static_dir, 'index.html')
        elif path == 'admin' or path == 'admin/admin.html':
            target = os.path.join(static_dir, 'admin', 'admin.html')
        else:
            target = os.path.join(static_dir, path)

        if os.path.exists(target) and not os.path.isdir(target):
            return web.FileResponse(target)
        
        log(f"WEB: Файл {path} не найден, отдаю index.html", "WARNING")
        return web.FileResponse(os.path.join(static_dir, 'index.html'))

    async def handle_login(self, request):
        try:
            data = await request.json()
            if str(data.get("login")) == self.admin_login and str(data.get("password")) == self.admin_pass:
                res = web.json_response({"status": "success", "token": self.session_token})
                res.set_cookie("auth_token", self.session_token, httponly=False)
                log(f"AUTH: Успешный вход [{request.remote}]", "SUCCESS")
                return res
            log(f"AUTH: Отказ в доступе [{request.remote}]", "WARNING")
            return web.json_response({"status": "error"}, status=401)
        except: return web.json_response({"status": "error"}, status=400)

    async def handle_get_stats(self, request):
        if request.cookies.get("auth_token") != self.session_token:
            return web.json_response({"status": "unauthorized"}, status=401)
        db_stats = await get_stats_for_web()
        return web.json_response({
            "balance": f"{self.current_balance:.2f}",
            "engine": {"core_id": self.core_id, "last_status": self.last_status, "ops_total": self.total_ops},
            "pool_info": {
                "address": self.target_pool or "NOT CONFIGURED",
                "reserve_ton": db_stats.get("reserve_ton", "0.00"),
                "status": "STABLE" if self.is_active else "HALTED"
            }
        })

    async def start_web_server(self):
        log("SERVER: Инициализация сервера...", "INFO")
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
        })
        
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/admin', self.handle_index)
        app.router.add_post('/api/login', self.handle_login)
        app.router.add_get('/api/stats', self.handle_get_stats)
        
        static_dir = self.get_static_path()
        if static_dir:
            app.router.add_static('/static/', path=static_dir)
            if os.path.exists(os.path.join(static_dir, 'images')):
                app.router.add_static('/images/', path=os.path.join(static_dir, 'images'))

        for route in list(app.router.routes()): cors.add(route)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        
        port = int(os.getenv("PORT", 3000))
        host = '0.0.0.0'
        
        log(f"SERVER: Попытка запуска на {host}:{port}", "INFO")
        try:
            site = web.TCPSite(self.runner, host, port)
            await site.start()
            log(f"SERVER: Терминал активен на порту {port}", "SUCCESS")
        except Exception as e:
            log(f"SERVER ERROR: Не удалось запустить сервер: {e}", "ERROR")

    async def core_loop(self):
        log("CORE: Запуск системных процессов...", "INFO")
        
        # ЗАПУСКАЕМ СЕРВЕР ПЕРВЫМ (чтобы Bothost не выдал 504)
        asyncio.create_task(self.start_web_server())

        log("DB: Ожидание подключения к базе данных...", "INFO")
        while True:
            try:
                await init_db()
                log("DB: Связь с PostgreSQL установлена", "SUCCESS")
                break
            except Exception as e:
                log(f"DB: Ошибка: {e}. Повтор через 5с...", "WARNING")
                await asyncio.sleep(5)

        while self.is_active:
            try:
                cfg = await load_remote_config()
                if cfg:
                    self.mnemonic = cfg.get('mnemonic', self.mnemonic)
                    self.ai_key = cfg.get('ai_api_key', self.ai_key)
                
                if not self.mnemonic:
                    self.last_status = "WAITING_CONFIG"
                    await asyncio.sleep(10); continue

                log("TON: Попытка синхронизации с сетью...", "INFO")
                async with LiteClient.from_mainnet_config() as client:
                    wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                    self.last_status = "ACTIVE"
                    log(f"TON: Кошелек {wallet.address} готов", "SUCCESS")
                    
                    while self.is_active:
                        balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=10.0)
                        self.current_balance = balance_nano / 1e9
                        log(f"MONITOR: Баланс {self.current_balance:.2f} TON", "TRACE")
                        await asyncio.sleep(30)
            except Exception as e:
                log(f"CRITICAL: Сбой в цикле: {e}", "ERROR")
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    loop = asyncio.get_event_loop()
    
    async def shutdown(ol):
        log("SHUTDOWN: Деактивация Sentinel...", "WARNING")
        ol.is_active = False
        if ol.runner: 
            log("SHUTDOWN: Остановка сервера...", "TRACE")
            await ol.runner.cleanup()
        
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        log(f"SHUTDOWN: Отмена {len(tasks)} активных задач", "TRACE")
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(overlord)))

    try:
        log("SYSTEM: Запуск завершен успешно", "SUCCESS")
        loop.run_until_complete(overlord.core_loop())
    except (KeyboardInterrupt, SystemExit):
        log("SYSTEM: Работа завершена пользователем.", "INFO")
    except Exception as e:
        log(f"SYSTEM FATAL: {e}\n{traceback.format_exc()}", "ERROR")

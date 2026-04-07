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
log(">>> ЗАПУСК СИСТЕМЫ QUANTUM V3 <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    from pytoniq import begin_cell as BeginCell
    log("Библиотеки TON загружены успешно", "SUCCESS")
except ImportError as e:
    log(f"Ошибка импорта pytoniq: {e}", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Модули базы данных подключены", "SUCCESS")
except ImportError as e:
    log(f"Ошибка импорта database.py: {e}", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(2).hex().upper()}"
        
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(16).hex() 
        
        self.pool_addr = None
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        self.mnemonic = None
        self.ai_key = None
        self.current_balance = 0.0
        self.total_ops = 0
        self.last_status = "BOOTING"
        self.runner = None
        log(f"Ядро {self.core_id} готово к работе", "CORE")

    def get_static_path(self):
        base = os.path.dirname(os.path.abspath(__file__))
        paths = [os.path.join(base, 'static'), '/app/static', './static']
        for p in paths:
            if os.path.exists(p):
                return p
        log("ВНИМАНИЕ: Папка static не найдена!", "WARNING")
        return None

    # --- WEB HANDLERS С ПОДДЕРЖКОЙ НОВОЙ СТРУКТУРЫ ---
    async def handle_index(self, request):
        peer = request.remote
        path = request.path.lower().strip('/')
        log(f"WEB: [{peer}] запрос {request.method} -> {request.path}", "WEB")
        
        static_dir = self.get_static_path()
        if not static_dir: return web.Response(text="Static folder missing", status=404)
        
        # Маршрутизация согласно структуре
        if path in ['admin', 'admin/index.html']:
            target = os.path.join(static_dir, 'admin', 'index.html')
        elif path == '' or path == 'index.html':
            target = os.path.join(static_dir, 'index.html')
        elif path == 'privacy.html':
            target = os.path.join(static_dir, 'privacy.html')
        elif path == 'terms.html':
            target = os.path.join(static_dir, 'terms.html')
        elif path == 'tonconnect-manifest.json':
            target = os.path.join(static_dir, 'tonconnect-manifest.json')
        else:
            # Поиск в корне static (для script.py и прочих)
            target = os.path.join(static_dir, path)

        if os.path.exists(target) and not os.path.isdir(target):
            return web.FileResponse(target)
        
        log(f"WEB: Файл {path} не найден, возврат на главную", "TRACE")
        return web.FileResponse(os.path.join(static_dir, 'index.html'))

    async def handle_login(self, request):
        try:
            data = await request.json()
            if str(data.get("login")) == self.admin_login and str(data.get("password")) == self.admin_pass:
                res = web.json_response({"status": "success", "token": self.session_token})
                res.set_cookie("auth_token", self.session_token, httponly=True)
                log(f"AUTH: Вход выполнен успешно [{request.remote}]", "SUCCESS")
                return res
            log(f"AUTH: Ошибка входа [{request.remote}]", "WARNING")
            return web.json_response({"status": "error", "message": "Invalid credentials"}, status=401)
        except: return web.json_response({"status": "error"}, status=400)

    async def handle_get_stats(self, request):
        if request.cookies.get("auth_token") != self.session_token:
            log(f"WEB: Отказ в доступе к API для {request.remote}", "WARNING")
            return web.json_response({"status": "unauthorized"}, status=401)
        
        log("WEB: Синхронизация статистики", "TRACE")
        db_stats = await get_stats_for_web()
        db_stats.update({
            'balance': f"{self.current_balance:.2f}",
            'engine': {"core_id": self.core_id, "status": self.last_status, "ops": self.total_ops}
        })
        return web.json_response(db_stats)

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
        
        # Роутинг страниц
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/admin', self.handle_index)
        app.router.add_get('/privacy.html', self.handle_index)
        app.router.add_get('/terms.html', self.handle_index)
        app.router.add_get('/tonconnect-manifest.json', self.handle_index)
        
        # API
        app.router.add_post('/api/login', self.handle_login)
        app.router.add_get('/api/stats', self.handle_get_stats)
        
        static_dir = self.get_static_path()
        if static_dir:
            # Раздача изображений
            app.router.add_static('/images/', path=os.path.join(static_dir, 'images'))
            # Раздача скриптов и файлов в корне static
            app.router.add_static('/static/', path=static_dir)
            # Статика для админ-панели
            admin_path = os.path.join(static_dir, 'admin')
            if os.path.exists(admin_path):
                app.router.add_static('/admin/static/', path=admin_path)

        for route in list(app.router.routes()): cors.add(route)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        port = int(os.getenv("PORT", 3000))
        await web.TCPSite(self.runner, '0.0.0.0', port).start()
        log(f"СЕРВЕР: Запущен на http://0.0.0.0:{port}", "SUCCESS")

    async def core_loop(self):
        log("БАЗА: Подключение...", "INFO")
        while True:
            try:
                await init_db()
                log("БАЗА: Соединение установлено", "SUCCESS")
                break
            except:
                log("БАЗА: Ожидание PostgreSQL...", "WARNING")
                await asyncio.sleep(5)

        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                log("КОНФИГ: Чтение настроек...", "TRACE")
                cfg = await load_remote_config()
                if not cfg or not cfg.get('mnemonic'):
                    log("КОНФИГ: Данные отсутствуют. Жду ввода в админке...", "WARNING")
                    self.last_status = "WAITING_CONFIG"
                    await asyncio.sleep(10); continue

                self.mnemonic = cfg.get('mnemonic')
                self.ai_key = cfg.get('ai_api_key')
                
                async with LiteClient.from_mainnet_config() as client:
                    wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                    log(f"TON: Кошелек {wallet.address} активен", "SUCCESS")
                    self.last_status = "ACTIVE"
                    
                    while self.is_active:
                        try:
                            balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=10.0)
                            self.current_balance = balance_nano / 1e9
                            log(f"TON: Баланс: {self.current_balance:.2f} TON", "INFO")

                            market = await get_market_state()
                            plan = await self.fetch_neural_strategy(market)
                            
                            if plan.get('cmd') == "BUY":
                                log(f"AI: КУПИТЬ на {plan.get('amt')} TON", "SUCCESS")
                                await self.dispatch_hft_pulse(wallet, plan)
                            else:
                                log(f"AI: Ожидание. Причина: {plan.get('reason')}", "INFO")

                            await asyncio.sleep(20)
                        except asyncio.TimeoutError:
                            log("TON: Тайм-аут ноды, переподключение...", "WARNING")
                            break
                        except Exception as e:
                            log(f"ЦИКЛ: Ошибка: {e}", "ERROR")
                            await asyncio.sleep(5); break

            except Exception as e:
                log(f"ЯДРО: Критический сбой: {e}", "ERROR")
                await asyncio.sleep(10)

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT", "reason": "No API Key"}
        try:
            client = openai.AsyncOpenAI(api_key=self.ai_key)
            res = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                          {"role": "user", "content": json.dumps(market_snapshot)}],
                response_format={"type": "json_object"}, timeout=15
            )
            return json.loads(res.choices[0].message.content)
        except: return {"cmd": "WAIT", "reason": "AI Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        log("TON: Инициация транзакции...", "TRACE")
        # Логика отправки...
        self.total_ops += 1
        return True

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(overlord.core_loop())
    except KeyboardInterrupt:
        log("СИСТЕМА: Остановка...", "WARNING")

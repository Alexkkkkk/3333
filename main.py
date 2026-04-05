import asyncio
import os
import json
import time
import openai
import sys
import random
import numpy as np
import traceback
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
import aiohttp_cors

# --- УЛЬТРА-СИСТЕМА ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",    # Red
        "CORE": "\033[95m",    # Magenta
        "TRACE": "\033[90m"     # Gray
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    # flush=True гарантирует мгновенное появление лога в терминале Bothost
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM <<<", "CORE")

# --- ПОШАГОВЫЙ ИМПОРТ И ПРОВЕРКА ЗАВИСИМОСТЕЙ ---
log("Шаг 1: Загрузка переменных окружения (.env)...", "TRACE")
load_dotenv()

log("Шаг 2: Импорт библиотек TON (pytoniq)...", "TRACE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    # Попытка импорта BeginCell из разных веток библиотеки
    try:
        from pytoniq_core import BeginCell
        log("BeginCell загружен из pytoniq_core", "TRACE")
    except ImportError:
        from pytoniq import BeginCell
        log("BeginCell загружен из pytoniq", "TRACE")
    log("Зависимости TON: OK", "SUCCESS")
except Exception as e:
    log(f"КРИТИЧЕСКАЯ ОШИБКА TON: {e}. Проверь requirements.txt", "ERROR")
    sys.exit(1)

log("Шаг 3: Подключение модуля базы данных (database.py)...", "TRACE")
try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Модули базы данных: OK", "SUCCESS")
except Exception as e:
    log(f"ОШИБКА ИМПОРТА database.py: {e}. Файл должен быть в корне!", "ERROR")
    sys.exit(1)

class OmniNeuralOverlord:
    def __init__(self):
        log("Шаг 4: Создание экземпляра Overlord...", "TRACE")
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.pool_addr = None
        self.vault_ton = Address("EQCt0-Ba6Y_9_6p20tH_E_Oq_H_O_O_O_O_O_O_O_O_O_O_O_O")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.synaptic_history = []
        self.last_status = "BOOTING"
        self.total_ops = 0
        log(f"Ядро создано. ID: {self.core_id}", "CORE")

    async def update_config_from_db(self):
        """Синхронизация локальных настроек с данными из PostgreSQL."""
        try:
            cfg = await load_remote_config()
            if not cfg:
                return False
            
            if cfg.get('mnemonic'):
                self.mnemonic = cfg.get('mnemonic').strip().replace('\n', ' ').replace('\r', '')
                self.ai_key = cfg.get('ai_api_key', '').strip()
                
                pool_raw = cfg.get('dedust_pool')
                if pool_raw: 
                    self.pool_addr = Address(pool_raw)
                
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                self.last_status = "ACTIVE"
                return True
            return False
        except Exception as e:
            log(f"Ошибка синхронизации конфига: {e}", "ERROR")
            return False

    # --- API & WEB DASHBOARD ---
    async def handle_index(self, request):
        if os.path.exists('./static/index.html'):
            return web.FileResponse('./static/index.html')
        return web.Response(text="<h1 style='color:blue'>QUANTUM CORE ACTIVE</h1>", content_type='text/html')

    async def handle_get_stats(self, request):
        try:
            db_stats = await get_stats_for_web()
            db_stats['engine'] = {
                "core_id": self.core_id,
                "ops_total": self.total_ops,
                "uptime": round(time.time() - self.session_start),
                "last_status": self.last_status
            }
            return web.json_response(db_stats)
        except Exception as e:
            return web.json_response({"status": "error", "msg": str(e)})

    async def handle_update_config(self, request):
        try:
            data = await request.json()
            await update_remote_config(data)
            await self.update_config_from_db()
            log("Конфигурация обновлена через API", "SUCCESS")
            return web.json_response({"status": "success"})
        except Exception as e:
            return web.json_response({"status": "error", "msg": str(e)}, status=400)

    # --- ANALYTICS & NEURAL ENGINE ---
    def _calculate_hyper_analytics(self):
        """Расчет индекса фрактальной эффективности (FEI)."""
        try:
            if len(self.synaptic_history) < 5: return None
            prices = np.array([h['price'] for h in self.synaptic_history if h['price'] > 0])
            if len(prices) < 5: return None
            
            diffs = np.abs(np.diff(prices))
            total_movement = np.sum(diffs)
            if total_movement == 0: return {"market_state": "STAGNANT", "fei": 0}
            fei = np.abs(prices[-1] - prices[0]) / total_movement
            return {"market_state": "TRENDING" if fei > 0.4 else "CHAOTIC", "fei": round(float(fei), 4)}
        except: return None

    async def fetch_neural_strategy(self, market_snapshot):
        """Запрос торгового решения у AI (GPT-4o)."""
        if not self.ai_key: 
            return {"cmd": "WAIT", "reason": "No AI Key"}
        
        try:
            hyper = self._calculate_hyper_analytics()
            openai.api_key = self.ai_key
            
            # Поддержка разных версий библиотеки OpenAI (v0.28 vs v1.0+)
            if hasattr(openai, 'AsyncOpenAI'):
                client = openai.AsyncOpenAI(api_key=self.ai_key)
                res = await asyncio.wait_for(client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                        {"role": "user", "content": json.dumps({"market": market_snapshot, "hyper": hyper})}
                    ],
                    response_format={ "type": "json_object" }
                ), timeout=15)
                content = res.choices[0].message.content
            else:
                res = await asyncio.wait_for(openai.ChatCompletion.acreate(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                        {"role": "user", "content": json.dumps({"market": market_snapshot, "hyper": hyper})}
                    ]
                ), timeout=15)
                content = res.choices[0].message.content

            return json.loads(content)
        except Exception as e:
            log(f"Neural AI Error: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Timeout/Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        """Исполнение транзакции в сети TON."""
        if not self.pool_addr: return False
        try:
            amt = float(plan.get('amt', 0))
            if amt <= 0: return False
            
            nano_amt = int(amt * 1e9)
            
            # Формирование Payload для свопа (DeDust)
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) 
                            .store_uint(int(time.time() + 300), 64) 
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=swap_payload)
            self.total_ops += 1
            log(f"TON: Pulse successful. Op #{self.total_ops} | Amount: {amt}", "SUCCESS")
            return True
        except Exception as e:
            log(f"TON: Pulse failed: {e}", "ERROR")
            return False

    # --- SERVER RUNNERS ---
    async def start_web_server(self):
        """Запуск внутреннего API и статики для Dashboard."""
        try:
            app = web.Application()
            cors = aiohttp_cors.setup(app, defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_headers="*", allow_credentials=True,
                    expose_headers="*", allow_methods="*"
                )
            })
            
            app.router.add_get('/', self.handle_index)
            app.router.add_get('/api/stats', self.handle_get_stats)
            app.router.add_post('/api/config', self.handle_update_config)
            
            if os.path.exists('static'):
                app.router.add_static('/static/', path='static', name='static')

            for route in list(app.router.routes()):
                cors.add(route)
            
            runner = web.AppRunner(app)
            await runner.setup()
            port = int(os.getenv("PORT", 3000))
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            log(f"Web Dashboard ONLINE (Порт {port})", "SUCCESS")
        except Exception as e:
            log(f"Ошибка Web-сервера: {e}", "ERROR")

    async def core_loop(self):
        """Основной бесконечный цикл работы ядра."""
        log("Запуск основного цикла управления...", "CORE")
        
        while True:
            log("Попытка рукопожатия с базой данных...", "TRACE")
            try:
                await init_db()
                log("База данных: ПОДКЛЮЧЕНО", "SUCCESS")
                break
            except Exception as e:
                log(f"БД недоступна, повтор через 5с... ({e})", "WARNING")
                await asyncio.sleep(5)

        # Веб-сервер запускается в фоне
        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                if not await self.update_config_from_db():
                    self.last_status = "WAITING_CONFIG"
                    log("Ожидание мнемоники/AI ключа в базе данных...", "WARNING")
                    await asyncio.sleep(10)
                    continue

                log("Подключение к LiteClient...", "TRACE")
                client = LiteClient.from_mainnet_config()
                await client.start()
                
                try:
                    wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                    log(f"Кошелек активен: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        # Каждую итерацию проверяем, не изменились ли настройки в БД
                        await self.update_config_from_db()
                        
                        market_state = await get_market_state()
                        p_curr = market_state['current_metrics']['price_ton']
                        
                        # Накопление истории цен
                        self.synaptic_history.append({"price": p_curr, "time": time.time()})
                        if len(self.synaptic_history) > 500: self.synaptic_history.pop(0)

                        balance_nano = await wallet.get_balance()
                        balance = balance_nano / 1e9
                        log(f"Баланс: {balance:.2f} TON | Цена: {p_curr:.4f}", "INFO")

                        # Запрос стратегии у AI
                        plan = await self.fetch_neural_strategy(market_state)
                        
                        # Если AI решил покупать и хватает баланса
                        if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 0.5):
                            if await self.dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state['current_metrics'])
                        
                        await asyncio.sleep(20)

                finally:
                    log("Завершение сессии LiteClient", "TRACE")
                    await client.stop()

            except Exception as e:
                log(f"ОШИБКА ЦИКЛА: {e}", "ERROR")
                traceback.print_exc()
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    try:
        asyncio.run(overlord.core_loop())
    except KeyboardInterrupt:
        log("Остановка по запросу пользователя (SIGINT)", "WARNING")
    except Exception as fatal:
        log(f"KERNEL PANIC (Критический сбой): {fatal}", "ERROR")
        traceback.print_exc()

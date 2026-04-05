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

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",    # Red
        "CORE": "\033[95m",    # Magenta
        "TRACE": "\033[90m"     # Grey
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ ---
log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    # Пытаемся найти метод создания ячейки (совместимость версий)
    try:
        from pytoniq import begin_cell as BeginCell
        log("TON: Используется метод begin_cell", "SUCCESS")
    except ImportError:
        try:
            from pytoniq_core import BeginCell
            log("TON: Используется BeginCell из pytoniq_core", "SUCCESS")
        except ImportError:
            from pytoniq import BeginCell
            log("TON: Используется BeginCell из pytoniq", "SUCCESS")
    log("Зависимости TON: OK", "SUCCESS")
except ImportError:
    log("Критическая ошибка: pytoniq не найден! Проверьте requirements.txt", "ERROR")
    sys.exit(1)

# Импорт базы данных
try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Модули базы данных: OK", "SUCCESS")
except ImportError:
    log("Файл database.py не найден в корневой директории!", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.pool_addr = None
        # Твой актуальный адрес кошелька (очищенный)
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        log(f"Overlord initialized. Core ID: {self.core_id}", "CORE")

    def _clean_string(self, text):
        """Удаляет все не-ASCII символы и лишние пробелы."""
        if not text: return ""
        return "".join(char for char in str(text) if ord(char) < 128).strip()

    async def update_config_from_db(self):
        """Синхронизация локальных переменных с БД и очистка от мусора."""
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                # Жесткая очистка мнемоники и ключей от скрытых символов
                self.mnemonic = self._clean_string(cfg.get('mnemonic')).replace('\n', ' ').replace('\r', '')
                self.ai_key = self._clean_string(cfg.get('ai_api_key', ''))
                
                pool_raw = self._clean_string(cfg.get('dedust_pool'))
                if pool_raw: 
                    try:
                        self.pool_addr = Address(pool_raw)
                    except Exception as addr_err:
                        log(f"Ошибка формата адреса пула: {addr_err}", "WARNING")
                
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                self.last_status = "ACTIVE"
                return True
            return False
        except Exception as e:
            log(f"Ошибка синхронизации конфига: {e}", "ERROR")
            return False

    # --- API & WEB ---
    async def handle_index(self, request):
        if os.path.exists('./static/index.html'):
            return web.FileResponse('./static/index.html')
        return web.Response(text="<h1 style='color:magenta'>QUANTUM CORE ACTIVE</h1>", content_type='text/html')

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

    # --- ANALYTICS & NEURAL ---
    def _calculate_hyper_analytics(self):
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
        if not self.ai_key: 
            return {"cmd": "WAIT", "reason": "No AI Key"}
        
        try:
            hyper = self._calculate_hyper_analytics()
            openai.api_key = self.ai_key
            
            # Универсальный вызов OpenAI
            res = await asyncio.wait_for(openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                    {"role": "user", "content": json.dumps({"market": market_snapshot, "hyper": hyper})}
                ]
            ), timeout=15)
            
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            log(f"Ошибка нейросети: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: 
            log("Транзакция отменена: не задан адрес пула", "WARNING")
            return False
        try:
            amt = float(plan.get('amt', 0))
            if amt <= 0: return False
            
            nano_amt = int(amt * 1e9)
            
            # Формирование полезной нагрузки для свопа
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) 
                            .store_uint(int(time.time() + 300), 64) 
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            # Отправка транзакции на твой vault_ton
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=swap_payload)
            self.total_ops += 1
            log(f"TON: Импульс успешно отправлен. Оп #{self.total_ops} | Сумма: {amt}", "SUCCESS")
            return True
        except Exception as e:
            log(f"TON: Ошибка импульса: {e}", "ERROR")
            return False

    # --- RUNNERS ---
    async def start_web_server(self):
        try:
            app = web.Application()
            cors = aiohttp_cors.setup(app, defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_headers="*",
                    allow_credentials=True,
                    expose_headers="*",
                    allow_methods="*"
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
            log(f"Веб-панель QUANTUM ONLINE (Порт {port})", "SUCCESS")
        except Exception as e:
            log(f"Ошибка запуска веб-сервера: {e}", "ERROR")

    async def core_loop(self):
        log("Вход в основной цикл ядра...", "CORE")
        
        # Проверка БД
        while True:
            try:
                await init_db()
                log("База данных подключена, таблицы проверены", "SUCCESS")
                break
            except Exception as e:
                log(f"Ожидание подключения к БД... ({e})", "WARNING")
                await asyncio.sleep(5)

        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                # Синхронизация данных
                if not await self.update_config_from_db():
                    self.last_status = "WAITING_CONFIG"
                    log("Ожидание мнемоники/AI ключа в базе данных...", "WARNING")
                    await asyncio.sleep(10)
                    continue

                client = LiteClient.from_mainnet_config()
                await client.start()
                
                try:
                    # Валидация мнемоники (список из 12-24 слов)
                    mnemonic_list = self.mnemonic.split()
                    if len(mnemonic_list) < 12:
                        log("Ошибка: Мнемоника в БД должна содержать 12 или 24 слова!", "ERROR")
                        await asyncio.sleep(30)
                        continue

                    wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                    log(f"Кошелек активен: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        # 1. Свежий конфиг
                        await self.update_config_from_db()
                        
                        # 2. Данные рынка
                        market_state = await get_market_state()
                        p_curr = market_state['current_metrics']['price_ton']
                        self.synaptic_history.append({"price": p_curr, "time": time.time()})
                        if len(self.synaptic_history) > 500: self.synaptic_history.pop(0)

                        # 3. Баланс
                        balance_nano = await wallet.get_balance()
                        balance = balance_nano / 1e9
                        log(f"Баланс: {balance:.2f} TON | Цена: {p_curr:.4f}", "INFO")

                        # 4. Решение ИИ
                        plan = await self.fetch_neural_strategy(market_state)
                        
                        # 5. Исполнение
                        if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 0.5):
                            if await self.dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state['current_metrics'])
                        
                        await asyncio.sleep(20)

                finally:
                    await client.stop()

            except Exception as e:
                log(f"Ошибка ядра: {e}", "ERROR")
                traceback.print_exc()
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    try:
        asyncio.run(overlord.core_loop())
    except KeyboardInterrupt:
        log("Работа завершена пользователем", "WARNING")
    except Exception as fatal:
        log(f"Критический сбой системы: {fatal}", "ERROR")
        traceback.print_exc()

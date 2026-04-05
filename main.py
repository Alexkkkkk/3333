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
        "TRACE": "\033[90m"     # Gray (для детальных шагов)
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    # flush=True гарантирует, что лог появится в панели Bothost мгновенно
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM <<<", "CORE")

# --- ПОШАГОВЫЙ ИМПОРТ И ПРОВЕРКА ЗАВИСИМОСТЕЙ ---
log("Шаг 1: Загрузка переменных окружения (.env)...", "TRACE")
load_dotenv()

log("Шаг 2: Импорт библиотек TON (pytoniq)...", "TRACE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    try:
        from pytoniq_core import BeginCell
    except ImportError:
        from pytoniq import BeginCell
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
        """Синхронизация с БД с детальным логированием состояния."""
        log("Синхронизация конфигурации из БД...", "TRACE")
        try:
            cfg = await load_remote_config()
            if not cfg:
                log("Конфигурация в БД отсутствует (таблица пуста)!", "WARNING")
                return False
            
            # Проверка ключей (логируем только факт наличия)
            m_status = "SET" if cfg.get('mnemonic') else "MISSING"
            a_status = "SET" if cfg.get('ai_api_key') else "MISSING"
            log(f"Статус данных: Мнемоника={m_status}, AI_Key={a_status}", "INFO")

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

    # --- API & WEB ---
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

    # --- RUNNERS ---
    async def start_web_server(self):
        log(f"Запуск Web-сервера на порту {os.getenv('PORT', 3000)}...", "TRACE")
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
                log("Папка /static успешно подключена", "TRACE")

            for route in list(app.router.routes()):
                cors.add(route)
            
            runner = web.AppRunner(app)
            await runner.setup()
            port = int(os.getenv("PORT", 3000))
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            log(f"Web Dashboard ONLINE (Порт {port})", "SUCCESS")
        except Exception as e:
            log(f"Ошибка запуска Web-сервера: {e}", "ERROR")

    async def core_loop(self):
        log("Запуск основного цикла управления...", "CORE")
        
        # Ожидание базы данных
        while True:
            log("Попытка рукопожатия с базой данных...", "TRACE")
            try:
                await init_db()
                log("База данных: ПОДКЛЮЧЕНО", "SUCCESS")
                break
            except Exception as e:
                log(f"БД недоступна, повтор через 5с... ({e})", "WARNING")
                await asyncio.sleep(5)

        # Запуск веба в фоновой задаче
        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                log("Цикл: Обновление состояния...", "TRACE")
                if not await self.update_config_from_db():
                    self.last_status = "WAITING_CONFIG"
                    log("Ожидание мнемоники/ключа в базе данных...", "WARNING")
                    await asyncio.sleep(10)
                    continue

                log("Подключение к LiteClient Mainnet...", "TRACE")
                client = LiteClient.from_mainnet_config()
                await client.start()
                
                try:
                    log("Инициализация кошелька из мнемоники...", "TRACE")
                    mnemonic_list = self.mnemonic.split()
                    if len(mnemonic_list) < 12:
                        log(f"Критически короткая мнемоника ({len(mnemonic_list)} слов)!", "ERROR")
                        await asyncio.sleep(10)
                        continue

                    wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                    log(f"КОШЕЛЕК АКТИВЕН: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        log("--- Начало итерации анализа ---", "TRACE")
                        await self.update_config_from_db()
                        
                        market_state = await get_market_state()
                        p_curr = market_state['current_metrics']['price_ton']
                        
                        balance_nano = await wallet.get_balance()
                        balance = balance_nano / 1e9
                        log(f"Баланс: {balance:.2f} TON | Цена: {p_curr:.4f}", "INFO")

                        # (Тут логика принятия решения AI...)
                        
                        log("Итерация завершена, сон 20с...", "TRACE")
                        await asyncio.sleep(20)

                finally:
                    log("Закрытие сессии LiteClient...", "TRACE")
                    await client.stop()

            except Exception as e:
                log(f"ОШИБКА ЦИКЛА ЯДРА: {e}", "ERROR")
                traceback.print_exc()
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    try:
        asyncio.run(overlord.core_loop())
    except KeyboardInterrupt:
        log("Запрошена остановка системы", "WARNING")
    except Exception as fatal:
        log(f"KERNEL PANIC (Критический сбой): {fatal}", "ERROR")
        traceback.print_exc()

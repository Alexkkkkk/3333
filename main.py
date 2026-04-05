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
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARNING": "\033[93m", "ERROR": "\033[91m", "CORE": "\033[95m", "TRACE": "\033[90m"}
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM <<<", "CORE")

# --- ШАГ 1: ENV ---
load_dotenv()

# --- ШАГ 2: ИСПРАВЛЕННЫЙ ИМПОРТ TON ---
log("Шаг 2: Импорт библиотек TON...", "TRACE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    try:
        # Пробуем импортировать из нового пакета pytoniq-core
        from pytoniq_core import BeginCell
        log("BeginCell загружен из pytoniq_core", "SUCCESS")
    except ImportError:
        # Если не вышло, пробуем из основного
        from pytoniq import BeginCell
        log("BeginCell загружен из pytoniq", "SUCCESS")
except Exception as e:
    log(f"КРИТИЧЕСКАЯ ОШИБКА ИМПОРТА: {e}", "ERROR")
    sys.exit(1)

# --- ШАГ 3: DATABASE ---
try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Модули базы данных: OK", "SUCCESS")
except Exception as e:
    log(f"ОШИБКА database.py: {e}", "ERROR")
    sys.exit(1)

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        self.pool_addr = None
        self.vault_ton = Address("EQCt0-Ba6Y_9_6p20tH_E_Oq_H_O_O_O_O_O_O_O_O_O_O_O_O")
        self.mnemonic = None
        self.ai_key = None
        self.synaptic_history = []
        self.last_status = "BOOTING"
        self.total_ops = 0
        log(f"Ядро создано. ID: {self.core_id}", "CORE")

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                self.mnemonic = cfg.get('mnemonic').strip().replace('\n', ' ').replace('\r', '')
                self.ai_key = cfg.get('ai_api_key', '').strip()
                if cfg.get('dedust_pool'):
                    self.pool_addr = Address(cfg.get('dedust_pool'))
                self.last_status = "ACTIVE"
                return True
            return False
        except Exception as e:
            log(f"Ошибка конфига: {e}", "ERROR")
            return False

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT"}
        try:
            openai.api_key = self.ai_key
            # Совместимость с openai==0.28.1
            res = await asyncio.wait_for(openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float}"},
                    {"role": "user", "content": json.dumps(market_snapshot)}
                ]
            ), timeout=15)
            return json.loads(res.choices[0].message.content)
        except:
            return {"cmd": "WAIT"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: return False
        try:
            amt = float(plan.get('amt', 0))
            nano_amt = int(amt * 1e9)
            payload = (BeginCell()
                       .store_uint(0xea06185d, 32) 
                       .store_uint(int(time.time() + 300), 64) 
                       .store_coins(nano_amt)
                       .store_address(self.pool_addr)
                       .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=payload)
            self.total_ops += 1
            log(f"Транзакция отправлена! Сумма: {amt} TON", "SUCCESS")
            return True
        except Exception as e:
            log(f"Ошибка транзакции: {e}", "ERROR")
            return False

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*", allow_methods="*")})
        app.router.add_get('/', lambda r: web.FileResponse('./static/index.html') if os.path.exists('./static/index.html') else web.Response(text="Core Active"))
        app.router.add_get('/api/stats', lambda r: web.json_response({"core_id": self.core_id, "ops": self.total_ops}))
        
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 3000))).start()
        log("Web-сервер запущен", "SUCCESS")

    async def core_loop(self):
        await init_db()
        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                if not await self.update_config_from_db():
                    log("Жду настройки в БД...", "WARNING")
                    await asyncio.sleep(10); continue

                client = LiteClient.from_mainnet_config()
                await client.start()
                
                try:
                    wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                    log(f"Кошелек: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        market_state = await get_market_state()
                        balance = (await wallet.get_balance()) / 1e9
                        log(f"Баланс: {balance:.2f} TON", "INFO")

                        plan = await self.fetch_neural_strategy(market_state)
                        if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 0.5):
                            await self.dispatch_hft_pulse(wallet, plan)
                        
                        await asyncio.sleep(20)
                finally:
                    await client.stop()
            except Exception as e:
                log(f"Ошибка цикла: {e}", "ERROR")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(OmniNeuralOverlord().core_loop())

import asyncio
import os
import json
import time
import openai
import sys
import numpy as np
import traceback
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
import aiohttp_cors

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", "ERROR": "\033[91m", 
        "CORE": "\033[95m", "TRACE": "\033[90m"
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM <<<", "CORE")
load_dotenv()

# --- УЛЬТРА-ГИБКИЙ ИМПОРТ TON ---
log("Шаг 2: Импорт библиотек TON...", "TRACE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    try:
        from pytoniq import begin_cell
        log("Метод begin_cell готов (pytoniq native)", "SUCCESS")
    except ImportError:
        try:
            from pytoniq_core import begin_cell
            log("Метод begin_cell готов (from pytoniq_core)", "SUCCESS")
        except ImportError:
            from pytoniq import BeginCell as begin_cell
            log("Используется резервный BeginCell", "WARNING")
            
except Exception as e:
    log(f"КРИТИЧЕСКАЯ ОШИБКА ТОН: {e}", "ERROR")
    sys.exit(1)

# Импорт базы данных
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
        
        # ВСТАВЛЕН ВАШ АДРЕС
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
            
        self.mnemonic = None
        self.ai_key = None
        self.total_ops = 0
        self.last_status = "BOOTING"

    async def update_config(self):
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                self.mnemonic = cfg.get('mnemonic').strip()
                self.ai_key = cfg.get('ai_api_key', '').strip()
                if cfg.get('dedust_pool'):
                    self.pool_addr = Address(cfg.get('dedust_pool'))
                return True
            return False
        except Exception as e:
            log(f"Ошибка конфига: {e}", "ERROR")
            return False

    async def fetch_strategy(self, market):
        if not self.ai_key: return {"cmd": "WAIT"}
        try:
            openai.api_key = self.ai_key
            res = await asyncio.wait_for(openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\", \"amt\": 1.0}"},
                    {"role": "user", "content": json.dumps(market)}
                ]
            ), timeout=15)
            return json.loads(res.choices[0].message.content)
        except: return {"cmd": "WAIT"}

    async def send_transaction(self, wallet, plan):
        if not self.pool_addr or not self.vault_ton: 
            log("Пропуск: адрес хранилища или пула не задан", "WARNING")
            return False
        try:
            amt = float(plan.get('amt', 0))
            nano_amt = int(amt * 1e9)
            
            payload = (begin_cell()
                       .store_uint(0xea06185d, 32) 
                       .store_uint(int(time.time() + 300), 64) 
                       .store_coins(nano_amt)
                       .store_address(self.pool_addr)
                       .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=payload)
            self.total_ops += 1
            log(f"Сделка #{self.total_ops} отправлена на {self.vault_ton}", "SUCCESS")
            return True
        except Exception as e:
            log(f"Ошибка транзакции: {e}", "ERROR")
            return False

    async def start_web(self):
        try:
            app = web.Application()
            cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*", allow_methods="*")})
            app.router.add_get('/', lambda r: web.FileResponse('./static/index.html') if os.path.exists('./static/index.html') else web.Response(text="Quantum Active"))
            app.router.add_get('/api/stats', lambda r: web.json_response({"ops": self.total_ops, "uptime": int(time.time()-self.session_start)}))
            
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 3000))).start()
            log("API Dashboard запущен на порту 3000", "SUCCESS")
        except Exception as e:
            log(f"Ошибка веб-сервера: {e}", "ERROR")

    async def run(self):
        await init_db()
        asyncio.create_task(self.start_web())
        
        while self.is_active:
            try:
                if not await self.update_config():
                    log("Ожидание настроек в БД...", "WARNING")
                    await asyncio.sleep(10); continue

                client = LiteClient.from_mainnet_config()
                await client.start()
                try:
                    mnemonic_list = self.mnemonic.split()
                    if len(mnemonic_list) < 12:
                        log("Ошибка: неверный формат мнемоники в БД!", "ERROR")
                        await asyncio.sleep(30); continue
                        
                    wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                    log(f"Кошелек активен: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        market = await get_market_state()
                        plan = await self.fetch_strategy(market)
                        if plan.get('cmd') == "BUY":
                            await self.send_transaction(wallet, plan)
                        await asyncio.sleep(30)
                finally:
                    await client.stop()
            except Exception as e:
                log(f"Рестарт цикла: {e}", "ERROR")
                await asyncio.sleep(10)

if __name__ == "__main__":
    bot = OmniNeuralOverlord()
    asyncio.run(bot.run())

import asyncio
import os
import json
import time
import openai
import sys
import random
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
import aiohttp_cors

# Блок TON библиотек
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
# Твои локальные модули (database.py должен быть в той же папке)
from database import init_db, log_ai_action, get_market_state, get_stats_for_web, get_pool

# Загрузка конфигурации
load_dotenv()
openai.api_key = os.getenv("AI_API_KEY")

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Конфигурация из .env
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))
        self.strategy_level = int(os.getenv('AI_STRATEGY_LEVEL', 10))
        
        # ДНК Системы (Аналитические коэффициенты)
        self.dna = {
            "market_pressure": 0.99,
            "stealth_mode": 0.94,
            "floor_protection": 0.88,
            "gas_strategy": "HYPER_FAST"
        }
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.backlog = asyncio.Queue()

    # --- МАТЕМАТИЧЕСКИЙ ДВИЖОК (Ultra-Analytics) ---
    def _calculate_quantum_signals(self):
        if len(self.synaptic_history) < 5: return None
        
        prices = [h['price'] for h in self.synaptic_history]
        current_price = prices[-1]
        
        # Расчет скользящей средней и отклонения
        sma = np.mean(prices[-10:]) if len(prices) >= 10 else np.mean(prices)
        std_dev = np.std(prices) if len(prices) > 1 else 0.001
        
        # Импульс за последние 5 тактов
        momentum = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
        
        # Индикатор перепроданности (Z-Score < -1.5)
        is_oversold = current_price < (sma - 1.5 * std_dev)
        
        return {
            "sma": round(float(sma), 8),
            "volatility": round(float(std_dev / sma), 4) if sma != 0 else 0,
            "momentum_pct": round(float(momentum * 100), 2),
            "is_oversold": is_oversold,
            "z_score": round(float((current_price - sma) / std_dev), 2) if std_dev > 0 else 0
        }

    # --- ИИ ПЛАНИРОВАНИЕ ---
    async def fetch_neural_strategy(self, market_snapshot):
        signals = self._calculate_quantum_signals()
        
        # Формируем контекст для ИИ-Архитектора
        prompt = {
            "core_id": self.core_id,
            "aggression": self.strategy_level,
            "market_data": market_snapshot['current_metrics'],
            "quantum_signals": signals,
            "recent_actions": market_snapshot.get('recent_memory', []),
            "mission": "Defend the floor, stimulate organic growth, maintain high liquidity."
        }

        try:
            res = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are OMNI-SENTINEL. High-speed TON Market Maker. Logic: BUY/PUMP/SHIELD/WAIT. Output JSON ONLY."},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.3
            )
            logic = json.loads(res.choices[0].message.content)
            
            # Валидация и лимиты (Safety First)
            return {
                "cmd": str(logic.get("cmd", "WAIT")).upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0), # Лимит 50 TON на операцию
                "delay": max(int(logic.get("delay", 30)), 10),
                "urgency": max(min(int(logic.get("urgency", 1)), 5), 1),
                "reason": str(logic.get("reason", "Recalibrating synapse..."))
            }
        except Exception as e:
            return {"cmd": "WAIT", "amt": 0, "delay": 45, "reason": f"Neural Link Error: {e}"}

    # --- ИСПОЛНЕНИЕ ТРАНЗАКЦИЙ (DeDust V2 Protocol) ---
    async def dispatch_hft_pulse(self, wallet, plan, market):
        amt = plan['amt']
        urgency = plan['urgency']
        
        # Конвертация в нано-единицы и расчет газа
        nano_amt = int(amt * 1e9)
        adjusted_gas = int(0.25e9 + (urgency * 0.03e9))

        # Payload для свопа TON -> Jetton на DeDust
        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32) # Op-code для swap
                        .store_uint(int(time.time() + 180), 64) # Deadline
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1)
                        .store_coins(0) # Limit
                        .store_maybe_ref(None)
                        .end_cell())
        try:
            # Stealth-модификатор: небольшая случайная разница в сумме (до 3%)
            jitter_amt = int(nano_amt * (1 + random.uniform(-0.03, 0.03)))
            
            await asyncio.wait_for(
                wallet.transfer(
                    destination=self.vault_ton,
                    amount=jitter_amt + adjusted_gas,
                    body=swap_payload
                ), timeout=30.0
            )
            
            self.total_ops += 1
            self.last_status = f"EXECUTED_{plan['cmd']}"
            
            # Сохраняем цену в историю для квантовых сигналов
            price = market.get('current_metrics', {}).get('price_ton', 0)
            self.synaptic_history.append({"price": price, "time": time.time()})
            return True
        except Exception as e:
            self.last_status = "TX_FAILED"
            print(f"\n🚨 [TX_ERROR]: {e}")
            return False

    # --- WEB HANDLERS ---
    async def handle_get_stats(self, request):
        stats = await get_stats_for_web()
        return web.json_response(stats)

    async def handle_update_settings(self, request):
        try:
            data = await request.json()
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute('''
                    UPDATE distribution_settings 
                    SET holders_pct = $1, staking_pct = $2, liquidity_pct = $3, treasury_pct = $4, updated_at = NOW()
                    WHERE label = 'default'
                ''', float(data['holders'])/100, float(data['staking'])/100, 
                     float(data['liquidity'])/100, float(data['treasury'])/100)
            return web.json_response({"status": "ok"})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)})

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
        })
        
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/settings', self.handle_update_settings)
        # Статика (интерфейс админки)
        if os.path.exists('static'):
            app.router.add_static('/', path='static', name='static')
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv('PORT', 3000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"\033[94m🌐 [WEB] Админка: http://localhost:{port}\033[0m")

    # --- BACKGROUND WORKERS ---
    async def telemetry_worker(self):
        """Асинхронная запись логов в БД, чтобы не тормозить цикл трейдинга."""
        while self.is_active:
            task = await self.backlog.get()
            try:
                await log_ai_action(task['strategy'], task['market'])
            except:
                pass
            finally:
                self.backlog.task_done()

    # --- MAIN LOOP ---
    async def core_loop(self):
        await init_db()
        asyncio.create_task(self.telemetry_worker())
        await self.start_web_server()

        # Инициализация клиента TON
        client = LiteClient.from_mainnet_config()
        await client.start()
        
        mnemonic = os.getenv('MNEMONIC').split()
        wallet = await WalletV4R2.from_mnemonic(client, mnemonic)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\033[95m--- 🌀 OMNI NEURAL CORE V20 : ACTIVATED ---\033[0m")
        print(f"Core ID: {self.core_id} | Mode: {self.dna['gas_strategy']}")

        while self.is_active:
            try:
                # 1. Получаем состояние рынка и баланс
                market = await get_market_state()
                balance = (await wallet.get_balance()) / 1e9
                
                # Обновляем UI в консоли
                sys.stdout.write(f"\r\033[96m[ BAL: {balance:.2f} TON | OPS: {self.total_ops} | STATUS: {self.last_status} ]\033[0m")
                sys.stdout.flush()

                # 2. ИИ принимает решение
                plan = await self.fetch_neural_strategy(market)
                
                # 3. Проверка условий и исполнение
                if plan['cmd'] in ["BUY", "PUMP", "SHIELD"] and balance > (plan['amt'] + 3.0):
                    success = await self.dispatch_hft_pulse(wallet, plan, market)
                    if success:
                        await self.backlog.put({"strategy": plan, "market": market})
                else:
                    # Даже если ждем, логируем состояние ожидания
                    if random.random() < 0.1: # Логируем WAIT только в 10% случаев, чтобы не забивать БД
                        await self.backlog.put({"strategy": plan, "market": market})

                # 4. Динамическая задержка
                wait_time = max(10, plan['delay'] + random.randint(-5, 15))
                await asyncio.sleep(wait_time)

            except Exception as e:
                self.last_status = "ERROR_LOOP"
                await asyncio.sleep(20)

if __name__ == "__main__":
    omni_node = OmniNeuralOverlord()
    try:
        asyncio.run(omni_node.core_loop())
    except KeyboardInterrupt:
        print("\033[91m\n🔌 Система деактивирована пользователем.\033[0m")

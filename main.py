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
# Твои локальные модули
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

    # --- THE SINGULARITY ENGINE (Hyper-Analytics) ---
    def _calculate_hyper_analytics(self):
        """Квантовая психометрия: FEI, Entropy и Gravity Price."""
        if len(self.synaptic_history) < 20: return None
        
        prices = np.array([h['price'] for h in self.synaptic_history])
        curr = prices[-1]
        
        # 1. Fractal Efficiency Index (FEI) - Истинный тренд vs Шум
        path_length = np.sum(np.abs(np.diff(prices)))
        radial_dist = np.abs(prices[-1] - prices[0])
        fei = radial_dist / path_length if path_length > 0 else 0

        # 2. Entropy Cluster (Volatility Compression)
        returns = np.diff(np.log(prices))
        # Сжатие волатильности часто предшествует взрыву
        vol_compression = np.std(returns[-5:]) / np.std(returns) if len(returns) > 5 else 1
        
        # 3. Z-Score (Статистическое отклонение)
        sma = np.mean(prices[-15:])
        std_dev = np.std(prices)
        z_score = (curr - sma) / std_dev if std_dev > 0 else 0

        # 4. Gravity Price (Средневзвешенный магнит ликвидности)
        # Придаем больший вес последним ценам
        weights = np.linspace(0.1, 1.0, len(prices))
        gravity = np.average(prices, weights=weights)

        # 5. Fair Value Gap (FVG)
        fvg_active = False
        if len(prices) >= 3:
            p1, p2, p3 = prices[-3], prices[-2], prices[-1]
            if p3 > p1 * 1.015: fvg_active = True

        return {
            "fractal_efficiency": round(float(fei), 4),
            "market_state": "TRENDING" if fei > 0.5 else "RANGING",
            "explosion_risk": "HIGH" if vol_compression < 0.4 else "STABLE",
            "gravity_price": round(float(gravity), 8),
            "z_score": round(float(z_score), 2),
            "fvg_active": fvg_active,
            "neural_confidence": round(float(fei * 100), 2)
        }

    # --- ИИ ПЛАНИРОВАНИЕ ---
    async def fetch_neural_strategy(self, market_snapshot):
        hyper = self._calculate_hyper_analytics()
        
        prompt = {
            "core_id": self.core_id,
            "market_metrics": market_snapshot['current_metrics'],
            "singularity_data": hyper,
            "recent_memory": market_snapshot.get('recent_memory', []),
            "mission": "Execute hyper-precise entry. Exploit market imbalances."
        }

        try:
            res = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": (
                        "You are OMNI-SINGULARITY. You see the market as a mathematical construct. "
                        "CMD: BUY/PUMP/SHIELD/WAIT. "
                        "If explosion_risk is HIGH, prepare for rapid movement. "
                        "If fractal_efficiency is low, avoid overtrading. Output JSON ONLY."
                    )},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.15 # Максимальная точность
            )
            logic = json.loads(res.choices[0].message.content)
            
            return {
                "cmd": str(logic.get("cmd", "WAIT")).upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0),
                "delay": max(int(logic.get("delay", 20)), 10),
                "urgency": max(min(int(logic.get("urgency", 1)), 5), 1),
                "reason": str(logic.get("reason", "Recalibrating fractal link")),
                "confidence": logic.get("confidence_pct", 0)
            }
        except Exception as e:
            return {"cmd": "WAIT", "amt": 0, "delay": 30, "reason": f"Neural Lag: {e}"}

    # --- ИСПОЛНЕНИЕ ТРАНЗАКЦИЙ ---
    async def dispatch_hft_pulse(self, wallet, plan, market):
        amt = plan['amt']
        urgency = plan['urgency']
        nano_amt = int(amt * 1e9)
        adjusted_gas = int(0.25e9 + (urgency * 0.03e9))

        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32)
                        .store_uint(int(time.time() + 150), 64)
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1)
                        .store_coins(0)
                        .store_maybe_ref(None)
                        .end_cell())
        try:
            # Stealth: Случайное изменение суммы на +-1.5%
            jitter = int(nano_amt * (1 + random.uniform(-0.015, 0.015)))
            await asyncio.wait_for(
                wallet.transfer(
                    destination=self.vault_ton,
                    amount=jitter + adjusted_gas,
                    body=swap_payload
                ), timeout=25.0
            )
            
            self.total_ops += 1
            self.last_status = f"SINGULARITY_{plan['cmd']}"
            
            price = market.get('current_metrics', {}).get('price_ton', 0)
            self.synaptic_history.append({"price": price, "time": time.time()})
            return True
        except Exception as e:
            self.last_status = "PULSE_ERROR"
            print(f"\n🚨 [CRITICAL]: {e}")
            return False

    # --- WEB & WORKERS (Стабильные модули) ---
    async def handle_get_stats(self, request):
        return web.json_response(await get_stats_for_web())

    async def handle_update_settings(self, request):
        try:
            data = await request.json()
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute('''
                    UPDATE distribution_settings SET holders_pct=$1, staking_pct=$2, 
                    liquidity_pct=$3, treasury_pct=$4 WHERE label='default'
                ''', float(data['holders'])/100, float(data['staking'])/100, 
                     float(data['liquidity'])/100, float(data['treasury'])/100)
            return web.json_response({"status": "ok"})
        except: return web.json_response({"status": "error"})

    async def start_web_server(self):
        app = web.Application()
        aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*")})
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/settings', self.handle_update_settings)
        if os.path.exists('static'): app.router.add_static('/', path='static', name='static')
        runner = web.AppRunner(app); await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 3000))).start()
        print(f"\033[94m🌐 [WEB] Singularity Terminal: http://localhost:3000\033[0m")

    async def telemetry_worker(self):
        while self.is_active:
            task = await self.backlog.get()
            try: await log_ai_action(task['strategy'], task['market'])
            except: pass
            finally: self.backlog.task_done()

    # --- CORE LOOP ---
    async def core_loop(self):
        await init_db()
        asyncio.create_task(self.telemetry_worker())
        await self.start_web_server()

        client = LiteClient.from_mainnet_config(); await client.start()
        wallet = await WalletV4R2.from_mnemonic(client, os.getenv('MNEMONIC').split())
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\033[95m--- 🌀 OMNI NEURAL CORE V99 : SINGULARITY ACTIVATED ---\033[0m")

        while self.is_active:
            try:
                market = await get_market_state()
                balance = (await wallet.get_balance()) / 1e9
                
                sys.stdout.write(f"\r\033[96m[ BAL: {balance:.2f} | OPS: {self.total_ops} | STATUS: {self.last_status} ]\033[0m")
                sys.stdout.flush()

                plan = await self.fetch_neural_strategy(market)
                
                if plan['cmd'] in ["BUY", "PUMP", "SHIELD"] and balance > (plan['amt'] + 3.0):
                    if await self.dispatch_hft_pulse(wallet, plan, market):
                        await self.backlog.put({"strategy": plan, "market": market})
                else:
                    if random.random() < 0.2: # Логируем важные аналитические циклы
                        await self.backlog.put({"strategy": plan, "market": market})

                await asyncio.sleep(max(5, plan['delay'] + random.randint(-2, 5)))

            except Exception as e:
                self.last_status = "RECALIBRATING"
                await asyncio.sleep(10)

if __name__ == "__main__":
    try: asyncio.run(OmniNeuralOverlord().core_loop())
    except KeyboardInterrupt: print("\033[91m\n🔌 Singularity Offline.\033[0m")

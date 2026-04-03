import asyncio
import os
import random
import json
import time
import openai
from dotenv import load_dotenv
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
# Импорт твоих функций из database.py
from database import init_db, log_ai_action, get_market_state

# Загрузка окружения
load_dotenv()
openai.api_key = os.getenv("AI_API_KEY")

class OmniNeuralDeDust:
    def __init__(self):
        self.is_active = True
        # Конфигурация из твоего .env
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))
        self.strategy_level = int(os.getenv('AI_STRATEGY_LEVEL', 10))
        
        # Базовые параметры экономики (в нанотонах)
        self.gas_fee = int(0.22 * 1e9) 
        self.last_status = "INITIALIZING"
        self.total_operations = 0

    async def fetch_neural_strategy(self, market_snapshot):
        """
        Deep Analysis Layer: ИИ анализирует 'психологию' и метрики рынка.
        """
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Промпт для ИИ-архитектора с учетом уровня агрессии
        neural_prompt = (
            f"SYSTEM_TIME: {current_time}\n"
            f"LAST_STATUS: {self.last_status}\n"
            f"STRATEGY_LEVEL: {self.strategy_level}/10 (10=Max Aggression)\n"
            f"MARKET_SNAPSHOT: {json.dumps(market_snapshot)}\n"
            f"MISSION: Orchestrate high-confidence growth. Protect the floor. Manipulate visual impact.\n"
            f"CONSTRAINTS: Max amount 50 TON. Use JSON only.\n"
            f"FIELDS: 'cmd' (BUY/PUMP/SHIELD/WAIT), 'amt' (float), 'delay' (int), 'urgency' (1-5), 'reason' (string)."
        )

        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are the Omni-Architect of TON. Manage liquidity with surgical precision."},
                    {"role": "user", "content": neural_prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.8
            )
            
            logic = json.loads(response.choices[0].message.content)
            
            # Валидация и жесткие лимиты безопасности
            return {
                "cmd": str(logic.get("cmd", "WAIT")).upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0), 
                "delay": max(int(logic.get("delay", 30)), 15),
                "urgency": max(min(int(logic.get("urgency", 1)), 5), 1),
                "reason": str(logic.get("reason", "Scanning market pulse..."))
            }
        except Exception as e:
            print(f"📡 [NEURAL_LINK_ERROR]: {e}")
            return {"cmd": "WAIT", "amt": 0, "delay": 45, "reason": "Connection unstable"}

    async def dispatch_hft_pulse(self, wallet, plan):
        """
        Hyper-Speed Dispatcher: Прямое исполнение в DeDust V2.
        """
        amount = plan['amt']
        urgency = plan['urgency']
        nano_amt = int(amount * 1e9)
        
        # Динамический газ: чем выше urgency, тем выше приоритет в блоке
        adjusted_gas = self.gas_fee + (urgency * int(0.01 * 1e9))

        # Payload: DeDust V2 Swap (Native TON -> Jetton)
        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32)
                        .store_uint(int(time.time()), 64) 
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1) 
                        .store_coins(0)   
                        .store_maybe_ref(None)
                        .end_cell())

        try:
            print(f"🚀 [DISPATCH] {plan['cmd']} | {amount} TON | Urgency: {urgency}")
            
            await wallet.transfer(
                destination=self.vault_ton,
                amount=nano_amt + adjusted_gas,
                body=swap_payload
            )
            
            self.total_operations += 1
            self.last_status = f"SUCCESS: {plan['cmd']} executed"
            return True
        except Exception as e:
            print(f"⚠️ [PULSE_FAILED]: {e}")
            self.last_status = f"FAILED: {str(e)[:50]}"
            return False

    async def core_loop(self):
        """
        Main Loop: Неубиваемое ядро управления.
        """
        # Подключение к LiteServer (Mainnet)
        client = LiteClient.from_mainnet_config()
        await client.start()
        
        mnemonic = os.getenv('MNEMONIC').split()
        wallet = await WalletV4R2.from_mnemonic(client, mnemonic)
        
        print(f"--- 🌀 OMNI NEURAL CORE ACTIVATED ---")
        print(f"--- WALLET: {wallet.address} ---")
        print(f"--- AGGRESSION LEVEL: {self.strategy_level} ---")

        while self.is_active:
            try:
                # 1. Сбор данных (Память + Рынок)
                market_snapshot = await get_market_state()
                
                # 2. Нейронное планирование
                strategy = await self.fetch_neural_strategy(market_snapshot)
                
                # 3. Визуализация в консоли
                print(f"🤖 [DECISION] {strategy['cmd']} >> {strategy['amt']} TON. Reason: {strategy['reason']}")

                # 4. Проверка условий и запуск импульса
                if strategy['cmd'] in ["BUY", "PUMP", "SHIELD"] and strategy['amt'] > 0:
                    success = await self.dispatch_hft_pulse(wallet, strategy)
                    
                    # Фиксация в БД (обучение ИИ)
                    if success:
                        await log_ai_action(strategy, market_snapshot)

                # 5. Адаптивный сон (контролируется ИИ)
                await asyncio.sleep(strategy['delay'])

            except Exception as core_err:
                print(f"🚨 [CORE_CRITICAL_ERROR]: {core_err}")
                self.last_status = "CRITICAL_ERROR"
                await asyncio.sleep(20) # Тайм-аут на самовосстановление

if __name__ == "__main__":
    # Гарантируем готовность базы данных
    asyncio.run(init_db())
    
    # Инициализация Omni-ядра
    omni_node = OmniNeuralDeDust()
    try:
        asyncio.run(omni_node.core_loop())
    except KeyboardInterrupt:
        print("\n🔌 Система штатно отключена. Нейросети деактивированы.")

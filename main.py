import asyncio
import os
import random
import json
import time
import openai
from dotenv import load_dotenv
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
from database import init_db, log_ai_action, get_market_state

# Загрузка нейронных фильтров
load_dotenv()
openai.api_key = os.getenv("AI_API_KEY")

class OmniNeuralDeDust:
    def __init__(self):
        self.is_active = True
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))
        # Газ с запасом для приоритетного включения в блок (High Priority)
        self.gas_fee = int(0.22 * 1e9) 
        self.last_action_time = 0

    async def fetch_neural_strategy(self, market_snapshot):
        """
        Deep Analysis Layer: ИИ оценивает 'психологию' графика.
        """
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Обогащаем промпт для глубокого понимания
        neural_prompt = (
            f"SYSTEM_TIME: {current_time}\n"
            f"MARKET_DATA: {market_snapshot}\n"
            f"MISSION: Orchestrate a high-confidence growth trajectory. Avoid predictable patterns.\n"
            f"CONSTRAINTS: Minimize slippage, maximize visual impact on candles.\n"
            f"OUTPUT_FORMAT: JSON only.\n"
            f"REQUIRED_KEYS: 'cmd' (BUY/PUMP/SHIELD/WAIT), 'amt' (float), 'delay' (int), 'urgency' (1-5), 'reason' (string)."
        )

        try:
            # Используем gpt-4-turbo для сложной логики маркет-мейкинга
            response = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are the Omni-Architect of TON liquidity. Your goal is dominance and stability."},
                    {"role": "user", "content": neural_prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.85 # Высокая креативность для обхода анти-бот систем
            )
            
            logic = json.loads(response.choices[0].message.content)
            
            # Санитарная проверка данных
            return {
                "cmd": logic.get("cmd", "WAIT").upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0), # Лимит безопасности 50 TON за раз
                "delay": max(int(logic.get("delay", 30)), 15),
                "urgency": logic.get("urgency", 1),
                "reason": logic.get("reason", "Analyzing pulse...")
            }
        except Exception as e:
            print(f"📡 [NEURAL_LINK_ERROR]: {e}")
            return {"cmd": "WAIT", "amt": 0, "delay": 60, "reason": "Recovering neural link"}

    async def dispatch_hft_pulse(self, wallet, amount, urgency):
        """
        Hyper-Speed Dispatcher: Исполнение транзакции на уровне ядра.
        """
        nano_amt = int(amount * 1e9)
        # Динамический газ в зависимости от срочности (Urgency)
        adjusted_gas = self.gas_fee + (urgency * int(0.01 * 1e9))

        # Payload: DeDust V2 Native Swap
        # Позволяет менять TON на твой Jetton максимально эффективно
        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32) # DeDust Swap Op
                        .store_uint(int(time.time()), 64) # Unique Query ID
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1) # Type: Swap
                        .store_coins(0)   # Slippage limit: Market
                        .store_maybe_ref(None)
                        .end_cell())

        try:
            # Отправка через Wallet V4R2 (Sequence-цепочка)
            print(f"🚀 [PULSE] Mode: {urgency} | Amount: {amount} TON | Status: DISPATCHING")
            await wallet.transfer(
                destination=self.vault_ton,
                amount=nano_amt + adjusted_gas,
                body=swap_payload
            )
            self.last_action_time = time.time()
            return True
        except Exception as e:
            print(f"⚠️ [PULSE_FAILED]: {e}")
            return False

    async def core_loop(self):
        """
        Main Infinity Loop: Неубиваемый цикл управления.
        """
        # Подключение к LiteServer (рекомендуется использовать надежный endpoint)
        client = LiteClient.from_mainnet_config()
        await client.start()
        
        mnemonic = os.getenv('MNEMONIC').split()
        wallet = await WalletV4R2.from_mnemonic(client, mnemonic)
        
        print(f"--- 🌀 OMNI NEURAL CORE ACTIVATED ---")
        print(f"--- OPERATING WALLET: {wallet.address} ---")

        while self.is_active:
            try:
                # 1. Запрос рыночных метрик (из database.py или API)
                market_snapshot = await get_market_state()
                
                # 2. Получение стратегии от ИИ
                strategy = await self.fetch_neural_strategy(market_snapshot)
                
                # 3. Визуальный контроль в консоли
                print(f"🤖 [DECISION] {strategy['cmd']} >> {strategy['amt']} TON. Reason: {strategy['reason']}")

                # 4. Проверка условий и запуск импульса
                if strategy['cmd'] in ["BUY", "PUMP", "SHIELD"] and strategy['amt'] > 0:
                    success = await self.dispatch_hft_pulse(
                        wallet, 
                        strategy['amt'], 
                        strategy['urgency']
                    )
                    if success:
                        await log_ai_action(strategy)

                # 5. Интеллектуальный сон (адаптивный тайминг)
                await asyncio.sleep(strategy['delay'])

            except Exception as core_err:
                print(f"🚨 [CORE_CRITICAL_ERROR]: {core_err}")
                await asyncio.sleep(20) # Тайм-аут для самовосстановления

if __name__ == "__main__":
    # Гарантированная подготовка инфраструктуры
    asyncio.run(init_db())
    
    # Инициализация и старт
    omni_node = OmniNeuralDeDust()
    try:
        asyncio.run(omni_node.core_loop())
    except KeyboardInterrupt:
        print("\n🔌 Системный выход. Все нейронные связи разорваны.")

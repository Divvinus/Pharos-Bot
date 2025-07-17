import time
import random
from pydantic import ValidationError
from typing import Self, Any

from .config_modules import FaroSwapBaseModule
from src.wallet import Wallet
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import show_trx_log, random_sleep
from bot_loader import config
from configs import (
    MAX_RETRY_ATTEMPTS, 
    RETRY_SLEEP_RANGE,
    SLEEP_SWAP,
    TOKENS_DATA_PHAROS
)


class FaroSwapModule(AsyncLogger, Wallet):
    TASK_MSG = "Swap tokens on FaroSwap"
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(
            self, account.keypair, config.pharos_rpc_endpoints, account.proxy
        )
        AsyncLogger.__init__(self)
        self.account = account
        self.config_swap = None
        self.deadline = int(time.time() + 12 * 3600)
        self.api_client: HTTPClient | None = None
        
    async def __aenter__(self) -> Self:
        self.api_client = HTTPClient(
            "https://api.dodoex.io/route-service/v2",  self.account.proxy
        )
        await self.api_client.__aenter__()
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
        await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
        
    async def check_basic_config(self) -> tuple[bool, str]:
        balance = await self.human_balance()
        if not balance > 0:
            error_msg = "No $PHRS tokens in wallet"
            await self.logger_msg(error_msg, "error", self.wallet_address, "check_basic_config")
            return False, error_msg
        
        try:
            self.config_swap: FaroSwapBaseModule = FaroSwapBaseModule()
        except ValidationError as error:
            error_messages: list[str] = [err["msg"] for err in error.errors()]

            error_msg: str = "\n".join(error_messages)
            await self.logger_msg(
                error_msg,
                "error",
                self.wallet_address,
                "run_swap",
            )
            return False, f"Configuration validation failed: {error_msg}"

        return True, "Config validation passed"
    
    async def get_swap_params(self, from_amount: int, address_token_1: str, address_token_2: str) -> dict[str, Any]:
        """Получение параметров свопа от API DODO"""
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,pt;q=0.6,uk;q=0.5',
            'cache-control': 'no-cache',
            'origin': 'https://faroswap.xyz',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://faroswap.xyz/',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        }
        
        # Конвертация нативного токена для API
        if address_token_1 == "0x0000000000000000000000000000000000000000":
            address_token_1 = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        elif address_token_2 == "0x0000000000000000000000000000000000000000":
            address_token_2 = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        
        params = {
            'chainId': '688688',
            'deadLine': self.deadline,
            'apikey': 'a37546505892e1a952',
            'slippage': round(random.uniform(1, 10), 2),
            'source': 'dodoV2AndMixWasm',
            'toTokenAddress': address_token_2,
            'fromTokenAddress': address_token_1,
            'userAddr': self.wallet_address,
            'estimateGas': 'true' if address_token_2 == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE" else 'false',
            'fromAmount': from_amount,
        }
        
        response = await self.api_client.send_request(
            method="GET",
            endpoint="/widget/getdodoroute",
            params=params,
            headers=headers
        )
        
        # Валидируем ответ
        swap_data = response['data']
        return swap_data['data']
        
    async def swap(
        self, 
        name_token_1: str, 
        name_token_2: str,
        address_token_1: str,
        address_token_2: str,
        amount_in: int
    ) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )  
            try:
                # Получаем параметры свопа от API
                swap_data = await self.get_swap_params(amount_in, address_token_1, address_token_2)
                
                # Approve токен если это не нативный PHRS
                if name_token_1 != "PHRS" and amount_in > 0:
                    # Получаем адрес для approve из API
                    spender_address = swap_data.get('targetApproveAddr', swap_data['to'])
                    status, result = await self._check_and_approve_token(
                        token_address=address_token_1,
                        spender_address=spender_address,
                        amount=amount_in
                    )
                    if not status:
                        return False, result
                
                # Извлекаем предложенный газ из API (если есть)
                api_gas_limit = swap_data.get('gasLimit', '0')
                
                # Преобразуем gasLimit в int, если он есть
                suggested_gas = None
                if api_gas_limit and api_gas_limit != '0':
                    if isinstance(api_gas_limit, str):
                        if api_gas_limit.startswith('0x'):
                            suggested_gas = int(api_gas_limit, 16)
                        else:
                            suggested_gas = int(api_gas_limit)
                    else:
                        suggested_gas = int(api_gas_limit)
                
                tx_params = await self.build_transaction_params(
                    to=swap_data['to'],
                    data=swap_data['data'],
                    value=int(swap_data['value']),
                    gas=suggested_gas,  # Передаём предложенный газ, если есть
                    gas_buffer=1.3 if suggested_gas else 1.5,  # Больший буфер если оцениваем сами
                    gas_price_buffer=1.1
                )
                
                # Отправляем транзакцию
                status, tx_hash = await self._process_transaction(tx_params)
                
                await show_trx_log(
                    self.wallet_address, f"Swap {name_token_1} -> {name_token_2} on FaroSwap",
                    status, tx_hash, config.pharos_evm_explorer
                )
                
                if status:
                    return status, tx_hash
                    
            except Exception as e:
                error_msg = f"Error swap: {name_token_1} -> {name_token_2}: {str(e)}"
                await self.logger_msg(
                    error_msg, "error", self.wallet_address, "swap"
                )
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                
        return False, f"Swap failed after {MAX_RETRY_ATTEMPTS} attempts"
        
    async def run_swap(self) -> tuple[bool, str]:
        await self.logger_msg(f"Start {self.TASK_MSG}", "info", self.wallet_address)

        status, msg = await self.check_basic_config()
        if not status: return status, msg
        
        failed_swaps = []  # Список для хранения ошибок
        success_count = 0
        
        for key, (name_token_1, name_token_2, percentage) in self.config_swap.pair.items():
            try:
                await self.logger_msg(f"Processing pair №{key}: {name_token_1} - {name_token_2}", "info", self.wallet_address)
                
                # Получаем данные токенов
                address_token_1 = TOKENS_DATA_PHAROS.get(name_token_1)
                address_token_2 = TOKENS_DATA_PHAROS.get(name_token_2)
                
                if not address_token_1 or not address_token_2:
                    error = f"Token data not found for pair #{key}"
                    failed_swaps.append(error)
                    continue
                    
                # Проверяем баланс
                balance = await self.token_balance(address_token_1)
                if balance <= 0:
                    error = f"Insufficient {name_token_1} balance for pair #{key}"
                    failed_swaps.append(error)
                    continue
                    
                amount_in = int(balance * (percentage / 100))
                
                # Выполняем свап
                success, result_msg = await self.swap(
                    name_token_1, 
                    name_token_2,
                    self._get_checksum_address(address_token_1),
                    self._get_checksum_address(address_token_2),
                    amount_in
                )
                
                if not success:
                    failed_swaps.append(f"Pair #{key}: {result_msg}")
                else:
                    success_count += 1
                    
                await random_sleep(self.wallet_address, *SLEEP_SWAP)
                    
            except Exception as e:
                error = f"Unexpected error in pair #{key}: {str(e)}"
                failed_swaps.append(error)
                await self.logger_msg(error, "error", self.wallet_address)
        
        # Формируем финальный результат
        total_pairs = len(self.config_swap.pair)
        summary = (
            f"Completed {success_count}/{total_pairs} swaps. "
            f"Failed: {len(failed_swaps)}"
        )
        
        if failed_swaps:
            details = "\n".join(failed_swaps)
            return False, f"{summary}\nErrors:\n{details}"
            
        return True, f"{summary} All swaps completed successfully"
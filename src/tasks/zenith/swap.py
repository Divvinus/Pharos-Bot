import time
from pydantic import ValidationError
from typing import Self

from .config_modules import ZenithSwapBaseModule
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account, ZenithSwapRouterContract, ZenithQuoterContract
from src.utils import show_trx_log, random_sleep
from bot_loader import config
from configs import (
    MAX_RETRY_ATTEMPTS, 
    RETRY_SLEEP_RANGE,
    SLEEP_SWAP,
    SLIPPAGE, 
    TOKENS_DATA_PHAROS
)


class ZenithSwapModule(AsyncLogger, Wallet):
    TASK_MSG = "Swap tokens on Zenith Finance"
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(
            self, account.keypair, config.pharos_rpc_endpoints, account.proxy
        )
        AsyncLogger.__init__(self)
        self.slippage = SLIPPAGE
        self.config_swap = None
        self.deadline = int(time.time() + 12 * 3600)
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
        
    async def check_basic_config(self) -> tuple[bool, str]:
        balance = await self.human_balance()
        if not balance > 0:
            error_msg = "No $PHRS tokens in wallet"
            await self.logger_msg(error_msg, "error", self.wallet_address, "check_basic_config")
            return False, error_msg
        
        try:
            self.config_swap: ZenithSwapBaseModule = ZenithSwapBaseModule()
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

    async def get_quote(
        self, 
        token_in: str, 
        token_out: str, 
        amount_in: int, 
        fee: int = 500
    ) -> tuple[int, dict]:
        """ Получает котировку от Quoter V2 """
        try:
            quote_params = {
                "tokenIn": self._get_checksum_address(token_in),
                "tokenOut": self._get_checksum_address(token_out),
                "amountIn": amount_in,
                "fee": fee,
                "sqrtPriceLimitX96": 0
            }
            
            quoter_contract = await self.get_contract(ZenithQuoterContract())
            
            result = await quoter_contract.functions.quoteExactInputSingle(quote_params).call()
            
            amount_out, sqrt_price_after, ticks_crossed, gas_estimate = result
            
            quote_details = {
                "amount_out": amount_out,
                "sqrt_price_x96_after": sqrt_price_after,
                "ticks_crossed": ticks_crossed,
                "gas_estimate": gas_estimate,
                "effective_price": amount_out / amount_in if amount_in > 0 else 0,
                "fee": fee
            }
            
            return amount_out, quote_details
            
        except Exception as e:
            raise Exception(f"Error Quoter: {str(e)}")
        
    def apply_slippage(self, amount_out: int) -> int:
        """Применяет slippage к котировке"""
        return int(amount_out * (100 - self.slippage) / 100)

    async def calculate_amount_out_minimum(
        self, 
        token_in: str, 
        token_out: str, 
        amount_in: int,
        fee: int = 500
    ) -> int:
        """
        Расчет amount_out_minimum с fallback стратегией
        """
        try:
            amount_out, quote_details = await self.get_quote(
                token_in, token_out, amount_in, fee
            )
            
            amount_out_minimum = self.apply_slippage(amount_out)
            
            return amount_out_minimum
            
        except Exception as e:
            raise Exception(f"Quoter is not available: {str(e)}")
    
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
                router_contract = await self.get_contract(ZenithSwapRouterContract())
                router_address = self._get_checksum_address(ZenithSwapRouterContract().address)
                amount_out_minimum = 0
                
                # Approve токены если нужно (для не-нативных токенов)
                if name_token_1 != "PHRS" and amount_in > 0:
                    status, result = await self._check_and_approve_token(
                        token_address=address_token_1,
                        spender_address=router_address,
                        amount=amount_in
                    )
                    if not status:
                        return False, result
                
                if name_token_1 == "PHRS" and name_token_2 == "wPHRS":
                    # Wrap
                    wrapped_contract = await self.get_contract(TOKENS_DATA_PHAROS.get("wPHRS"))
                    tx_params = await self.build_transaction_params(
                        wrapped_contract.functions.deposit(),
                        value=amount_in
                    )
                
                elif name_token_1 == "wPHRS" and name_token_2 == "PHRS":
                    # Unwrap
                    wrapped_contract = await self.get_contract(TOKENS_DATA_PHAROS.get("wPHRS"))
                    tx_params = await self.build_transaction_params(
                        wrapped_contract.functions.withdraw(amount_in)
                    )
                
                elif name_token_1 == "PHRS" and name_token_2 != "wPHRS":
                    # PHRS -> ERC20                    
                    amount_out_minimum = await self.calculate_amount_out_minimum(
                        token_in=TOKENS_DATA_PHAROS.get("wPHRS"),
                        token_out=address_token_2,
                        amount_in=amount_in,
                        fee=500
                    )
                    
                    tx_params = await self.build_transaction_params(
                        router_contract.functions.exactInputSingle((
                            self._get_checksum_address(TOKENS_DATA_PHAROS.get("wPHRS")),  # tokenIn
                            self._get_checksum_address(address_token_2),                   # tokenOut
                            500,                                                            # fee
                            self.wallet_address,                                           # recipient
                            amount_in,                                                     # amountIn
                            amount_out_minimum,                                            # amountOutMinimum
                            0                                                              # sqrtPriceLimitX96
                        )),
                        value=amount_in  # Отправляем нативный PHRS
                    )

                elif name_token_1 not in ("PHRS", "wPHRS") and name_token_2 == "PHRS":
                    # ERC20 -> PHRS (через multicall)
                    amount_out_minimum = await self.calculate_amount_out_minimum(
                        token_in=address_token_1,
                        token_out=TOKENS_DATA_PHAROS.get("wPHRS"),
                        amount_in=amount_in,
                        fee=500
                    )
                    
                    # Подготавливаем multicall: exactInputSingle + unwrapWETH9
                    swap_data = router_contract.encode_abi(
                        "exactInputSingle",
                        args=[(
                            self._get_checksum_address(address_token_1),
                            self._get_checksum_address(TOKENS_DATA_PHAROS.get("wPHRS")),
                            500,
                            "0x0000000000000000000000000000000000000002",  # MSG_SENDER
                            amount_in,
                            amount_out_minimum,
                            0
                        )]
                    )
                    
                    unwrap_data = router_contract.encode_abi(
                        "unwrapWETH9",
                        args=[amount_out_minimum, self.wallet_address]
                    )
                    
                    tx_params = await self.build_transaction_params(
                        router_contract.functions.multicall([swap_data, unwrap_data])
                    )

                elif name_token_1 not in ("PHRS", "wPHRS") and name_token_2 not in ("PHRS", "wPHRS"):
                    # ERC20 -> ERC20                    
                    amount_out_minimum = await self.calculate_amount_out_minimum(
                        token_in=address_token_1,
                        token_out=address_token_2,
                        amount_in=amount_in,
                        fee=500
                    )
                    
                    tx_params = await self.build_transaction_params(
                        router_contract.functions.exactInputSingle((
                            self._get_checksum_address(address_token_1),
                            self._get_checksum_address(address_token_2),
                            500,
                            self.wallet_address,
                            amount_in,
                            amount_out_minimum,
                            0
                        ))
                    )

                elif name_token_1 == "wPHRS" and name_token_2 != "PHRS":
                    # wPHRS -> ERC20
                    amount_out_minimum = await self.calculate_amount_out_minimum(
                        token_in=TOKENS_DATA_PHAROS.get("wPHRS"),
                        token_out=address_token_2,
                        amount_in=amount_in,
                        fee=500
                    )
                    
                    tx_params = await self.build_transaction_params(
                        router_contract.functions.exactInputSingle((
                            self._get_checksum_address(TOKENS_DATA_PHAROS.get("wPHRS")),
                            self._get_checksum_address(address_token_2),
                            500,
                            self.wallet_address,
                            amount_in,
                            amount_out_minimum,
                            0
                        ))
                    )

                status, tx_hash = await self._process_transaction(tx_params)
                
                await show_trx_log(
                    self.wallet_address, f"Swap {name_token_1} -> {name_token_2} on Zenith Finance",
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
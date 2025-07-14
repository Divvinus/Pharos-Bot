import asyncio
import random
import functools
from decimal import Decimal
from typing import Any, Self, Callable

from better_proxy import Proxy
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress, HexStr
from pydantic import HttpUrl
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.contract import AsyncContract
from web3.eth import AsyncEth
from web3.types import Nonce, TxParams
from web3.middleware import ExtraDataToPOAMiddleware

from src.exceptions.wallet_exceptions import InsufficientFundsError, WalletError, BlockchainError
from src.models.onchain_model import BaseContract, ERC20Contract
from src.logger import AsyncLogger


logger = AsyncLogger()
Account.enable_unaudited_hdwallet_features()


class Wallet(Account):
    ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
    DEFAULT_TIMEOUT = 60
    MAX_RETRIES = 3
    
    def __init__(
        self, 
        keypair: str, 
        rpc_url: list[HttpUrl | str], 
        proxy: Proxy | None = None,
        request_timeout: int = 30
    ) -> None:
        if not rpc_url:
            raise WalletError("RPC URL list cannot be empty")
        
        self.rpc_urls = [str(url) for url in rpc_url]
        self.current_rpc_index = 0
        self.proxy = proxy
        self.request_timeout = request_timeout
        self.keypair = self._initialize_account(keypair)
        self._is_closed = False
        self._create_web3()
        
    def _create_web3(self):        
        self._provider = AsyncHTTPProvider(
            self.rpc_urls[self.current_rpc_index],
            request_kwargs={
                "proxy": self.proxy.as_url if self.proxy else None,
                "ssl": False,
                "timeout": self.request_timeout
            }
        )
        self.web3 = AsyncWeb3(self._provider, modules={"eth": AsyncEth})
        self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    def _switch_rpc_url(self):
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_urls)
        new_rpc_url = self.rpc_urls[self.current_rpc_index]
        self._create_web3()
        return new_rpc_url

    async def close(self):
        if self._is_closed:
            return
        
        try:
            if self._provider:
                await self._provider.disconnect()
            
        except Exception as e:
            await logger.logger_msg(
                f"Error during wallet cleanup: {str(e)}", "warning", self.__class__.__name__, "close"
            )
        finally:
            self._is_closed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @staticmethod
    def retry_with_rpc_switch(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            max_attempts = self.MAX_RETRIES
            current_attempt = 0
            last_error = None
            
            # Ошибки, при которых стоит переключить RPC
            rpc_related_errors = [
                "connection", "timeout", "network", "unreachable", 
                "503", "502", "500", "429", "gateway", "service unavailable",
                "read timeout", "connect timeout", "connection refused",
                "bad gateway", "too many requests", "rate limit",
                "invalid response", "rpc error", "node", "endpoint"
            ]
            
            def is_rpc_related_error(error_str: str) -> bool:
                error_lower = error_str.lower()
                return any(err.lower() in error_lower for err in rpc_related_errors)
            
            while current_attempt < max_attempts:
                try:
                    return await func(self, *args, **kwargs)
                    
                except Exception as e:
                    error_str = str(e)
                    last_error = e
                    
                    # Проверяем, связана ли ошибка с RPC
                    if is_rpc_related_error(error_str):
                        # Переключаем RPC только если проблема в RPC
                        old_rpc = self.rpc_urls[self.current_rpc_index]
                        new_rpc = self._switch_rpc_url()
                        
                        await logger.logger_msg(
                            f"RPC-related error in {func.__name__}: {error_str}. Switching RPC to: {new_rpc}", 
                            "warning", self.__class__.__name__, func.__name__
                        )
                        
                        # Небольшая пауза перед повтором с новым RPC
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        continue
                        
                    else:
                        # Если ошибка не связана с RPC - сразу завершаем
                        raise
                        
            raise BlockchainError(f"Failed in {func.__name__} after {max_attempts} attempts. Last error: {str(last_error)}")
        
        return wrapper

    @staticmethod
    def _initialize_account(input_str: str) -> Account:
        input_str = input_str.strip()

        key_candidate = input_str.replace(" ", "")
        if key_candidate.startswith('0x'):
            key_body = key_candidate[2:]
        else:
            key_body = key_candidate

        if len(key_body) == 64 and all(c in '0123456789abcdefABCDEF' for c in key_body):
            keypair = '0x' + key_body if not key_candidate.startswith('0x') else key_candidate
            try:
                return Account.from_key(keypair)
            except ValueError:
                pass

        words = [word for word in input_str.split() if word]
        if len(words) in (12, 24):
            mnemonic = ' '.join(words)
            try:
                return Account.from_mnemonic(mnemonic)
            except ValueError as e:
                raise WalletError(f"Invalid mnemonic phrase: {e}")
        else:
            raise WalletError("Input must be a 12 or 24 word mnemonic phrase or a 64-character hexadecimal private key")

    @property
    def wallet_address(self):
        return self.keypair.address

    @retry_with_rpc_switch
    async def is_eip1559_supported(self) -> bool:
        latest_block = await self.web3.eth.get_block('latest')
        return 'baseFeePerGas' in latest_block

    @staticmethod
    def _get_checksum_address(address: str) -> ChecksumAddress:
        return AsyncWeb3.to_checksum_address(address)   

    async def get_contract(self, contract: BaseContract | str | object) -> AsyncContract:
        if isinstance(contract, str):
            address = self._get_checksum_address(contract)
            temp_contract = ERC20Contract(address="")
            abi = await temp_contract.get_abi()
            return self.web3.eth.contract(address=address, abi=abi)
        
        if isinstance(contract, BaseContract):
            address = self._get_checksum_address(contract.address)
            abi = await contract.get_abi()
            return self.web3.eth.contract(
                address=address,
                abi=abi
            )

        if hasattr(contract, "address") and hasattr(contract, "abi"):
            address = self._get_checksum_address(contract.address)
            return self.web3.eth.contract(
                address=address,
                abi=contract.abi
            )

        raise TypeError("Invalid contract type: expected BaseContract, str, or contract-like object")

    @retry_with_rpc_switch
    async def token_balance(self, token_address: str) -> int:
        if self._is_native_token(token_address):
            return await self.web3.eth.get_balance(self.keypair.address)
        contract = await self.get_contract(token_address)
        return await contract.functions.balanceOf(
            self._get_checksum_address(self.keypair.address)
        ).call()

    def _is_native_token(self, token_address: str) -> bool:
        return token_address in (self.ZERO_ADDRESS)

    @retry_with_rpc_switch
    async def convert_amount_to_decimals(self, amount: Decimal, token_address: str) -> int:
        checksum_address = self._get_checksum_address(token_address)

        if self._is_native_token(checksum_address):
            return self.web3.to_wei(Decimal(str(amount)), 'ether')
        
        contract = await self.get_contract(token_address) 
        decimals = await contract.functions.decimals().call()
        return int(Decimal(str(amount)) * Decimal(10 ** decimals))

    @retry_with_rpc_switch
    async def convert_amount_from_decimals(self, amount: int, token_address: str) -> float:
        checksum_address = self._get_checksum_address(token_address)

        if self._is_native_token(checksum_address):
            return float(self.web3.from_wei(amount, 'ether'))
        
        contract = await self.get_contract(token_address)
        decimals = await contract.functions.decimals().call()
        return float(Decimal(amount) / Decimal(10 ** decimals))

    @retry_with_rpc_switch
    async def get_nonce(self) -> Nonce:
        count = await self.web3.eth.get_transaction_count(self.wallet_address, 'pending')
        return Nonce(count)

    @retry_with_rpc_switch
    async def check_balance(self) -> bool:
        return await self.web3.eth.get_balance(self.keypair.address)

    @retry_with_rpc_switch
    async def human_balance(self) -> float:
        balance = await self.web3.eth.get_balance(self.keypair.address)
        return float(self.web3.from_wei(balance, "ether"))
    
    @retry_with_rpc_switch
    async def has_sufficient_funds_for_tx(self, transaction: TxParams) -> bool:
        balance = await self.web3.eth.get_balance(self.keypair.address)
        required = int(transaction.get('value', 0))
        
        if balance < required:
            required_eth = self.web3.from_wei(required, 'ether')
            balance_eth = self.web3.from_wei(balance, 'ether')
            raise InsufficientFundsError(
                f"Insufficient ETH balance. Required: {required_eth:.6f} ETH, Available: {balance_eth:.6f} ETH"
            )
            
        return True

    @retry_with_rpc_switch
    async def get_signature(self, text: str, keypair: str | None = None):
        try:
            signing_key = (
                self.from_key(keypair) 
                if keypair 
                else self.keypair
            )

            encoded = encode_defunct(text=text)
            signature = signing_key.sign_message(encoded).signature
            
            return signature.hex()

        except Exception as error:
            raise ValueError(f"Signing failed: {str(error)}") from error

    @retry_with_rpc_switch
    async def _estimate_gas_params(
        self,
        tx_params: dict,
        gas_buffer: float = 1.2,
        gas_price_buffer: float = 1.05,
        block_count: int = 25  # Количество блоков для анализа
    ) -> dict:
        gas_estimate = await self.web3.eth.estimate_gas(tx_params)
        tx_params["gas"] = int(gas_estimate * gas_buffer)
        
        if await self.is_eip1559_supported():
            # Получаем исторические данные о газе
            base_fee_avg, priority_fee_avg = await self.get_gas_stats(block_count)
            
            # Рассчитываем базовые значения с буфером
            base_fee_val = int(base_fee_avg * gas_price_buffer)
            priority_fee_val = int(priority_fee_avg * gas_price_buffer)
            
            # Генерируем случайные отклонения (+/- 5%)
            base_fee_random = random.randint(int(base_fee_val * 0.95), int(base_fee_val * 1.05))
            priority_fee_random = random.randint(int(priority_fee_val * 0.95), int(priority_fee_val * 1.05))
            
            # Гарантируем минимальные значения с вариацией
            min_base_fee = max(base_fee_random, random.randint(1, 10))  # Случайное значение от 1 до 10
            min_priority = max(priority_fee_random, random.randint(1, 5))  # Случайное значение от 1 до 5
            
            # Рассчитываем максимальную цену газа
            max_fee_val = min_base_fee * 2 + min_priority
            
            tx_params.update({
                "maxPriorityFeePerGas": min_priority,
                "maxFeePerGas": max_fee_val
            })
        else:
            # Для legacy-транзакций
            gas_price = await self.web3.eth.gas_price
            gas_price_random = random.randint(int(gas_price * 0.95), int(gas_price * 1.05))
            tx_params["gasPrice"] = max(
                int(gas_price_random * gas_price_buffer), 
                random.randint(1, 10)  # Случайное минимальное значение
            )
            
        return tx_params

    @retry_with_rpc_switch
    async def get_gas_stats(self, block_count: int = 25) -> tuple[int, int]:
        """Возвращает средний baseFeePerGas и средний приоритетный fee из последних блоков"""
        try:
            latest_block_number = await self.web3.eth.block_number
            start_block = max(latest_block_number - block_count + 1, 0)
            block_numbers = list(range(start_block, latest_block_number + 1))
            
            blocks = await asyncio.gather(
                *[self.web3.eth.get_block(block_num, full_transactions=True) for block_num in block_numbers]
            )
            
            base_fees = []
            priority_fees = []
            
            for block in blocks:
                if 'baseFeePerGas' in block:
                    base_fees.append(block['baseFeePerGas'])
                    
                # Анализируем транзакции в блоке
                if block['transactions']:
                    for tx in block['transactions']:
                        if 'maxPriorityFeePerGas' in tx:
                            priority_fees.append(tx['maxPriorityFeePerGas'])
            
            # Если нет данных о приоритетных fee, используем текущий
            if not priority_fees:
                priority_fee_avg = await self.web3.eth.max_priority_fee
            else:
                priority_fee_avg = sum(priority_fees) // len(priority_fees)
            
            return (
                sum(base_fees) // len(base_fees) if base_fees else 0,
                priority_fee_avg
            )
            
        except Exception:
            latest_block = await self.web3.eth.get_block('latest')
            priority_fee = await self.web3.eth.max_priority_fee
            return (
                latest_block.get('baseFeePerGas', 0),
                priority_fee
            )
    
    @retry_with_rpc_switch
    async def build_transaction_params(
        self,
        contract_function: Any = None,
        to: str = None,
        value: int = 0,
        gas_buffer: float = 1.2,
        gas_price_buffer: float = 1.05,
        gas: int = None,
        gas_price: int = None,
        **kwargs
    ) -> dict:
        base_params = {
            "from": self.wallet_address,
            "nonce": await self.get_nonce(),
            "value": value,
            **kwargs
        }

        try:
            chain_id = await self.web3.eth.chain_id
            base_params["chainId"] = chain_id
        except Exception as e:
            await logger.logger_msg(
                msg=f"Failed to get chain_id with RPC {self.rpc_urls[self.current_rpc_index]}: {e}", 
                type_msg="warning", 
                address=self.wallet_address,
                method_name="build_transaction_params"
            )

        should_estimate_gas = gas is None or gas_price is None
    
        if contract_function is None:
            if to is None:
                raise ValueError("'to' address required for ETH transfers")
            base_params.update({"to": to})
            return await self._estimate_gas_params(base_params, gas_buffer, gas_price_buffer) if should_estimate_gas else base_params
        
        tx_params = await contract_function.build_transaction(base_params)
        return await self._estimate_gas_params(tx_params, gas_buffer, gas_price_buffer) if should_estimate_gas else tx_params
    
    @retry_with_rpc_switch
    async def _check_and_approve_token(
        self, 
        token_address: str, 
        spender_address: str, 
        amount: int
    ) -> tuple[bool, str]:
        try:
            token_contract = await self.get_contract(token_address)
            
            current_allowance = await token_contract.functions.allowance(
                self.wallet_address, 
                spender_address
            ).call()

            if current_allowance >= amount:
                return True, "Allowance already sufficient"

            approve_params = await self.build_transaction_params(
                contract_function=token_contract.functions.approve(spender_address, amount),
            )

            success, result = await self._process_transaction(approve_params)
            if not success:
                raise WalletError(f"Approval failed: {result}")

            success_msg = f"Approval {token_address} successful"
            await logger.logger_msg(success_msg, "success")
            return True, success_msg

        except Exception as error:
            error_msg = f"Error during approval: {str(error)}"
            await logger.logger_msg(error_msg, "error", "_check_and_approve_token")
            return False, error_msg
        
    @retry_with_rpc_switch
    async def send_and_verify_transaction(self, transaction: Any) -> tuple[bool, str]:
        tx_hash = None
        try:
            signed = self.keypair.sign_transaction(transaction)
            tx_hash = await self.web3.eth.send_raw_transaction(signed.raw_transaction)
            
            receipt = await asyncio.wait_for(
                self.web3.eth.wait_for_transaction_receipt(tx_hash),
                timeout=self.DEFAULT_TIMEOUT
            )
            if receipt["status"] == 1:
                return True, tx_hash.hex()
            else:
                return False, f"Transaction reverted. Hash: {tx_hash.hex()}"
            
        except asyncio.TimeoutError:
            if tx_hash:
                await logger.logger_msg(
                    f"Transaction sent but confirmation timed out. Hash: {tx_hash.hex()}", "warning", "send_and_verify_transaction"
                )
                return False, f"PENDING:{tx_hash.hex()}"
                
        except Exception as error:
            error_str = str(error)
            if "NONCE_TOO_SMALL" in error_str or "nonce too low" in error_str.lower():
                await logger.logger_msg(
                    f"Nonce too small. Current: {transaction.get('nonce')}. Getting new nonce", "warning", "send_and_verify_transaction"
                )
                try:
                    new_nonce = await self.web3.eth.get_transaction_count(self.wallet_address, 'pending')
                    if new_nonce <= transaction['nonce']:
                        new_nonce = transaction['nonce'] + 1
                    transaction['nonce'] = new_nonce
                    # Повторная попытка с новым nonce
                    return await self.send_and_verify_transaction(transaction)
                except Exception as nonce_error:
                    await logger.logger_msg(f"Error getting new nonce: {str(nonce_error)}", "error", "send_and_verify_transaction")
            raise

    async def _process_transaction(self, transaction: Any) -> tuple[bool, str]:
        await  logger.logger_msg("Sending the transaction to the blockchain", "info")
        try:
            status, result = await self.send_and_verify_transaction(transaction)
            return status, result
        except Exception as error:
            return False, str(error)
from typing import Self

from bot_loader import config
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.logger import AsyncLogger
from src.models import Account, PharosBadgeContract
from src.utils import random_sleep, show_trx_log
from src.wallet import Wallet


class PharosBadge(AsyncLogger, Wallet):
    TASK_MSG = "Mint Pharos Testnet Badge"
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(
            self, account.keypair, config.pharos_rpc_endpoints, account.proxy
        )
        AsyncLogger.__init__(self)
        self.account = account
        self.jwt_token: str | None = None
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
        
    async def run_mint_pharos_badge(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )   
            try:
                balance = await self.human_balance()
                if not balance > 1:
                    error_msg = f'You do not have enough tokens in your balance to execute {self.TASK_MSG}. Your balance: {balance} $PHRS. Required: 1 $PHRS.'
                    await self.logger_msg(error_msg, "error", self.wallet_address, "run_mint_pharos_badge")
                    return False, error_msg
                
                contract = await self.get_contract(PharosBadgeContract())
                address = self._get_checksum_address(PharosBadgeContract().address)
                
                baalnce_badge = await self.token_balance(address)
                if baalnce_badge > 0:
                    success_msg = "You've previously claimed Pharos Testnet Badge"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    return True, success_msg
                
                allowlist_proof = (
                    [],
                    0,
                    2**256 - 1,
                    "0x0000000000000000000000000000000000000000"
                )
                
                tx_params = await self.build_transaction_params(
                    contract.functions.claim(
                        self.wallet_address,
                        1,
                        self._get_checksum_address("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
                        self.web3.to_wei(1, "ether"),
                        allowlist_proof,
                        b''
                    ),
                    value=self.web3.to_wei(1, "ether")
                )
                
                status, tx_hash = await self._process_transaction(tx_params)

                if status:
                    await show_trx_log(
                        self.wallet_address, self.TASK_MSG, 
                        status, tx_hash, config.pharos_evm_explorer
                    )
                    
                if status:
                    return status, tx_hash
                
            except Exception as e:
                error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_mint_pharos_badge")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
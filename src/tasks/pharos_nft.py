from typing import Self

from bot_loader import config
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.logger import AsyncLogger
from src.models import Account, PharosNftContract
from src.utils import random_sleep, show_trx_log
from src.wallet import Wallet


class PharosNft(AsyncLogger, Wallet):
    TASK_MSG = "Mint Pharos Testnet Nft"
    
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
        
    async def run_mint_pharos_nft(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )   
            try:                
                contract = await self.get_contract(PharosNftContract())
                address = self._get_checksum_address(PharosNftContract().address)
                
                baalnce_nft = await self.token_balance(address)
                if baalnce_nft > 0:
                    success_msg = "You've previously claimed Pharos Testnet Nft"
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
                        0,
                        allowlist_proof,
                        b''
                    )
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
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_mint_pharos_nft")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
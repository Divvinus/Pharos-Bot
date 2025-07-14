import random
from typing import Self

from bot_loader import config
from ..registration import ConnectWalletPharos
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE, MAX_SEND_PHRS
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import random_sleep, show_trx_log
from src.wallet import Wallet


# Тип для HTTP-заголовков
Headers = dict[str, str]

class SendToFriends(AsyncLogger, Wallet):
    TASK_MSG = '"Send To Friends" task'
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(
            self, account.keypair, config.pharos_rpc_endpoints, account.proxy
        )
        AsyncLogger.__init__(self)
        self.account = account
        self.api_client: HTTPClient | None = None
        self.jwt_token: str | None = None
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        
        self.api_client = HTTPClient(
            "https://api.pharosnetwork.xyz",  self.account.proxy
        )
        await self.api_client.__aenter__()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
        
    @staticmethod
    async def process_connect_wallet(account: Account) -> tuple[bool, str]:
        async with ConnectWalletPharos(account) as pharosnetwork:
            return await pharosnetwork.run_connect_wallet(return_token=True)
        
    def get_headers(self) -> Headers:
        """Заголовки для запросов к Pharos API"""
        return {
            'accept': 'application/json, text/plain, */*',
            'authorization': f'Bearer {self.jwt_token}',
            'origin': 'https://testnet.pharosnetwork.xyz',
            'referer': 'https://testnet.pharosnetwork.xyz/'
        }
        
    async def get_to_address(self) -> str:
        headers = {
            'accept': '*/*',
            'content-type': 'application/json',
            'origin': 'https://testnet.pharosscan.xyz',
            'referer': 'https://testnet.pharosscan.xyz/',
        }
        
        params = {
            'size': '1',
            'page': random.randint(1, 1000),
        }
        
        response = await self.api_client.send_request(
            method="GET",
            url="https://api.socialscan.io/pharos-testnet/v1/explorer/transactions",
            params=params,
            headers=headers
        )
        
        transaction = response['data']['data'][0]
        return self._get_checksum_address(transaction['from_address'])
        
    async def verify_tasks(self, tx_hash: str) -> tuple[bool, str]:
        await self.logger_msg(f"Send a request for {self.TASK_MSG}", "info", self.wallet_address)
        
        json_data  = {
            'address': self.wallet_address,
            'task_id': 103,
            'tx_hash': f'0x{tx_hash}',
        }
        
        response = await self.api_client.send_request(
            method="POST",
            endpoint="/task/verify",
            json_data=json_data ,
            headers=self.get_headers()
        )
        
        response_data = response['data']
        
        status = response_data.get("code")
        if status == 0:
            success_msg = f"{self.TASK_MSG} completed successfully"
            await self.logger_msg(success_msg, "success", self.wallet_address)
            return True, success_msg
        
        error_msg = f"{self.TASK_MSG} unknown error: {response}"
        await self.logger_msg(error_msg, "error", self.wallet_address, "verify_tasks")
        return False, error_msg
        
    async def run_send_to_friends(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        result, self.jwt_token = await self.process_connect_wallet(self.account)
        if not result:
            return result, self.jwt_token
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )   
            try:
                balance = await self.human_balance()
                if not balance > 0:
                    error_msg = f'You do not have tokens in your balance to execute {self.TASK_MSG}. Your balance: {balance} $PHRS'
                    await self.logger_msg(error_msg, "error", self.wallet_address, "run_send_to_friends")
                    return False, error_msg
                
                if MAX_SEND_PHRS <= 0 or not isinstance(MAX_SEND_PHRS, (int, float)):
                    error_msg = f'Incorrectly configured MAX_SEND_PHRS, should be a number greater than zero'
                    await self.logger_msg(error_msg, "error", self.wallet_address, "run_send_to_friends")
                    return False, error_msg
                
                if MAX_SEND_PHRS > balance:
                    max_send = balance
                else:
                    max_send = MAX_SEND_PHRS
                
                send_amount = round(random.uniform(0.001, max_send), 5)
                to_address = await self.get_to_address()
                
                tx_params = await self.build_transaction_params(
                    to=to_address,
                    value=self.web3.to_wei(send_amount, "ether")
                )
                
                status, tx_hash = await self._process_transaction(tx_params)

                if status:
                    await show_trx_log(
                        self.wallet_address, f"Transfer {send_amount} $PHRS to {to_address}", 
                        status, tx_hash, config.pharos_evm_explorer
                    )
                    
                    status, result = await self.verify_tasks(tx_hash)
                    if status:
                        return status, result
                    
                    else:
                        continue
                    
                else:
                    continue
                
            except Exception as e:
                error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_send_to_friends")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
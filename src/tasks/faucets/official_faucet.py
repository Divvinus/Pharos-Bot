from typing import Self

from src.tasks.registration  import ConnectWalletPharos
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address, random_sleep


# Тип для HTTP-заголовков
Headers = dict[str, str]

class OfficialFaucet(AsyncLogger):
    TASK_MSG = "Faucet $PHRS"
    
    def __init__(self, account: Account) -> None:
        AsyncLogger.__init__(self)
        self.account = account
        self.api_client: HTTPClient | None = None
        self.jwt_token: str | None = None
        self._wallet_address: str | None = None 
        
    async def __aenter__(self) -> Self:        
        self.api_client = HTTPClient(
            "https://api.pharosnetwork.xyz",  self.account.proxy
        )
        await self.api_client.__aenter__()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
        
    @property
    def wallet_address(self) -> str:
        if self._wallet_address is None:
            self._wallet_address = get_address(self.account.keypair)
        return self._wallet_address
        
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
        
    async def faucet(self) -> tuple[bool, str]:        
        params = {
            'address': self.wallet_address
        }
        
        response = await self.api_client.send_request(
            method="POST",
            endpoint="/faucet/daily",
            params=params,
            headers=self.get_headers()
        )
        
        response_data = response['data']
        
        status = response_data.get("code")
        if status == 0:
            return True, "True"
        if status == 1:
            return False, response_data.get("msg")
        
        error_msg = f"Unknown error: {response}"
        await self.logger_msg(error_msg, "error", self.wallet_address, "faucet")
        return False, error_msg
        
    async def run_faucet(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        result, self.jwt_token = await self.process_connect_wallet(self.account)
        if not result:
            return result, self.jwt_token
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )   
            try:
                status, result = await self.faucet()
                
                if status:
                    success_msg = f"Successfully {self.TASK_MSG}"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    return True, success_msg
                
                if result == "faucet did not cooldown":
                    success_msg = f"It hasn't been 24 hours since the last {self.TASK_MSG}"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    return True, success_msg
                
                if result == "user has not bound X account":
                    error_msg = f"Need to link the twitter account before {self.TASK_MSG}"
                    await self.logger_msg(error_msg, "error", self.wallet_address)
                    return False, error_msg
                
                await self.logger_msg(result, "warning", self.wallet_address, "run_faucet")
                
            except Exception as e:
                error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_faucet")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
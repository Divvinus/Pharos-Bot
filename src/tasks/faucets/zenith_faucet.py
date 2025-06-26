from typing import Self

from src.api.captcha  import CaptchaSolver
from configs import (
    MAX_RETRY_ATTEMPTS, 
    RETRY_SLEEP_RANGE,
    CAP_MONSTER_API_KEY,
    TWO_CAPTCHA_API_KEY
)
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address, random_sleep


# Тип для HTTP-заголовков
Headers = dict[str, str]

class ZenithFaucet(AsyncLogger):
    TASK_MSG = "Stablecoins faucet"
    
    def __init__(self, account: Account) -> None:
        AsyncLogger.__init__(self)
        self.account = account
        self.api_client: HTTPClient | None = None
        self._wallet_address: str | None = None 
        
    async def __aenter__(self) -> Self:        
        self.api_client = HTTPClient(
            "https://testnet-router.zenithswap.xyz/api",  self.account.proxy
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
        
    def get_headers(self) -> Headers:
        """Заголовки для запросов к Zenith Swap API"""
        return {
            'accept': '*/*',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://testnet.zenithfinance.xyz',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://testnet.zenithfinance.xyz/'
        }
        
    async def get_tokens(self) -> tuple[bool, str]:        
        async with CaptchaSolver(self.account) as solver:
            captcha_token = await solver.solve_captcha()
        
        json_data = {
            'CFTurnstileResponse': captcha_token
        }
            
        response = await self.api_client.send_request(
            method="POST",
            endpoint="/v1/faucet",
            json_data=json_data,
            headers=self.get_headers()
        )
        
        response_data = response['data']
        
        if response_data["message"] == "ok":
            return True, response_data["data"]["txHash"]
        
        return False, response_data.get("message", "Unknow error")            
        
    async def run_faucet(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        captcha_keys = [CAP_MONSTER_API_KEY, TWO_CAPTCHA_API_KEY]
        available_keys = [key for key in captcha_keys if key]
        if not available_keys:
            error_msg = "No valid API key was found"
            await self.logger_msg(error_msg, "error", self.wallet_address, "run_faucet")
            return False, error_msg
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )   
            try:                
                status, result = await self.get_tokens()
                
                if status:
                    success_msg = f"Successfully {self.TASK_MSG}"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    return True, success_msg
                
                if "has already got token today" in result:
                    success_msg = f"It hasn't been 24 hours since the last {self.TASK_MSG}"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    return True, success_msg
                
                await self.logger_msg(result, "warning", self.wallet_address, "run_faucet")
                
            except Exception as e:
                error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_faucet")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
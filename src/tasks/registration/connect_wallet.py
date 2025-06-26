import random
from typing import Self

from bot_loader import config
from configs import REFERRAL_CODES
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import random_sleep, ConfigValidator
from src.wallet import Wallet


login_validator = ConfigValidator()

@login_validator.register("REFERRAL_CODES", "Must be a valid list with at least one valid referral code")
def validate_withdraw_amount(value, context) -> bool:
    if not isinstance(value, list):
        return False
    
    return value

class ConnectWalletPharos(AsyncLogger, Wallet):
    TASK_MSG = "Connect wallet on Pharos Network site"
    
    def __init__(self, account: Account, login: bool = True) -> None:
        Wallet.__init__(
            self, account.keypair, config.pharos_rpc_endpoints, account.proxy
        )
        AsyncLogger.__init__(self)
        self.account = account
        self.login = login
        self.api_client: HTTPClient | None = None
        self.pharos_jwt: str | None = None

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
        
    async def check_configs(self) -> tuple[bool, str]:
        config_context = {
            "REFERRAL_CODES": REFERRAL_CODES
        }
        
        valid, msg = login_validator.validate(config_context)
        
        if not valid:
            await self.logger_msg(msg, "error", self.wallet_address, "check_configs")
        
        return valid, msg
    
    async def _get_params(self) -> dict:
        try:
            signature = await self.get_signature('pharos')
        except Exception as error:
            raise error
        
        response = {
            'address': self.wallet_address,
            'signature': f"0x{signature}",  
        }

        if not self.login:
            response['invite_code'] = random.choice(REFERRAL_CODES)

        return response
        
    def _get_headers(self) -> dict:
        return {
            'accept': 'application/json, text/plain, */*',
            'authorization': 'Bearer null',
            'origin': 'https://testnet.pharosnetwork.xyz',
            'referer': 'https://testnet.pharosnetwork.xyz/'
        }
        
    def _extract_jwt_token(self, response: dict) -> str:
        try:
            if not response or 'data' not in response:
                raise ValueError("Invalid API response format - missing 'data' field")
            
            response_data = response['data']
            
            if response_data.get('code') != 0:
                raise ValueError(f"API returned error code: {response_data}")
            
            if 'data' not in response_data or 'jwt' not in response_data['data']:
                raise ValueError("JWT token not found in response")
            
            return response_data['data']['jwt']
    
        except Exception as e:
            raise ValueError(f"Failed to extract JWT token: {str(e)}")
        
    async def run_connect_wallet(self, return_token: bool = False) -> tuple[bool, str]:
        await self.logger_msg(f"Start {self.TASK_MSG}", "info", self.wallet_address)
        
        if not self.login:
            status, msg = await self.check_configs()
            if not status: 
                return status, msg

        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )            
            try:
                params = await self._get_params()
                
                response = await self.api_client.send_request(
                    method="POST",
                    endpoint="/user/login",
                    params=params,
                    headers=self._get_headers()
                )
                
                self.pharos_jwt = self._extract_jwt_token(response)
                
                if self.pharos_jwt:
                    success_msg = f"Wallet address successfully linked to Pharos Network"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    
                    if return_token:
                        return True, self.pharos_jwt
                    return True, success_msg

            except Exception as e:
                error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_connect_wallet")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
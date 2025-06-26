from typing import Self

from bot_loader import config
from .registration import ConnectWalletPharos
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address, random_sleep


# Тип для HTTP-заголовков
Headers = dict[str, str]

class StatisticsAccount(AsyncLogger):
    TASK_MSG = "Account statistics"
    
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
        
    async def get_statistics(self) -> tuple[bool, str]:        
        params = {
            'address': self.wallet_address
        }
        
        response = await self.api_client.send_request(
            method="GET",
            endpoint="/user/profile",
            params=params,
            headers=self.get_headers()
        )
        
        response_data = response['data']
        
        user = response_data.get("data", {}).get("user_info", {})
    
        # Проверка привязки социальных сетей
        twitter_status = "Bound" if user.get("XId") else "Not Bound"
        discord_status = "Bound" if user.get("DiscordId") else "Not Bound"
        
        # Форматирование дат
        create_time = user.get("CreateTime", "").replace("T", " ").split(".")[0]
        update_time = user.get("UpdateTime", "").replace("T", " ").split(".")[0]
        
        # Форматирование булевых значений
        is_kol = "Yes" if user.get("IsKol") else "No"
        
        # Построение статистики
        stats = f"""
            📊 Account statistics {user.get('Address', '')}

            🔹 ID: {user.get('ID', 'N/A')}
            🔹 Invite code: {user.get('InviteCode', '')}
            🔹 Date of Creation: {create_time}
            🔹 Last update: {update_time}

            🌐 Social media:
            • Twitter: {twitter_status}
            • Discord: {discord_status}

            ⭐ KOL Status: {is_kol}
            💯 Points:
            • Total points: {user.get('TotalPoints', 0)}
            • Task points: {user.get('TaskPoints', 0)}
            • Invite points: {user.get('InvitePoints', 0)}

            👨‍👦 Referral system:
            • Father: {user.get('FatherAddress', '')}
            • Grandpa: {user.get('GrandpaAddress', '')}
        """
        
        await self.logger_msg(stats, "success")
        
        return stats
        
    async def run_statistics_account(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        result, self.jwt_token = await self.process_connect_wallet(self.account)
        if not result:
            return result, self.jwt_token
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )   
            try:
                return await self.get_statistics()                                
            except Exception as e:
                error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_statistics_account")

                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed {self.TASK_MSG} after {MAX_RETRY_ATTEMPTS} attempts"
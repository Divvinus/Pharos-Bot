from .official_faucet import OfficialFaucet
from .zenith_faucet import ZenithFaucet

from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address

class FullFaucets(AsyncLogger):
    TASK_MSG = "Requesting test tokens from all faucets"
    
    def __init__(self, account: Account) -> None:
        AsyncLogger.__init__(self)
        self.account: Account = account
        self._wallet_address: str | None = None 
        
    @property
    def wallet_address(self) -> str:
        if self._wallet_address is None:
            self._wallet_address = get_address(self.account.keypair)
        return self._wallet_address
        
    @staticmethod
    async def process_phrs_faucet(account: Account) -> tuple[bool, str]:
        async with OfficialFaucet(account) as faucet:
            return await faucet.run_faucet()
        
    @staticmethod
    async def process_zenith_faucet(account: Account) -> tuple[bool, str]:
        async with ZenithFaucet(account) as faucet:
            return await faucet.run_faucet()
        
    async def run_faucets(self) -> tuple[bool, str]:
        """Запрос тестовых токенов со всех доступных кранов"""
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        # Результаты выполнения для каждого крана
        results = {
            "Official PHRS Faucet": (False, "Not executed"),
            "Zenith Faucet": (False, "Not executed")
        }
        
        # Этап 1: Официальный кран PHRS
        try:
            faucet_success, faucet_msg = await self.process_phrs_faucet(self.account)
            results["Official PHRS Faucet"] = (faucet_success, faucet_msg)
        except Exception as e:
            error_msg = f"Unexpected error in PHRS faucet: {str(e)}"
            results["Official PHRS Faucet"] = (False, error_msg)
        
        # Этап 2: Кран Zenith
        try:
            zenith_success, zenith_msg = await self.process_zenith_faucet(self.account)
            results["Zenith Faucet"] = (zenith_success, zenith_msg)
        except Exception as e:
            error_msg = f"Unexpected error in Zenith faucet: {str(e)}"
            results["Zenith Faucet"] = (False, error_msg)
        
        # Анализ результатов
        successful_faucets = []
        failed_faucets = []
        
        for faucet_name, (success, message) in results.items():
            if success:
                successful_faucets.append(f"{faucet_name}: {message}")
            else:
                failed_faucets.append(f"{faucet_name}: {message}")
        
        total_faucets = len(results)
        success_count = len(successful_faucets)
        
        # Формирование итогового отчета
        if success_count == total_faucets:
            faucets_list = "\n    • " + "\n    • ".join(f"✅ {item}" for item in successful_faucets)
            final_msg = (
                f"\n💧 Successfully claimed from ALL faucets! 💦\n"
                f"Claimed from {success_count}/{total_faucets} faucets:\n{faucets_list}"
            )
            await self.logger_msg(final_msg, "success", self.wallet_address)
            return True, final_msg
            
        elif success_count == 0:
            faucets_list = "\n    • " + "\n    • ".join(f"❌ {item}" for item in failed_faucets)
            final_msg = (
                f"\n⛔ Failed to claim from ANY faucet!\n"
                f"Failed faucets ({total_faucets}):\n{faucets_list}"
            )
            await self.logger_msg(final_msg, "error", self.wallet_address)
            return False, final_msg
            
        else:
            success_list = "\n    • " + "\n    • ".join(f"✅ {item}" for item in successful_faucets) if successful_faucets else ""
            fail_list = "\n    • " + "\n    • ".join(f"❌ {item}" for item in failed_faucets) if failed_faucets else ""
            final_msg = (
                f"\n⚠️ Partially successful faucet claims\n"
                f"Success: {success_count}/{total_faucets}\n"
                f"Successful claims:{success_list}\n"
                f"Failed claims:{fail_list}"
            )
            await self.logger_msg(final_msg, "warning", self.wallet_address)
            return False, final_msg
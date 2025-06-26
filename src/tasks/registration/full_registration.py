from .connect_wallet import ConnectWalletPharos
from .connect_twitter import ConnectTwitterPharos
from .connect_discord import ConnectDiscordPharos
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address

class FullRegistrationPharos(AsyncLogger):
    TASK_MSG = "Full registration on Pharos Network site"
    
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
    async def process_connect_wallet(account: Account) -> tuple[bool, str]:
        async with ConnectWalletPharos(account, False) as pharosnetwork:
            return await pharosnetwork.run_connect_wallet()
        
    @staticmethod
    async def process_connect_twitter(account: Account) -> tuple[bool, str]:
        twitter = ConnectTwitterPharos(account)
        return await twitter.run_connect_twitter()
    
    @staticmethod
    async def process_connect_discord(account: Account) -> tuple[bool, str]:
        discord = ConnectDiscordPharos(account)
        return await discord.run_connect_discord()
    
    async def run_full_registration(self) -> tuple[bool, str]:
        """Полная регистрация аккаунта на Pharos Network (кошелек + Twitter + Discord)"""
        await self.logger_msg(f"Start {self.TASK_MSG}", "info", self.wallet_address)
        
        # Результаты выполнения каждого этапа
        results = {
            "wallet": (False, "Not executed"),
            "twitter": (False, "Not executed"), 
            "discord": (False, "Not executed")
        }
        
        # Этап 1: Подключение кошелька
        try:
            wallet_success, wallet_message = await self.process_connect_wallet(self.account)
            results["wallet"] = (wallet_success, wallet_message)
                
        except Exception as e:
            error_msg = f"Unexpected error during wallet connection: {str(e)}"
            results["wallet"] = (False, error_msg)
        
        # Этап 2: Подключение Twitter
        try:
            twitter_success, twitter_message = await self.process_connect_twitter(self.account)
            results["twitter"] = (twitter_success, twitter_message)
                
        except Exception as e:
            error_msg = f"Unexpected error during Twitter connection: {str(e)}"
            results["twitter"] = (False, error_msg)
        
        # Этап 3: Подключение Discord
        try:
            discord_success, discord_message = await self.process_connect_discord(self.account)
            results["discord"] = (discord_success, discord_message)
                
        except Exception as e:
            error_msg = f"Unexpected error during Discord connection: {str(e)}"
            results["discord"] = (False, error_msg)
        
        # Анализ результатов и формирование итогового ответа
        successful_steps = []
        failed_steps = []
        
        for step_name, (success, message) in results.items():
            if success:
                successful_steps.append(f"{step_name.capitalize()}: {message}")
            else:
                failed_steps.append(f"{step_name.capitalize()}: {message}")
        
        # Определение итогового статуса
        success_count = len(successful_steps)
        total_steps = len(results)
        
        if success_count == total_steps:
            # Все этапы успешны ✅
            steps_list = "\n    • " + "\n    • ".join(f"✅ {step}" for step in successful_steps)
            final_message = (
                f"\n🎉 Full registration completed successfully! 🎊\n"
                f"👟 Steps ({success_count}/{total_steps}):\n{steps_list}"
            )
            await self.logger_msg(final_message, "success", self.wallet_address)
            return True, final_message

        elif success_count == 0:
            # Все этапы провалились ❌
            steps_list = "\n    • " + "\n    • ".join(f"❌ {step}" for step in failed_steps)
            final_message = (
                f"\n💥 Full registration failed completely!\n"
                f"  Failed steps ({total_steps}):\n{steps_list}"
            )
            await self.logger_msg(final_message, "error", self.wallet_address)
            return False, final_message

        else:
            # Частичное выполнение (уже есть в твоем коде)
            steps_success = "\n    • " + "\n    • ".join(f"✅ {step}" for step in successful_steps) if successful_steps else ""
            steps_failed = "\n    • " + "\n    • ".join(f"❌ {step}" for step in failed_steps) if failed_steps else ""
            final_message = (
                f"\n!!!  Partial registration completed with warnings\n"
                f"  Success: {success_count}/{total_steps}\n"
                f"  Successful steps:{steps_success}\n"
                f"  Failed steps:{steps_failed}"
            )
            await self.logger_msg(final_message, "warning", self.wallet_address)
            return False, final_message
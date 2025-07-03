from src.tasks import *
from src.tasks.registration import *
from src.tasks.faucets import *
from src.tasks.pharos_tasks import *
from src.tasks.zenith import *
from src.models import Account


class PharosBot:
    @staticmethod
    async def process_auto_route(account: Account) -> tuple[bool, str]:
        """Обработчик для авто-роута"""
        from route_manager import process_route
        return await process_route(account)
     
    """ ---------------------------------- Statistics Account -----------------------------------------"""
    @staticmethod
    async def process_statistics_account(account: Account) -> tuple[bool, str]:
        async with StatisticsAccount(account) as account:
            return await account.run_statistics_account()
        
    """ -------------------- Registration on Pharos Network site --------------------"""
    @staticmethod
    async def process_full_registration(account: Account) -> tuple[bool, str]:
        registration  = FullRegistrationPharos(account)
        return await registration.run_full_registration()
    
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
    
    """ -------------------- Fulfilling twitter tasks on Pharos Network site --------------------"""
    @staticmethod
    async def process_twitter_tasks(account: Account) -> tuple[bool, str]:
        async with TwitterTasks(account) as worker:
            return await worker.run_twitter_tasks()
        
    """ ---------------------------------- Daily Check-in -----------------------------------------"""
    @staticmethod
    async def process_daily_check_in(account: Account) -> tuple[bool, str]:
        async with DailyCheckIn(account) as worker:
            return await worker.run_daily_check_in()
        
    """ ---------------------------------- Faucets -----------------------------------------"""
    @staticmethod
    async def process_full_faucets(account: Account) -> tuple[bool, str]:
        faucets = FullFaucets(account)
        return await faucets.run_faucets()
        
    @staticmethod
    async def process_phrs_faucet(account: Account) -> tuple[bool, str]:
        async with OfficialFaucet(account) as faucet:
            return await faucet.run_faucet()
        
    @staticmethod
    async def process_zenith_faucet(account: Account) -> tuple[bool, str]:
        async with ZenithFaucet(account) as faucet:
            return await faucet.run_faucet()
        
    """ ---------------------------------- Onchain -----------------------------------------"""
    @staticmethod
    async def process_send_to_friends(account: Account) -> tuple[bool, str]:
        async with SendToFriends(account) as onchain:
            return await onchain.run_send_to_friends()
        
    @staticmethod
    async def process_mint_pharos_badge(account: Account) -> tuple[bool, str]:
        async with PharosBadge(account) as onchain:
            return await onchain.run_mint_pharos_badge()
        
    @staticmethod
    async def process_mint_pharos_nft(account: Account) -> tuple[bool, str]:
        async with PharosNft(account) as onchain:
            return await onchain.run_mint_pharos_nft()
        
    """ ---------------------------------- Zenith Finance -----------------------------------------"""
    @staticmethod
    async def process_connect_twitter_zenith(account: Account) -> tuple[bool, str]:
        twitter = ConnectTwitterZenith(account)
        return await twitter.run_connect_twitter()
    
    @staticmethod
    async def process_swap_zenith(account: Account) -> tuple[bool, str]:
        twitter = ZenithSwapModule(account)
        return await twitter.run_swap()
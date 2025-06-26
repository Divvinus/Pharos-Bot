import asyncio
import random

from eth_account import Account

from src.logger import AsyncLogger


async def random_sleep(
    address: str | None = None, 
    min_sec: int = 30, 
    max_sec: int = 60
) -> None:
    logger = AsyncLogger()
    delay = random.uniform(min_sec, max_sec)
    
    minutes, seconds = divmod(delay, 60)
    template = (
        f"Sleep "
        f"{int(minutes)} minutes {seconds:.1f} seconds" if minutes > 0 else 
        f"Sleep {seconds:.1f} seconds"
    )
    await logger.logger_msg(template, type_msg="info", address=address)
    
    chunk_size = 0.1
    chunks = int(delay / chunk_size)
    remainder = delay - (chunks * chunk_size)
    
    try:
        for _ in range(chunks):
            await asyncio.sleep(chunk_size)
            
        if remainder > 0:
            await asyncio.sleep(remainder)
            
    except asyncio.CancelledError:
        await logger.logger_msg(
            f"Sleep interrupted", type_msg="warning", address=address
        )
        raise

_ACCOUNT = Account()
Account.enable_unaudited_hdwallet_features()

def get_address(mnemonic: str) -> str:
    normalized_mnemonic = ' '.join(word for word in mnemonic.split() if word)
    
    if len(normalized_mnemonic.split()) in (12, 24):
        return _ACCOUNT.from_mnemonic(normalized_mnemonic).address
    else:
        if not mnemonic.startswith('0x'):
            mnemonic = '0x' + mnemonic
        return _ACCOUNT.from_key(mnemonic).address
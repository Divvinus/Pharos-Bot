import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import json

class ContractError(Exception):
    """Base exception for contract-related errors"""
    pass

@dataclass(slots=True)
class BaseContract:
    address: str
    abi_file: str = "erc_20.json"
    
    _abi_path: ClassVar[Path] = Path("./abi")
    _abi_subdir: ClassVar[str] = ""

    async def get_abi(self) -> list[dict[str, Any]]:
        directory = self._abi_path / self._abi_subdir
        file_path = directory / self.abi_file
        try:
            content = await asyncio.to_thread(file_path.read_bytes)
            abi_data = json.loads(content)
            
            if not isinstance(abi_data, list):
                raise ContractError(f"Invalid ABI structure in {file_path}")
                
            return abi_data
        except FileNotFoundError as e:
            raise ContractError(f"ABI file not found: {file_path}") from e
        except json.JSONDecodeError as e:
            raise ContractError(f"Invalid JSON in ABI file: {file_path}") from e

@dataclass(slots=True)
class ERC20Contract(BaseContract):
    address: str = ""
    abi_file: str = "erc_20.json"
    
@dataclass(slots=True)
class HypurrContract(BaseContract):
    address: str = "0xB96f07367e69e86d6e9C3F29215885104813eeAE"
    abi_file: str = "hypurr.json"
    
@dataclass(slots=True)
class GotchipusNFTContract(BaseContract):
    address: str = "0x0000000038f050528452d6da1e7aacfa7b3ec0a8"
    abi_file: str = "gotchipus_nft.json"
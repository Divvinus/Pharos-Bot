import json
from pathlib import Path
from typing import Self

from better_proxy import Proxy
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)


class Account:
    __slots__ = (
        'keypair',
        'proxy',
        'auth_tokens_twitter',
        'auth_tokens_discord',
    )

    def __init__(
        self,
        keypair: str,
        proxy: Proxy | None = None,
        auth_tokens_twitter: str | None = None,
        auth_tokens_discord: str | None = None,
    ) -> None:
        self.keypair = keypair
        self.proxy = proxy
        self.auth_tokens_twitter = auth_tokens_twitter
        self.auth_tokens_discord = auth_tokens_discord
    def __repr__(self) -> str:
        return f'Account({self.keypair!r})'


class DelayRange(BaseModel):
    min: int
    max: int

    @field_validator('max')
    @classmethod
    def validate_max(cls, value: int, info: ValidationInfo) -> int:
        if value < info.data['min']:
            raise ValueError('max must be greater than or equal to min')
        return value

    model_config = ConfigDict(frozen=True)


class PercentRange(BaseModel):
    min: int = Field(ge=0, le=100)
    max: int = Field(ge=0, le=100)

    @field_validator('max')
    @classmethod
    def validate_max(cls, value: int, info: ValidationInfo) -> int:
        if value < info.data['min']:
            raise ValueError('max must be greater than or equal to min')
        return value
    

class Config(BaseModel):
    accounts: list[Account] = Field(default_factory=list)
    threads: int
    
    delay_before_start: DelayRange
    delay_between_tasks: DelayRange
    
    tg_token: str = ""
    tg_id: str = ""
    send_stats_to_telegram: bool = False
    
    pharos_rpc_endpoints: list[str] = []
    pharos_evm_explorer: str = ""
    
    module: str = ""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='forbid',
    )

    @classmethod
    def load(cls, config_path: str | Path) -> Self:
        if isinstance(config_path, str):
            config_path = Path(config_path)
        
        try:
            raw_data = json.loads(config_path.read_text)
            return cls.model_validate(raw_data)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Config file not found: {config_path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {config_path}") from e
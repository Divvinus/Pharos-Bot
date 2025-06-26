import random
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import openpyxl
from better_proxy import Proxy
from ruamel.yaml import YAML

from configs import SHUFFLE_WALLETS
from src.exceptions.configuration_exceptions import ConfigurationError
from src.models import Account, Config


yaml = YAML(typ='safe')


@dataclass
class FileData:
    path: Path
    required: bool = True
    allow_empty: bool = False


class ConfigLoader:
    REQUIRED_PARAMS: set[str] = frozenset({
        'threads',
        'delay_before_start',
        'delay_between_tasks'
    })

    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path or Path(__file__).parent.parent.parent)
        self.config_path = self.base_path / 'config'
        self.settings_path = self.config_path / 'settings.yaml'
        self.xlsx_paths = {
            'accounts': FileData(self.config_path / 'accounts.xlsx')
        }

    def _load_yaml(self) -> dict:
        try:
            with open(self.settings_path, 'r', encoding='utf-8') as file:
                config = yaml.load(file)
            
            if not isinstance(config, dict):
                raise ConfigurationError('Configuration must be a dictionary')
            
            missing_fields = self.REQUIRED_PARAMS - set(config.keys())
            if missing_fields:
                raise ConfigurationError(
                    f'Missing required fields: {", ".join(missing_fields)}'
                )
            
            if 'delay_between_tasks' not in config:
                config['delay_between_tasks'] = {'min': 30, 'max': 120}
            
            return config
        
        except Exception as error:
            raise ConfigurationError(
                f'Error loading configuration: {error}'
            ) from error

    def _get_accounts(self) -> Generator[Account, None, None]:
        accounts_path = self.xlsx_paths['accounts'].path
        
        if not accounts_path.exists():
            raise ConfigurationError(f'Accounts file not found: {accounts_path}')
        
        wb = openpyxl.load_workbook(accounts_path, read_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        
        try:
            header = next(rows)
        except StopIteration:
            raise ConfigurationError('Accounts file is empty')
        
        col_map = {
            cell.strip(): idx 
            for idx, cell in enumerate(header) 
            if cell
        }
        
        required_cols = {'Key Pair'}
        for col in required_cols:
            if col not in col_map:
                raise ConfigurationError(f'Missing required column: {col}')
        
        for row in rows:
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            
            keypair = row[col_map['Key Pair']]
            if not keypair or str(keypair).strip() == '':
                continue
            
            keypair = str(keypair).strip()
            proxy_str = (
                row[col_map.get('Proxy')] 
                if 'Proxy' in col_map 
                else None
            )
            
            proxy = None
            if proxy_str:
                proxy = Proxy.from_str(str(proxy_str).strip())
                
            twitter_token = (
                row[col_map.get('Twitter Token')] 
                if 'Twitter Token' in col_map 
                else None
            )
            
            discord_token = (
                row[col_map.get('Discord Token')] 
                if 'Discord Token' in col_map 
                else None
            )
            
            yield Account(
                keypair=keypair,
                proxy=proxy,
                auth_tokens_twitter=(
                    str(twitter_token).strip() 
                    if twitter_token 
                    else None
                ),
                auth_tokens_discord=(
                    str(discord_token).strip() 
                    if discord_token 
                    else None
                ),
            )

    def load(self) -> Config:
        try:
            params = self._load_yaml()
            accounts = list(self._get_accounts())
            
            if not accounts:
                raise ConfigurationError('No valid accounts found')
            
            if SHUFFLE_WALLETS:
                random.shuffle(accounts)
            
            return Config(accounts=accounts, **params)
        
        except ConfigurationError as error:
            raise ConfigurationError(
                f'Configuration error: {error}'
            ) from error
        
        except Exception as error:
            raise ConfigurationError(
                f'Unexpected error during configuration loading: {error}'
            ) from error
            exit(1)


def load_config() -> Config:
    return ConfigLoader().load()
"""
Модели и конфигурации для работы с Twitter API.
"""

from dataclasses import dataclass
from typing import Protocol, Optional, Any


class Account(Protocol):
    """Протокол аккаунта, который будет использоваться в Twitter-клиентах."""
    auth_tokens_twitter: str
    proxy: Any
    keypair: Any


@dataclass(frozen=True)
class TwitterConfig:
    """Базовая конфигурация параметров Twitter."""
    # Общие параметры для всех платформ
    BEARER_TOKEN: str = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    API_DOMAIN: str = "twitter.com"
    OAUTH2_PATH: str = "/i/api/2/oauth2/authorize"


@dataclass(frozen=True)
class PharosTwitterConfig(TwitterConfig):
    """Конфигурация параметров авторизации Twitter для Pharos."""
    CLIENT_ID: str = "TGQwNktPQWlBQzNNd1hyVkFvZ2E6MTpjaQ"
    REDIRECT_URI: str = "https://testnet.pharosnetwork.xyz"
    REQUIRED_SCOPES: str = "users.read tweet.read follows.read"


@dataclass(frozen=True)
class ZenithTwitterConfig(TwitterConfig):
    """Конфигурация параметров авторизации Twitter для Zenith."""
    CLIENT_ID: str = "V29kYkpGVUpEYXAxXzUtMzdpLTU6MTpjaQ"
    REDIRECT_URI: str = "https://testnet-router.zenithswap.xyz/api/v1/oauth2/twitter/callback"
    REQUIRED_SCOPES: str = "tweet.read tweet.write follows.read follows.write like.read like.write users.read offline.access"
    ZENITH_TWITTER_ID: int = 1909913609838411776
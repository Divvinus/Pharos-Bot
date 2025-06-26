"""
Twitter API клиенты для взаимодействия с различными платформами.
Предоставляет унифицированный интерфейс для авторизации Twitter-аккаунта и
привязки его к различным платформам.
"""

from src.twitter.models import TwitterConfig, Account
from src.twitter.exceptions import (
    TwitterClientError,
    TwitterAuthError,
    TwitterNetworkError,
    TwitterInvalidTokenError, 
    TwitterAccountSuspendedError,
    TwitterAlreadyConnectedError,
    TwitterRateLimitError,
    TwitterAlreadyDoneError,
    TwitterActionBlockedError,
    TwitterAPIError,
)
from src.twitter.utils import TwitterWorker

__all__ = [
    # Клиенты для платформ
    "ConnectTwitterPharos", 
    "ConnectTwitterZenith",
    # Модели и конфигурации
    "TwitterConfig",
    "Account",
    # Исключения
    "TwitterClientError",
    "TwitterBaseException",
    "TwitterAuthError",
    "TwitterNetworkError",
    "TwitterInvalidTokenError", 
    "TwitterAccountSuspendedError",
    "TwitterAlreadyConnectedError",
    "TwitterRateLimitError",
    "TwitterAlreadyDoneError",
    "TwitterActionBlockedError",
    "TwitterAPIError",
    # Утилиты
    "TwitterWorker",
]
"""
Базовый класс для работы с Twitter API.
"""

import aiohttp
from abc import ABC, abstractmethod
from typing import Tuple, Optional, Dict, Any
from urllib.parse import parse_qs, urlparse

from Jam_Twitter_API.account_sync import TwitterAccountSync
from Jam_Twitter_API.errors import TwitterError, TwitterAccountSuspended, IncorrectData

from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.logger import AsyncLogger
from src.models import Account
from src.utils import save_bad_twitter_token, get_address, random_sleep

from src.twitter.exceptions import (
    TwitterAuthError,
    TwitterNetworkError, 
    TwitterInvalidTokenError,
    TwitterAccountSuspendedError,
)
from src.twitter.models import TwitterConfig
from src.twitter.utils import make_request, Headers


class TwitterBaseClient(AsyncLogger, ABC):
    """Базовый класс для Twitter-клиентов."""
    
    TASK_MSG = "Connect Twitter account"
    
    def __init__(self, account: Account, config: TwitterConfig) -> None:
        """
        Инициализация клиента Twitter.
        
        Args:
            account: Объект аккаунта с токеном Twitter
            config: Конфигурация Twitter API
        """
        AsyncLogger.__init__(self)
        self.account = account
        self.config = config
        self.twitter_client = None
        self.session = None
        self._wallet_address: Optional[str] = None
        
    @property
    def wallet_address(self) -> str:
        """Получение адреса кошелька."""
        if self._wallet_address is None:
            self._wallet_address = get_address(self.account.keypair)
        return self._wallet_address
        
    @abstractmethod
    def get_platform_headers(self) -> Headers:
        """
        Получение заголовков для запросов к платформе.
        
        Returns:
            Headers: HTTP-заголовки
        """
        pass
        
    def get_twitter_headers(self, csrf_token: str) -> Headers:
        """
        Заголовки для запросов к Twitter API.
        
        Args:
            csrf_token: CSRF-токен для Twitter
            
        Returns:
            Headers: HTTP-заголовки для Twitter API
        """
        return {
            'authority': self.config.API_DOMAIN,
            'accept': '*/*',
            'authorization': f'Bearer {self.config.BEARER_TOKEN}',
            'cookie': f'auth_token={self.account.auth_tokens_twitter}; ct0={csrf_token}',
            'x-csrf-token': csrf_token,
            'origin': f'https://{self.config.API_DOMAIN}',
            'referer': f'https://{self.config.API_DOMAIN}/i/oauth2/authorize',
            'x-twitter-auth-type': 'OAuth2Session',
            'x-twitter-active-user': 'yes',
            'content-type': 'application/x-www-form-urlencoded'
        }
        
    async def _handle_sync_errors(self, error: TwitterError) -> None:
        """
        Обработка ошибок синхронизации аккаунта.
        
        Args:
            error: Объект ошибки TwitterError
            
        Raises:
            TwitterAccountSuspendedError: Если аккаунт заблокирован
            TwitterInvalidTokenError: При недействительном токене
            TwitterAuthError: При других ошибках авторизации
        """
        if isinstance(error, TwitterAccountSuspended):
            await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
            raise TwitterAccountSuspendedError(f"Twitter account blocked or suspended")

        error_code = getattr(error, 'error_code', None)
        if error_code in (32, 89, 215, 326) or isinstance(error, IncorrectData):
            await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
            raise TwitterInvalidTokenError(f"Invalid Twitter authorization token")
    
    async def _initialize_twitter_client(self) -> TwitterAccountSync:
        """
        Инициализация синхронного клиента Twitter.
        
        Returns:
            TwitterAccountSync: Клиент для синхронизации с Twitter
            
        Raises:
            TwitterAuthError: При ошибках авторизации
        """
        try:
            return TwitterAccountSync.run(
                auth_token=self.account.auth_tokens_twitter,
                proxy=self.account.proxy.as_url,
                setup_session=True
            )
        except TwitterError as error:
            await self._handle_sync_errors(error)
            raise TwitterAuthError(f"Twitter client initialization error")
    
    async def _make_request(self, method: str, url: str, headers: Headers = None, **kwargs) -> aiohttp.ClientResponse:
        """
        Выполнение HTTP-запроса с повторными попытками.
        
        Args:
            method: HTTP-метод (GET, POST)
            url: URL для запроса
            headers: HTTP-заголовки
            **kwargs: Дополнительные параметры запроса
            
        Returns:
            aiohttp.ClientResponse: Ответ сервера
            
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterNetworkError: При сетевых ошибках
        """
        return await make_request(self.session, method, url, headers, **kwargs)
    
    @abstractmethod
    async def link_twitter_account(self) -> str:
        """
        Основной метод для привязки Twitter-аккаунта.
        
        Returns:
            str: Сообщение о результате операции
            
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterNetworkError: При сетевых ошибках
            TwitterInvalidTokenError: При недействительном токене
            TwitterAccountSuspendedError: Если аккаунт заблокирован
        """
        pass
    
    async def run_connect_twitter(self) -> Tuple[bool, str]:
        """
        Основной метод для запуска процесса привязки Twitter-аккаунта.
        
        Returns:
            Tuple[bool, str]: (успех операции, сообщение о результате)
        """
        await self.logger_msg(f"Start {self.TASK_MSG}", "info", self.wallet_address)
        
        # Проверяем наличие токена
        if not self.account.auth_tokens_twitter:
            error_msg = "Twitter authorization token is missing"
            await self.logger_msg(error_msg, "error", self.wallet_address)
            return False, error_msg
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", 
                "info", 
                self.wallet_address
            )  
            
            try:
                # Создаем единую сессию для всех запросов
                self.session = aiohttp.ClientSession(proxy=self.account.proxy.as_url)
                
                try:
                    result_message = await self.link_twitter_account()
                    await self.logger_msg(
                        f"Task completed successfully: {result_message}", "success", self.wallet_address
                    )
                    return True, result_message
                finally:
                    # Закрываем сессию в любом случае
                    if self.session and not self.session.closed:
                        await self.session.close()
                
            except TwitterAccountSuspendedError:
                error_msg = "Twitter account blocked or suspended"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_connect_twitter")
                return False, error_msg
                
            except TwitterInvalidTokenError:
                error_msg = "Invalid or expired Twitter authorization token"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_connect_twitter")
                return False, error_msg
                
            except TwitterNetworkError:
                error_msg = f"Network error when trying {attempt + 1}: connection problems"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "run_connect_twitter")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    final_error = "Failed to connect to services after all attempts"
                    await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_twitter")
                    return False, final_error
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)
                
            except TwitterAuthError as e:
                error_msg = f"Authorization error on {attempt + 1}: {str(e)}"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "run_connect_twitter")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    final_error = "Authorization failed after all attempts"
                    await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_twitter")
                    return False, final_error
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)
                
            except Exception as e:
                error_msg = f"Unexpected error while trying to {attempt + 1}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_connect_twitter")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)

        # Если все попытки исчерпаны
        final_error = f"Task {self.TASK_MSG} failed after {MAX_RETRY_ATTEMPTS} attempts"
        await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_twitter")
        return False, final_error
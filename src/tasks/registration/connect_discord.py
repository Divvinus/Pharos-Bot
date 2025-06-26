import aiohttp
import asyncio
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.exceptions.discord_exceptions import (
    DiscordAuthError,
    DiscordNetworkError,
    DiscordInvalidTokenError,
    DiscordServerError,
    DiscordRateLimitError,
)
from src.logger import AsyncLogger
from src.models import Account
from src.utils import save_bad_discord_token, get_address, random_sleep


# Тип для HTTP-заголовков
Headers = dict[str, str]


@dataclass(frozen=True)
class DiscordAuthConfig:
    """Конфигурация параметров авторизации Discord"""
    CLIENT_ID: str = "1372430524521644062"
    GUILD_ID: str = "1374448020074139668"
    REDIRECT_URI: str = "https://testnet.pharosnetwork.xyz/experience"
    BASE_URL: str = "https://discord.com"
    API_URL: str = f"{BASE_URL}/api/v9"
    OAUTH_PATH: str = "/oauth2/authorize"
    REQUIRED_SCOPES: str = "identify"
    SUPER_PROPERTIES: str = "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6InJ1IiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZSwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTI5LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6Imh0dHBzOi8vdGVzdG5ldC5waGFyb3NuZXR3b3JrLnh5ei8iLCJyZWZlcnJpbmdfZG9tYWluX2N1cnJlbnQiOiJ0ZXN0bmV0LnBoYXJvc25ldHdvcmsueHl6IiwicmVsZWFzZV9jaGFubmVsIjoic3RhYmxlIiwiY2xpZW50X2J1aWxkX251bWJlciI6NDA1MjA5LCJjbGllbnRfZXZlbnRfc291cmNlIjpudWxsLCJjbGllbnRfbGF1bmNoX2lkIjoiNDU4NmJmOWQtOGNhMi00NjM3LWFjZTYtY2QwZmMyNTVkMjdhIiwiY2xpZW50X2FwcF9zdGF0ZSI6ImZvY3VzZWQifQ=="


class ConnectDiscordPharos(AsyncLogger):
    """Клиент для взаимодействия с Discord API"""
    TASK_MSG = "Connect discord on Pharos Network site"
    
    def __init__(self, account: Account) -> None:
        """Инициализация с объектом аккаунта"""
        AsyncLogger.__init__(self)
        self.account = account
        self._wallet_address: str | None = None 
        self.session = None
        self._config = DiscordAuthConfig()
        
    @property
    def wallet_address(self) -> str:
        if self._wallet_address is None:
            self._wallet_address = get_address(self.account.keypair)
        return self._wallet_address
    
    def get_pharos_headers(self) -> Headers:
        """Заголовки для запросов к Pharos API"""
        return {
            'authority': "api.pharosnetwork.xyz",
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': "https://testnet.pharosnetwork.xyz",
            'referer': "https://testnet.pharosnetwork.xyz/"
        }

    def get_discord_headers(self) -> Headers:
        """Заголовки для запросов к Discord API"""
        return {
            'authority': 'discord.com',
            'accept': '*/*',
            'authorization': self.account.auth_tokens_discord,
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'dnt': '1',
            'origin': 'https://discord.com',
            'pragma': 'no-cache',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-debug-options': 'bugReporterEnabled',
            'x-super-properties': self._config.SUPER_PROPERTIES
        }

    def _build_auth_params(self, code_challenge: str, state: str) -> dict[str, str]:
        """Параметры для OAuth-авторизации"""
        return {
            "client_id": self._config.CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self._config.REDIRECT_URI,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": self._config.REQUIRED_SCOPES,
            "state": state
        }

    def _build_referer_url(self, params: dict[str, str]) -> str:
        """Построение URL для Referer заголовка"""
        query_parts = []
        for key, value in params.items():
            query_parts.append(f"{key}={value}")
        query_string = "&".join(query_parts)
        return f"{self._config.BASE_URL}{self._config.OAUTH_PATH}?{query_string}"

    @staticmethod
    def _extract_auth_code(redirect_url: str) -> str:
        """Извлечение кода авторизации из URL перенаправления"""
        parsed_url = urlparse(redirect_url)
        query_params = parse_qs(parsed_url.query)
        return query_params.get('code', [''])[0]

    async def _make_request(
        self, 
        method: str, 
        url: str, 
        headers: Headers = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """Выполнение HTTP-запроса с повторными попытками и обновлением заголовков"""
        last_error = None
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # Обновляем заголовки сессии если переданы новые
                if headers:
                    self.session.headers.update(headers)
                
                # Выполняем запрос
                if method.lower() == 'get':
                    response = await self.session.get(url, **kwargs, ssl=False)
                elif method.lower() == 'post':
                    response = await self.session.post(url, **kwargs, ssl=False)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                return response
                
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, 
                    aiohttp.ClientOSError, asyncio.TimeoutError) as error:
                last_error = error
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await random_sleep("Account", *RETRY_SLEEP_RANGE)
                else:
                    break
            
            except Exception as error:
                raise DiscordAuthError(f"Unexpected error while executing a query: {str(error)}")
        
        # Обработка сетевых ошибок после всех попыток
        error_msg = str(last_error)
        if any(term in error_msg.lower() for term in ["forcibly severed", "connection", "ssl", "host"]):
            raise DiscordNetworkError(f"Network connection error after {MAX_RETRY_ATTEMPTS} attempts")
        raise DiscordNetworkError(f"Unknown network error: {error_msg}")

    async def _get_oauth_parameters(self) -> tuple[str, str]:
        """Получение параметров для OAuth-авторизации"""
        try:
            # Устанавливаем заголовки для Pharos API
            response = await self._make_request(
                "get",
                "https://api.pharosnetwork.xyz/auth/discord",
                headers=self.get_pharos_headers(),
                allow_redirects=False
            )
            
            async with response:
                if response.status != 307:
                    raise DiscordAuthError(f"Unexpected status when retrieving OAuth parameters: {response.status}")
                
                location = response.headers.get("Location", "")
                if not location:
                    raise DiscordAuthError("No redirect URL for OAuth was received")
                
                parsed_url = urlparse(location)
                query_params = parse_qs(parsed_url.query)
                code_challenge = query_params.get("code_challenge", [""])[0]
                state = query_params.get("state", [""])[0]
                
                if not code_challenge or not state:
                    raise DiscordAuthError("The required OAuth parameters have not been received")
                
                return code_challenge, state
                
        except DiscordAuthError:
            raise
        except Exception as error:
            raise DiscordNetworkError(f"Error retrieving OAuth parameters: {str(error)}")

    async def link_discord_account(self) -> str:
        """Основной метод для привязки Discord-аккаунта"""
        # Создаем единую сессию для всех запросов
        self.session = aiohttp.ClientSession(proxy=self.account.proxy.as_url)
        
        try:
            # Шаг 1: Получение параметров авторизации
            code_challenge, state = await self._get_oauth_parameters()
            
            # Шаг 2: Подготовка данных для авторизации
            auth_params = self._build_auth_params(code_challenge, state)
            referer_url = self._build_referer_url(auth_params)
            discord_headers = self.get_discord_headers()
            discord_headers['referer'] = referer_url
            
            auth_url = f"{self._config.API_URL}{self._config.OAUTH_PATH}"
            
            # Шаг 3: Запрос авторизации к Discord API
            auth_payload = {
                "guild_id": self._config.GUILD_ID,
                "permissions": "0",
                "authorize": True,
                "integration_type": 0,
                "location_context": {
                    "guild_id": "10000",
                    "channel_id": "10000",
                    "channel_type": 10000
                },
                "dm_settings": {
                    "allow_mobile_push": False
                }
            }
            
            auth_response = await self._make_request(
                'post', 
                auth_url,
                headers=discord_headers,
                params=auth_params,
                json=auth_payload,
                allow_redirects=False
            )
            
            async with auth_response:
                if auth_response.status == 401 or auth_response.status == 403:
                    await save_bad_discord_token(self.account.auth_tokens_discord, self.wallet_address)
                    raise DiscordInvalidTokenError("Invalid Discord credentials")
                elif auth_response.status >= 500:
                    raise DiscordServerError(f"Discord server error (status: {auth_response.status})")
                elif auth_response.status == 429:
                    raise DiscordRateLimitError("Discord rate limit exceeded")
                elif auth_response.status != 200:
                    raise DiscordAuthError(f"Discord authorization error (status: {auth_response.status})")
                
                try:
                    auth_data = await auth_response.json()
                except Exception:
                    raise DiscordAuthError("Received incorrect response from Discord API")
                
                redirect_url = auth_data.get('location')
                if not redirect_url:
                    raise DiscordAuthError("No redirect URL received from Discord")
                
                final_auth_code = self._extract_auth_code(redirect_url)
                if not final_auth_code:
                    raise DiscordAuthError("Failed to extract authorization code from redirect URL")
            
            # Шаг 4: Привязка аккаунта к Pharos
            bind_payload = {
                'state': state, 
                'code': final_auth_code, 
                'address': self.wallet_address
            }
            
            bind_response = await self._make_request(
                "post",
                "https://api.pharosnetwork.xyz/auth/bind/discord",
                headers=self.get_pharos_headers(),
                json=bind_payload
            )
            
            async with bind_response:
                if bind_response.status == 200:
                    return "Discord account successfully linked to Pharos Network"
                elif bind_response.status == 400:
                    try:
                        error_data = await bind_response.json()
                        error_message = error_data.get('message', 'Unknown error')
                        raise DiscordAuthError(f"Account linking error: {error_message}")
                    except Exception:
                        raise DiscordAuthError("Account linking error: invalid data")
                elif bind_response.status == 401 or bind_response.status == 403:
                    await save_bad_discord_token(self.account.auth_tokens_discord, self.wallet_address)
                    raise DiscordInvalidTokenError("Access denied on account linking")
                elif bind_response.status == 409:
                    raise DiscordAuthError("The Discord account is already linked to another wallet")
                else:
                    raise DiscordAuthError(f"Account binding error (status: {bind_response.status})")
                        
        finally:
            # Закрываем сессию в любом случае
            if self.session and not self.session.closed:
                await self.session.close()

    async def run_connect_discord(self) -> tuple[bool, str]:
        await self.logger_msg(f"Start {self.TASK_MSG}", "info", self.wallet_address)
        
        # Проверяем наличие токена
        if not self.account.auth_tokens_discord:
            error_msg = "Discord authorization token is missing"
            await self.logger_msg(error_msg, "error", self.wallet_address)
            return False, error_msg
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            await self.logger_msg(
                f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
            )  
            
            try:
                result_message = await self.link_discord_account()
                await self.logger_msg(
                    f"Task completed successfully: {result_message}", "success", self.wallet_address
                )
                return True, result_message
                
            except DiscordInvalidTokenError as e:
                error_msg = "Invalid or expired Discord authorization token"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_connect_discord")
                return False, error_msg
                
            except DiscordServerError as e:
                error_msg = f"Discord server error on attempt {attempt + 1}: {str(e)}"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "run_connect_discord")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    final_error = "Discord server error after all attempts"
                    await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_discord")
                    return False, final_error
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)
                
            except DiscordRateLimitError as e:
                error_msg = f"Discord rate limit on attempt {attempt + 1}: waiting before retry"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "run_connect_discord")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    final_error = "Discord rate limit exceeded after all attempts"
                    await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_discord")
                    return False, final_error
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)
                
            except DiscordNetworkError as e:
                error_msg = f"Network error when trying {attempt + 1}: connection problems"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "run_connect_discord")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    final_error = "Failed to connect to services after all attempts"
                    await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_discord")
                    return False, final_error
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)
                
            except DiscordAuthError as e:
                error_msg = f"Authorization error on {attempt + 1}: {str(e)}"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "run_connect_discord")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    final_error = "Authorization failed after all attempts"
                    await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_discord")
                    return False, final_error
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)
                
            except Exception as e:
                error_msg = f"Unexpected error while trying to {attempt + 1}: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run_connect_discord")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                    
                await random_sleep("Account", *RETRY_SLEEP_RANGE)

        # Если все попытки исчерпаны
        final_error = f"Task {self.TASK_MSG} failed after {MAX_RETRY_ATTEMPTS} attempts"
        await self.logger_msg(final_error, "error", self.wallet_address, "run_connect_discord")
        return False, final_error
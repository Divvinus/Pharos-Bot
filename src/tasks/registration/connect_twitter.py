"""
Клиент для подключения Twitter к платформе Pharos Network.
"""

from urllib.parse import parse_qs, urlparse

from src.utils import save_bad_twitter_token

from src.twitter.base import TwitterBaseClient
from src.twitter.exceptions import (
    TwitterAuthError,
    TwitterNetworkError,
    TwitterInvalidTokenError,
)
from src.twitter.models import PharosTwitterConfig, Account
from src.twitter.utils import Headers


class ConnectTwitterPharos(TwitterBaseClient):
    """Клиент для привязки Twitter к Pharos Network."""
    
    TASK_MSG = "Connect twitter on Pharos Network site"
    
    def __init__(self, account: Account) -> None:
        """
        Инициализация клиента для Pharos Network.
        
        Args:
            account: Объект аккаунта с токеном Twitter
        """
        super().__init__(account, PharosTwitterConfig())
    
    def get_platform_headers(self) -> Headers:
        """
        Заголовки для запросов к Pharos API.
        
        Returns:
            Headers: HTTP-заголовки для Pharos API
        """
        return {
            'authority': "api.pharosnetwork.xyz",
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': "https://testnet.pharosnetwork.xyz",
            'referer': "https://testnet.pharosnetwork.xyz/"
        }

    def _build_auth_params(self, code_challenge: str, state: str) -> dict[str, str]:
        """
        Параметры для OAuth-авторизации.
        
        Args:
            code_challenge: Код проверки для OAuth2 PKCE
            state: Состояние для OAuth2
            
        Returns:
            dict[str, str]: Параметры для OAuth-авторизации
        """
        return {
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "client_id": self.config.CLIENT_ID,
            "redirect_uri": self.config.REDIRECT_URI,
            "response_type": "code",
            "scope": self.config.REQUIRED_SCOPES,
            "state": state
        }

    @staticmethod
    def _extract_auth_code(redirect_url: str) -> str:
        """
        Извлечение кода авторизации из URL перенаправления.
        
        Args:
            redirect_url: URL перенаправления
            
        Returns:
            str: Код авторизации
        """
        parsed_url = urlparse(redirect_url)
        query_params = parse_qs(parsed_url.query)
        return query_params.get('code', [''])[0]

    async def _get_oauth_parameters(self) -> tuple[str, str]:
        """
        Получение параметров для OAuth-авторизации.
        
        Returns:
            tuple[str, str]: (code_challenge, state)
            
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterNetworkError: При сетевых ошибках
        """
        try:
            # Устанавливаем заголовки для Pharos API
            response = await self._make_request(
                "get",
                "https://api.pharosnetwork.xyz/auth/twitter",
                headers=self.get_platform_headers(),
                allow_redirects=False
            )
            
            async with response:
                if response.status != 307:
                    raise TwitterAuthError(f"Unexpected status when retrieving OAuth parameters: {response.status}")
                
                location = response.headers.get("Location", "")
                if not location:
                    raise TwitterAuthError("No redirect URL for OAuth was received")
                
                parsed_url = urlparse(location)
                query_params = parse_qs(parsed_url.query)
                code_challenge = query_params.get("code_challenge", [""])[0]
                state = query_params.get("state", [""])[0]
                
                if not code_challenge or not state:
                    raise TwitterAuthError("The required OAuth parameters have not been received")
                
                return code_challenge, state
                
        except TwitterAuthError:
            raise
        except Exception as error:
            raise TwitterNetworkError(f"Error retrieving OAuth parameters: {str(error)}")

    async def link_twitter_account(self) -> str:
        """
        Основной метод для привязки Twitter-аккаунта к Pharos.
        
        Returns:
            str: Сообщение о результате операции
            
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterNetworkError: При сетевых ошибках
            TwitterInvalidTokenError: При недействительном токене
        """
        # Шаг 1: Инициализация клиента Twitter
        twitter_client = await self._initialize_twitter_client()
        twitter_headers = self.get_twitter_headers(twitter_client.ct0)
        auth_url = f"https://{self.config.API_DOMAIN}{self.config.OAUTH2_PATH}"
        
        # Шаг 2: Получение параметров авторизации
        code_challenge, state = await self._get_oauth_parameters()
        
        # Шаг 3: Запрос авторизации к Twitter
        auth_response = await self._make_request(
            'get', 
            auth_url,
            headers=twitter_headers,
            params=self._build_auth_params(code_challenge, state)
        )
        
        async with auth_response:
            if auth_response.status == 401 or auth_response.status == 403:
                await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
                raise TwitterInvalidTokenError("Invalid Twitter credentials")
            elif auth_response.status != 200:
                raise TwitterAuthError(f"Twitter authorization error (status: {auth_response.status})")
            
            try:
                auth_data = await auth_response.json()
            except Exception:
                raise TwitterAuthError("Received incorrect response from Twitter API")
            
            auth_code = auth_data.get('auth_code')
            if not auth_code:
                raise TwitterAuthError("Did not receive authorization code from Twitter")
        
        # Шаг 4: Подтверждение авторизации
        approval_response = await self._make_request(
            'post', 
            auth_url,
            headers=twitter_headers,
            params={'approval': 'true', 'code': auth_code}
        )
        
        async with approval_response:
            if approval_response.status == 401 or approval_response.status == 403:
                await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
                raise TwitterInvalidTokenError("Twitter authorization confirmation error")
            elif approval_response.status != 200:
                raise TwitterAuthError(f"Authorization confirmation error (status: {approval_response.status})")
            
            try:
                approval_data = await approval_response.json()
            except Exception:
                raise TwitterAuthError("Incorrect response was received when confirming authorization")
            
            redirect_url = approval_data.get('redirect_uri', '')
            if not redirect_url:
                raise TwitterAuthError("No redirect URL received after authorization")
            
            final_auth_code = self._extract_auth_code(redirect_url)
            if not final_auth_code:
                raise TwitterAuthError("Failed to extract the final authorization code")
        
        # Шаг 5: Привязка аккаунта к Pharos
        bind_payload = {
            'state': state, 
            'code': final_auth_code, 
            'address': self.wallet_address
        }
        
        bind_response = await self._make_request(
            "post",
            "https://api.pharosnetwork.xyz/auth/bind/twitter",
            headers=self.get_platform_headers(),
            json=bind_payload
        )
        
        async with bind_response:
            if bind_response.status == 200:
                return "Twitter account successfully linked to Pharos Network"
            elif bind_response.status == 400:
                try:
                    error_data = await bind_response.json()
                    error_message = error_data.get('message', 'Unknown error')
                    raise TwitterAuthError(f"Account linking error: {error_message}")
                except Exception:
                    raise TwitterAuthError("Account linking error: invalid data")
            elif bind_response.status == 401 or bind_response.status == 403:
                await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
                raise TwitterInvalidTokenError("Access denied on account linking")
            elif bind_response.status == 409:
                raise TwitterAuthError("The Twitter account is already linked to another wallet")
            else:
                raise TwitterAuthError(f"Account binding error (status: {bind_response.status})")
"""
Клиент для подключения Twitter к платформе Zenith Finance.
"""

from urllib.parse import parse_qs, urlparse

from src.utils import save_bad_twitter_token

from src.twitter.base import TwitterBaseClient
from src.twitter.exceptions import (
    TwitterAuthError,
    TwitterNetworkError,
    TwitterInvalidTokenError,
    TwitterAlreadyConnectedError,
)
from src.twitter.models import ZenithTwitterConfig, Account
from src.twitter.utils import Headers, TwitterWorker


class ConnectTwitterZenith(TwitterBaseClient):
    """Клиент для привязки Twitter к Zenith Finance."""
    
    TASK_MSG = "Connect twitter on Zenith Finance site"
    
    def __init__(self, account: Account) -> None:
        """
        Инициализация клиента для Zenith Finance.
        
        Args:
            account: Объект аккаунта с токеном Twitter
        """
        super().__init__(account, ZenithTwitterConfig())
    
    def get_platform_headers(self) -> Headers:
        """
        Заголовки для запросов к Zenith API.
        
        Returns:
            Headers: HTTP-заголовки для Zenith API
        """
        return {
            'accept': '*/*',
            'origin': "https://testnet.zenithfinance.xyz",
            'referer': "https://testnet.zenithfinance.xyz/",
            'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        }

    async def _get_oauth_url(self) -> tuple[str, str]:
        """
        Получение URL для OAuth-авторизации и code_challenge.
        
        Returns:
            tuple[str, str]: (oauth_url, code_challenge)
            
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterNetworkError: При сетевых ошибках
            TwitterAlreadyConnectedError: Если аккаунт уже привязан
        """
        try:
            # Запрос к Zenith API для получения URL авторизации
            url = f"https://testnet-router.zenithswap.xyz/api/v1/oauth2/twitter_url?wallet={self.wallet_address}"
            response = await self._make_request(
                "get",
                url,
                headers=self.get_platform_headers(),
            )
            
            async with response:
                if response.status != 200:
                    raise TwitterAuthError(f"Failed to get OAuth URL: status {response.status}")
                
                try:
                    response_data = await response.json()
                except Exception:
                    raise TwitterAuthError("Invalid response format when getting OAuth URL")
                
                if response_data.get('status') != 200:
                    raise TwitterAuthError(f"API error: {response_data.get('message', 'Unknown error')}")
                
                data = response_data.get('data', {})
                oauth_url = data.get('url', '')
                state = data.get('state')
                
                # Проверяем случай, когда аккаунт уже привязан (пустой URL и state = 1)
                if not oauth_url and state == 1:
                    raise TwitterAlreadyConnectedError()
                
                if not oauth_url:
                    raise TwitterAuthError("No OAuth URL received")
                
                # Извлекаем code_challenge из URL
                parsed_url = urlparse(oauth_url)
                query_params = parse_qs(parsed_url.query)
                code_challenge = query_params.get('code_challenge', [''])[0]
                
                if not code_challenge:
                    raise TwitterAuthError("No code_challenge found in OAuth URL")
                
                return oauth_url, code_challenge
                
        except Exception as error:
            if isinstance(error, (TwitterAuthError, TwitterAlreadyConnectedError)):
                raise
            raise TwitterNetworkError(f"Error getting OAuth URL: {str(error)}")

    async def link_twitter_account(self) -> str:
        """
        Основной метод для привязки Twitter-аккаунта к Zenith.
        
        Returns:
            str: Сообщение о результате операции
            
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterNetworkError: При сетевых ошибках
            TwitterInvalidTokenError: При недействительном токене
        """
        try:
            # Шаг 1: Инициализация клиента Twitter
            twitter_client = await self._initialize_twitter_client()
            twitter_headers = self.get_twitter_headers(twitter_client.ct0)
            
            # Шаг 2: Получение URL для OAuth-авторизации
            oauth_url, code_challenge = await self._get_oauth_url()
            
            # Получаем параметры из URL
            parsed_url = urlparse(oauth_url)
            query_params = parse_qs(parsed_url.query)
            
            # Шаг 3: Запрос авторизации к Twitter API
            auth_url = f"https://{self.config.API_DOMAIN}{self.config.OAUTH2_PATH}"
            
            # Сохраняем state для последующей верификации
            state = query_params.get('state', [self.wallet_address])[0]
            
            # Собираем параметры из полученного URL
            auth_params = {
                'client_id': query_params.get('client_id', [self.config.CLIENT_ID])[0],
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
                'redirect_uri': self.config.REDIRECT_URI,
                'response_type': 'code',
                'scope': self.config.REQUIRED_SCOPES,
                'state': state
            }
            
            auth_response = await self._make_request(
                'get', 
                auth_url,
                headers=twitter_headers,
                params=auth_params
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
            
            # Шаг 4: Подтверждение авторизации (approval=true)
            approval_response = await self._make_request(
                'post', 
                auth_url,
                headers=twitter_headers,
                data={'approval': 'true', 'code': auth_code}
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
                
                redirect_uri = approval_data.get('redirect_uri', '')
                if not redirect_uri:
                    raise TwitterAuthError("No redirect URL received after authorization")
                
                # Парсим redirect_uri для получения final_code
                parsed_redirect = urlparse(redirect_uri)
                if 'testnet-router.zenithswap.xyz' not in parsed_redirect.netloc:
                    raise TwitterAuthError("Invalid redirect URL domain")
                
                # Извлекаем код из URL редиректа
                redirect_params = parse_qs(parsed_redirect.query)
                final_code = redirect_params.get('code', [''])[0]
                
                if not final_code:
                    raise TwitterAuthError("No authorization code found in redirect URL")
                
                # Шаг 5: Подписка на аккаунт Zenith
                # Этот шаг может быть необходим для полной функциональности на сайте Zenith,
                # но сама привязка происходит независимо от успешности подписки
                await self.logger_msg(
                    f"Following Zenith Twitter account (ID: {self.config.ZENITH_TWITTER_ID})",
                    "info",
                    self.wallet_address
                )
                
                try:
                    async with TwitterWorker(self.account) as twitter_module:
                        await twitter_module.follow_user(self.config.ZENITH_TWITTER_ID)
                except Exception as e:
                    await self.logger_msg(
                        f"Following Zenith Twitter account failed: {str(e)}, but continuing with account linking",
                        "warning",
                        self.wallet_address
                    )
                
                # Шаг 6: Колбек запрос для завершения привязки
                callback_url = f"{self.config.REDIRECT_URI}?code={final_code}&state={state}"
                try:
                    await self._make_request(
                        'get',
                        callback_url,
                        headers=self.get_platform_headers(),
                        allow_redirects=False
                    )
                except Exception as e:
                    # Даже если запрос вызвал ошибку, привязка может произойти
                    await self.logger_msg(
                        f"Callback request completed with result: {str(e)}",
                        "warning",
                        self.wallet_address
                    )
                
                return "Twitter account successfully linked to Zenith Finance"
                
        except TwitterAlreadyConnectedError:
            success_message = "Twitter account is already connected to this wallet"
            return success_message
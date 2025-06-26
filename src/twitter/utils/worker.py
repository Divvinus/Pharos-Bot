"""
Модуль для работы с Twitter API.
"""

import twitter
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Self

from src.utils import save_bad_twitter_token
from src.wallet import Wallet
from src.twitter.exceptions import (
    TwitterClientError,
    TwitterInvalidTokenError,
    TwitterAccountSuspendedError,
    TwitterRateLimitError,
    TwitterAlreadyDoneError,
    TwitterActionBlockedError,
    TwitterAPIError,
)
from src.twitter.models import Account


class TwitterWorker(Wallet):
    """Клиент для взаимодействия с Twitter API"""
    
    def __init__(self, account: Account) -> None:
        """
        Инициализация клиента Twitter.
        
        Args:
            account: Объект аккаунта с токеном Twitter
        """
        super().__init__(account.keypair, account.proxy)
        self.account = account
        self.twitter_account = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def _handle_twitter_error(self, error: Exception) -> Exception:
        """
        Анализирует ошибку Twitter API и преобразует её в соответствующее кастомное исключение
        
        Args:
            error: Объект исключения
            
        Returns:
            Exception: Кастомное исключение соответствующего типа
        """
        error_str = str(error)
        error_code = None
        
        # Извлекаем код ошибки, если он есть
        if hasattr(error, 'error_code'):
            error_code = error.error_code
        else:
            # Попытка извлечь код ошибки из строки сообщения
            code_match = re.search(r'(\d{2,3})', error_str)
            if code_match:
                error_code = int(code_match.group(1))
        
        # Коды ошибок и соответствующие им исключения
        error_map = {
            # Ошибки авторизации
            32: TwitterInvalidTokenError("Invalid Authentication Token"),
            64: TwitterInvalidTokenError("Account suspended"),
            89: TwitterInvalidTokenError("Token expired or invalid"),
            135: TwitterInvalidTokenError("Could not authenticate you"),
            215: TwitterInvalidTokenError("Bad Authentication data"),
            326: TwitterInvalidTokenError("To protect our users from spam, this account can't perform this action right now"),
            
            # Ошибки действий
            139: TwitterAlreadyDoneError("Tweet already liked"),
            327: TwitterAlreadyDoneError("You have already retweeted this Tweet"),
            
            # Ограничения
            88: TwitterRateLimitError("Rate limit exceeded"),
            108: TwitterActionBlockedError("You are unable to follow more people at this time"),
            162: TwitterActionBlockedError("You have been blocked from following this account"),
            160: TwitterAlreadyDoneError("You have already requested to follow this user"),
        }
        
        # Проверяем наличие кода ошибки в нашем словаре
        if error_code and error_code in error_map:
            exception = error_map[error_code]
            
            # Если это ошибка с недействительным токеном, сохраняем токен как плохой
            if isinstance(exception, TwitterInvalidTokenError):
                await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
            
            return exception
        
        # Проверка по тексту ошибки, если код не найден
        lower_error = error_str.lower()
        
        # Проверка на недействительный токен
        invalid_token_phrases = [
            "could not authenticate", 
            "invalid token", 
            "token has been revoked", 
            "session invalid",
            "not authorized",
            "authorization required",
            "invalid or expired token"
        ]
        
        for phrase in invalid_token_phrases:
            if phrase in lower_error:
                await save_bad_twitter_token(self.account.auth_tokens_twitter, self.wallet_address)
                return TwitterInvalidTokenError(f"Invalid token: {error_str}")
        
        # Проверка на другие известные ошибки по тексту
        if "rate limit" in lower_error:
            return TwitterRateLimitError(f"Rate limit exceeded: {error_str}")
        
        if "already retweeted" in lower_error:
            return TwitterAlreadyDoneError(f"Already retweeted: {error_str}")
        
        if "already favorited" in lower_error or "already liked" in lower_error:
            return TwitterAlreadyDoneError(f"Already liked: {error_str}")
        
        if "already follow" in lower_error or "already requested to follow" in lower_error:
            return TwitterAlreadyDoneError(f"Already following: {error_str}")
        
        if "unable to follow" in lower_error:
            return TwitterActionBlockedError(f"Unable to follow: {error_str}")
        
        if "blocked from following" in lower_error:
            return TwitterActionBlockedError(f"Blocked from following: {error_str}")
        
        if "account suspended" in lower_error or "account locked" in lower_error:
            return TwitterAccountSuspendedError(f"Account suspended: {error_str}")
        
        # Общая ошибка API для всех остальных случаев
        return TwitterAPIError(f"Twitter API error: {error_str}", error_code)

    @asynccontextmanager
    async def _get_twitter_client(self) -> AsyncGenerator[twitter.Client | None, None]:
        """
        Контекстный менеджер для получения клиента Twitter API.
        
        Yields:
            twitter.Client: Клиент Twitter API
        
        Raises:
            TwitterAuthError: При ошибках авторизации
            TwitterAccountSuspendedError: Если аккаунт заблокирован
            TwitterInvalidTokenError: При недействительном токене
        """
        self.twitter_account = twitter.Account(auth_token=self.account.auth_tokens_twitter)
        client = None

        try:
            async with twitter.Client(
                self.twitter_account,
                proxy=str(self.account.proxy) if self.account.proxy else None
            ) as client:
                await client.update_account_info()
                yield client

        except Exception as error:
            # Преобразуем исключение в наши кастомные исключения
            twitter_error = await self._handle_twitter_error(error)
            # Пробрасываем исключение дальше для обработки
            raise twitter_error
                
    async def retweet_tweet(self, tweet_id: int) -> bool:
        """
        Ретвит указанного твита.
        
        Args:
            tweet_id: ID твита для ретвита
            
        Returns:
            bool: True, если ретвит успешен или уже был выполнен, False в случае ошибки
        """
        try:
            async with self._get_twitter_client() as client:
                if not client:
                    return False

                for attempt in range(3):
                    try:
                        query_id = client._ACTION_TO_QUERY_ID['CreateRetweet']
                        url = f"{client._GRAPHQL_URL}/{query_id}/CreateRetweet"
                        
                        json_payload = {
                            "variables": {"tweet_id": tweet_id, "dark_request": False},
                            "queryId": query_id,
                        }
                        
                        try:
                            response, data = await client.request("POST", url, json=json_payload)
                            
                            if "data" in data and "create_retweet" in data["data"] and "retweet_results" in data["data"]["create_retweet"]:
                                return True
                                
                        except Exception as api_error:
                            # Преобразуем в наши исключения
                            twitter_error = await self._handle_twitter_error(api_error)
                            
                            if isinstance(twitter_error, TwitterAlreadyDoneError):
                                return True
                            
                            if isinstance(twitter_error, TwitterInvalidTokenError):
                                # Токен недействителен, нет смысла продолжать попытки
                                raise twitter_error
                            
                            # Если это последняя попытка, пробрасываем ошибку дальше
                            if attempt == 2:
                                raise twitter_error

                    except (TwitterInvalidTokenError, TwitterAccountSuspendedError):
                        # Для критических ошибок сразу завершаем
                        raise
                    except Exception as outer_error:
                        if attempt == 2:
                            # Если это была последняя попытка, завершаем с ошибкой
                            if isinstance(outer_error, TwitterClientError):
                                raise outer_error
                            else:
                                raise TwitterAPIError(f"Unexpected error: {str(outer_error)}")

                # Если дошли сюда, значит все попытки исчерпаны
                raise TwitterAPIError("Failed to retweet a tweet even after three attempts")
                
        except TwitterAlreadyDoneError:
            # Ретвит уже сделан ранее - считаем успехом
            return True
        except (TwitterInvalidTokenError, TwitterAccountSuspendedError, TwitterClientError):
            # Любые ошибки Twitter API - возвращаем False
            return False
        except Exception:
            # Неожиданные ошибки - возвращаем False
            return False
        
    async def like_tweet(self, tweet_id: int) -> bool:
        """
        Поставить лайк на указанный твит.
        
        Args:
            tweet_id: ID твита для лайка
            
        Returns:
            bool: True, если лайк успешен или уже был выполнен, False в случае ошибки
        """
        try:
            async with self._get_twitter_client() as client:
                if not client:
                    return False

                for attempt in range(3):
                    try:
                        query_id = client._ACTION_TO_QUERY_ID.get('FavoriteTweet')
                        url = f"{client._GRAPHQL_URL}/{query_id}/FavoriteTweet"
                        
                        json_payload = {
                            "variables": {"tweet_id": str(tweet_id)},
                            "queryId": query_id,
                        }
                        
                        try:
                            response, data = await client.request("POST", url, json=json_payload)
                            
                            if data.get("data", {}).get("favorite_tweet") == "Done":
                                return True
                                
                        except Exception as api_error:
                            # Преобразуем в наши исключения
                            twitter_error = await self._handle_twitter_error(api_error)
                            
                            if isinstance(twitter_error, TwitterAlreadyDoneError):
                                return True
                            
                            if isinstance(twitter_error, TwitterInvalidTokenError):
                                # Токен недействителен, нет смысла продолжать попытки
                                raise twitter_error
                            
                            # Если это последняя попытка, пробрасываем ошибку дальше
                            if attempt == 2:
                                raise twitter_error

                    except (TwitterInvalidTokenError, TwitterAccountSuspendedError):
                        # Для критических ошибок сразу завершаем
                        raise
                    except Exception as outer_error:
                        if attempt == 2:
                            # Если это была последняя попытка, завершаем с ошибкой
                            if isinstance(outer_error, TwitterClientError):
                                raise outer_error
                            else:
                                raise TwitterAPIError(f"Unexpected error: {str(outer_error)}")

                # Если дошли сюда, значит все попытки исчерпаны
                raise TwitterAPIError("Failed to like tweet after three attempts")
                
        except TwitterAlreadyDoneError:
            # Лайк уже был поставлен ранее - считаем успехом
            return True
        except (TwitterInvalidTokenError, TwitterAccountSuspendedError, TwitterClientError):
            # Любые ошибки Twitter API - возвращаем False
            return False
        except Exception:
            # Неожиданные ошибки - возвращаем False
            return False
        
    async def follow_user(self, user_id: int) -> bool:
        """
        Подписаться на указанного пользователя.
        
        Args:
            user_id: ID пользователя для подписки
            
        Returns:
            bool: True, если подписка успешна или уже была выполнена, False в случае ошибки
        """
        try:
            async with self._get_twitter_client() as client:
                if not client:
                    return False

                for attempt in range(3):
                    try:
                        url = "https://x.com/i/api/1.1/friendships/create.json"
                        data = {
                            "include_profile_interstitial_type": "1",
                            "include_blocking": "1",
                            "include_blocked_by": "1",
                            "include_followed_by": "1",
                            "include_want_retweets": "1",
                            "include_mute_edge": "1",
                            "include_can_dm": "1",
                            "include_can_media_tag": "1",
                            "include_ext_is_blue_verified": "1",
                            "include_ext_verified_type": "1",
                            "include_ext_profile_image_shape": "1",
                            "skip_status": "1",
                            "user_id": str(user_id)
                        }
                        
                        try:
                            response, data = await client.request("POST", url, data=data)
                            
                            if "id" in data and data["id"] == user_id:
                                return True
                                
                        except Exception as api_error:
                            # Преобразуем в наши исключения
                            twitter_error = await self._handle_twitter_error(api_error)
                            
                            if isinstance(twitter_error, TwitterAlreadyDoneError):
                                return True
                            
                            if isinstance(twitter_error, TwitterActionBlockedError):
                                raise twitter_error
                            
                            if isinstance(twitter_error, TwitterInvalidTokenError):
                                # Токен недействителен, нет смысла продолжать попытки
                                raise twitter_error
                            
                            # Если это последняя попытка, пробрасываем ошибку дальше
                            if attempt == 2:
                                raise twitter_error

                    except (TwitterInvalidTokenError, TwitterAccountSuspendedError, TwitterActionBlockedError):
                        # Для критических ошибок сразу завершаем
                        raise
                    except Exception as outer_error:
                        if attempt == 2:
                            # Если это была последняя попытка, завершаем с ошибкой
                            if isinstance(outer_error, TwitterClientError):
                                raise outer_error
                            else:
                                raise TwitterAPIError(f"Unexpected error: {str(outer_error)}")

                # Если дошли сюда, значит все попытки исчерпаны
                raise TwitterAPIError("Failed to follow user after three attempts")
                
        except TwitterAlreadyDoneError:
            # Подписка уже была оформлена ранее - считаем успехом
            return True
        except (TwitterInvalidTokenError, TwitterAccountSuspendedError, TwitterActionBlockedError, TwitterClientError):
            # Любые ошибки Twitter API - возвращаем False
            return False
        except Exception:
            # Неожиданные ошибки - возвращаем False
            return False
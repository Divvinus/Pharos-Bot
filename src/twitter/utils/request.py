"""
Утилиты для выполнения HTTP-запросов.
"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional, Tuple, Union

from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.utils import random_sleep
from src.twitter.exceptions import TwitterAuthError, TwitterNetworkError

# Тип для HTTP-заголовков
Headers = Dict[str, str]


async def make_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    headers: Optional[Headers] = None,
    **kwargs
) -> aiohttp.ClientResponse:
    """
    Выполнение HTTP-запроса с повторными попытками и обновлением заголовков.
    
    Args:
        session: Сессия aiohttp
        method: HTTP метод ('get', 'post', и т.д.)
        url: URL запроса
        headers: HTTP заголовки
        **kwargs: Дополнительные параметры запроса
        
    Returns:
        aiohttp.ClientResponse: Ответ сервера
        
    Raises:
        TwitterAuthError: При ошибках авторизации
        TwitterNetworkError: При сетевых ошибках
    """
    last_error = None
    
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            # Обновляем заголовки сессии если переданы новые
            if headers:
                session.headers.update(headers)
            
            # Выполняем запрос
            if method.lower() == 'get':
                response = await session.get(url, **kwargs, ssl=False)
            elif method.lower() == 'post':
                response = await session.post(url, **kwargs, ssl=False)
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
            raise TwitterAuthError(f"Unexpected error while executing a query: {str(error)}")
    
    # Обработка сетевых ошибок после всех попыток
    error_msg = str(last_error)
    if any(term in error_msg.lower() for term in ["forcibly severed", "connection", "ssl", "host"]):
        raise TwitterNetworkError(f"Network connection error after {MAX_RETRY_ATTEMPTS} attempts")
    raise TwitterNetworkError(f"Unknown network error: {error_msg}")
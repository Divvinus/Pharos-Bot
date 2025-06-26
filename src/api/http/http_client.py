import asyncio
import json
import random
from typing import Literal, Any, Self

import aiohttp
import ua_generator
from yarl import URL
from better_proxy import Proxy

from .exceptions import *


class HTTPClient:
    # Ошибки, при которых стоит повторить запрос
    RETRYABLE_ERRORS = (
        APIServerSideError,
        APIRateLimitError, 
        APITimeoutError,
        APISSLError,
        aiohttp.ClientError,
        aiohttp.ServerTimeoutError,
        asyncio.TimeoutError
    )
    
    # Максимальная задержка между повторами (секунды)
    MAX_RETRY_DELAY = 30.0
    
    def __init__(self, base_url: str, proxy: Proxy | None = None) -> None:
        self.base_url = base_url
        self.proxy = proxy
        self._session: aiohttp.ClientSession | None = None
        self._headers = self._generate_browser_headers()
        
    def _generate_browser_headers(self) -> dict[str, str]:
        """
        Генерация реалистичных браузерных заголовков.
        
        Returns:
            Словарь с заголовками, имитирующими настоящий браузер
        """
        user_agent = ua_generator.generate(
            device='desktop', 
            platform='windows', 
            browser='chrome'
        )
        
        return {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-CH-UA': str(user_agent.ch.brands),
            'Sec-CH-UA-Mobile': str(user_agent.ch.mobile).lower(),
            'Sec-CH-UA-Platform': f'"{user_agent.ch.platform}"',
            'User-Agent': user_agent.text
        }

    async def _create_session(self) -> aiohttp.ClientSession:
        """
        Создание новой HTTP сессии с правильными настройками.
        
        Returns:
            Настроенная aiohttp сессия
        """
        connector = aiohttp.TCPConnector(
            limit=100,  # Максимальное количество соединений
            limit_per_host=10,  # Максимальное количество соединений на хост
            ttl_dns_cache=300,  # Кеш DNS на 5 минут
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=60,  # Общий таймаут
            connect=10,  # Таймаут подключения
            sock_read=30  # Таймаут чтения
        )
        
        return aiohttp.ClientSession(
            headers=self._headers,
            connector=connector,
            timeout=timeout,
            trust_env=True  # Использовать переменные окружения для прокси
        )

    def _build_request_url(self, url: str | None = None, endpoint: str | None = None) -> str:
        """
        Построение итогового URL для запроса.
        
        Args:
            url: Полный URL (приоритет над endpoint)
            endpoint: Эндпоинт относительно base_url
            
        Returns:
            Итоговый URL для запроса
            
        Raises:
            APIClientError: Если не указан ни url, ни endpoint
        """
        if url:
            try:
                parsed_url = URL(url)
                # Исправляем некорректные комбинации схема/порт
                if parsed_url.scheme == 'https' and parsed_url.port == 80:
                    parsed_url = parsed_url.with_port(443)
                elif parsed_url.scheme == 'http' and parsed_url.port == 443:
                    parsed_url = parsed_url.with_port(80)
                return str(parsed_url)
            except Exception:
                return url
        
        if endpoint:
            base = URL(self.base_url)
            clean_endpoint = endpoint.lstrip('/')
            return str(base / clean_endpoint)
            
        raise APIClientError("Either the full URL or the endpoint must be specified")

    def _prepare_headers(self, custom_headers: dict[str, str] | None = None) -> dict[str, str]:
        """
        Подготовка финальных заголовков для запроса.
        
        Args:
            custom_headers: Дополнительные заголовки для запроса
            
        Returns:
            Объединенные заголовки
        """
        headers = self._headers.copy()
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _parse_response_data(self, text: str, content_type: str) -> Any:
        """
        Умный парсинг ответа сервера.
        
        Args:
            text: Текст ответа
            content_type: MIME-тип контента
            
        Returns:
            Распарсенные данные или исходный текст
        """
        if not text:
            return None
            
        # Проверяем, что это JSON по content-type или структуре
        is_json_content = any(json_type in content_type.lower() 
                             for json_type in ['application/json', 'text/json', '/json'])
        looks_like_json = text.strip().startswith('{') or text.strip().startswith('[')
        
        if is_json_content or looks_like_json:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
                
        return text

    def _handle_http_status(self, status_code: int, response_data: dict[str, Any]) -> None:
        """
        Обработка HTTP статус-кодов с выбросом соответствующих исключений.
        
        Args:
            status_code: HTTP статус код
            response_data: Данные ответа для контекста ошибки
            
        Raises:
            APIRateLimitError: При превышении лимита запросов (429)
            APIClientSideError: При ошибках клиента (4xx)
            APIServerSideError: При ошибках сервера (5xx)
        """
        if status_code == 429:
            raise APIRateLimitError("API request limit exceeded")
        elif 400 <= status_code < 500:
            raise APIClientSideError(
                f"Client error: HTTP {status_code}", 
                status_code, 
                response_data
            )
        elif status_code >= 500:
            raise APIServerSideError(
                f"Server error: HTTP {status_code}", 
                status_code, 
                response_data
            )

    def _calculate_retry_delay(self, attempt: int, base_delay: tuple[float, float]) -> float:
        """
        Расчет задержки для повторного запроса с экспоненциальным отступом.
        
        Args:
            attempt: Номер текущей попытки
            base_delay: Базовый диапазон задержки (мин, макс)
            
        Returns:
            Время задержки в секундах
        """
        base_time = random.uniform(*base_delay)
        exponential_factor = min(2 ** (attempt - 1), self.MAX_RETRY_DELAY / base_time)
        return min(base_time * exponential_factor, self.MAX_RETRY_DELAY)

    async def _execute_single_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        **request_kwargs
    ) -> dict[str, Any]:
        """
        Выполнение одного HTTP запроса без повторов.
        
        Args:
            method: HTTP метод
            url: URL для запроса  
            headers: Заголовки запроса
            **request_kwargs: Дополнительные параметры для aiohttp
            
        Returns:
            Словарь с результатом запроса
        """
        proxy_url = self.proxy.as_url if self.proxy else None
        
        async with self._session.request(
            method=method,
            url=url,
            headers=headers,
            proxy=proxy_url,
            raise_for_status=False,
            **request_kwargs
        ) as response:
            
            content_type = response.headers.get('Content-Type', '')
            status_code = response.status
            text = await response.text()
            
            result = {
                "status_code": status_code,
                "url": str(response.url),
                "text": text,
                "data": self._parse_response_data(text, content_type),
                "headers": dict(response.headers)
            }
            
            return result

    async def send_request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"] = "GET",
        url: str | None = None,
        endpoint: str | None = None,
        json_data: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        allow_redirects: bool = True,
        verify_ssl: bool = False,
        validate_status: bool = True,
        max_retries: int = 3,
        retry_delay: tuple[float, float] = (1.0, 3.0),
        timeout: float = 30.0
    ) -> dict[str, Any]:
        """
        Основной метод для отправки HTTP запросов с автоматическими повторами.
        
        Args:
            method: HTTP метод (GET, POST, PUT, DELETE, PATCH, OPTIONS)
            url: Полный URL (альтернатива endpoint)
            endpoint: Эндпоинт относительно base_url
            json_data: Данные для отправки в формате JSON
            form_data: Данные формы
            params: URL параметры
            headers: Дополнительные заголовки
            cookies: Куки для запроса
            allow_redirects: Разрешить автоматические редиректы
            verify_ssl: Проверять SSL сертификаты
            validate_status: Проверять HTTP статус и бросать исключения при ошибках
            max_retries: Максимальное количество повторов
            retry_delay: Диапазон задержки между повторами (мин, макс сек)
            timeout: Таймаут запроса в секундах
            
        Returns:
            Словарь с результатом запроса содержащий status_code, url, text, data, headers
            
        Raises:
            APIClientError: При ошибках конфигурации или неожиданных ошибках
            APIConnectionError: При проблемах с сетевым соединением
            APITimeoutError: При превышении таймаута
            APIRateLimitError: При превышении лимита запросов
            APIClientSideError: При ошибках клиента (4xx)
            APIServerSideError: При ошибках сервера (5xx)
            APISSLError: При ошибках SSL
            APISessionError: При проблемах с сессией
        """
        if not self._session or self._session.closed:
            raise APISessionError("HTTP session is not initialized. Use context manager")
            
        target_url = self._build_request_url(url, endpoint)
        request_headers = self._prepare_headers(headers)
                
        # Подготовка параметров запроса
        request_kwargs = {
            'params': params,
            'cookies': cookies,
            'allow_redirects': allow_redirects,
            'ssl': verify_ssl,
            'timeout': aiohttp.ClientTimeout(total=timeout)
        }
        
        # Добавляем данные в зависимости от типа
        if json_data:
            request_kwargs['json'] = json_data
            request_headers['Content-Type'] = 'application/json'
        elif form_data:
            request_kwargs['data'] = form_data
        
        last_error = None
        
        # Основной цикл повторов
        for attempt in range(1, max_retries + 1):
            try:
                result = await self._execute_single_request(
                    method=method,
                    url=target_url,
                    headers=request_headers,
                    **request_kwargs
                )
                
                # Проверяем статус только если это требуется
                if validate_status:
                    self._handle_http_status(result["status_code"], result)
                
                return result
                
            except (aiohttp.ClientSSLError, aiohttp.ClientConnectorSSLError) as error:
                last_error = APISSLError(f"SSL connection error: {error}")
                
            except (aiohttp.ClientConnectorError, aiohttp.ClientOSError) as error:
                last_error = APIConnectionError(f"Connection error: {error}")
                
            except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as error:
                last_error = APITimeoutError(f"Request timeout exceeded: {error}")
                
            except aiohttp.ServerDisconnectedError as error:
                last_error = APIConnectionError(f"The server dropped the connection: {error}")
                
            except (APIRateLimitError, APIClientSideError):
                # Эти ошибки не должны повторяться
                raise
                
            except self.RETRYABLE_ERRORS as error:
                last_error = error
                
            except Exception as error:
                raise APIClientError(f"Unexpected error when querying to {target_url}: {error}")
            
            # Если это не последняя попытка - ждем и повторяем
            if attempt < max_retries:
                delay = self._calculate_retry_delay(attempt, retry_delay)
                await asyncio.sleep(delay)
            else:
                break
        
        # Если все попытки исчерпаны - пробрасываем последнюю ошибку
        if last_error:
            raise last_error
            
        raise APIServerSideError(f"All {max_retries} of query attempts to {target_url} have been exhausted")

    async def get(self, **kwargs) -> dict[str, Any]:
        """Удобный метод для GET запросов"""
        return await self.send_request(method="GET", **kwargs)
    
    async def post(self, **kwargs) -> dict[str, Any]:
        """Удобный метод для POST запросов"""
        return await self.send_request(method="POST", **kwargs)
    
    async def put(self, **kwargs) -> dict[str, Any]:
        """Удобный метод для PUT запросов"""
        return await self.send_request(method="PUT", **kwargs)
    
    async def delete(self, **kwargs) -> dict[str, Any]:
        """Удобный метод для DELETE запросов"""
        return await self.send_request(method="DELETE", **kwargs)

    async def __aenter__(self) -> Self:
        """Вход в контекст-менеджер: создание сессии"""
        if not self._session or self._session.closed:
            self._session = await self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекста-менеджера: закрытие сессии"""
        await self.close()

    async def close(self) -> None:
        """Безопасное закрытие HTTP клиента и освобождение ресурсов"""
        if self._session and not self._session.closed:
            try:
                await self._session.close()
                # Даем время на корректное закрытие соединений
                await asyncio.sleep(0.1)
            except Exception as error:
                raise APIClientError(f"Error when closing HTTP client: {error}")
            finally:
                self._session = None
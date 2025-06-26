import aiohttp
import asyncio
import json
from typing import Any, Self

from configs import (
    MAX_RETRY_ATTEMPTS, 
    RETRY_SLEEP_RANGE,
    CAP_MONSTER_API_KEY,
    TWO_CAPTCHA_API_KEY
)
from src.models import Account
from src.utils import get_address, random_sleep
from .exceptions import *

class CaptchaSolver:
    # Конфигурация сервисов капчи
    CAPTCHA_SERVICES = {
        CAP_MONSTER_API_KEY: "https://api.capmonster.cloud",
        TWO_CAPTCHA_API_KEY: "https://api.2captcha.com"
    }
    
    def __init__(self, account: Account):
        self.account = account
        self._session: aiohttp.ClientSession | None= None
        self._current_api_key: str | None = None
        self._service_base_url: str | None = None
        self._wallet_address: str | None = None 

    @property
    def wallet_address(self) -> str:
        """Получение адреса кошелька (ленивая инициализация)"""
        if self._wallet_address is None:
            self._wallet_address = get_address(self.account.keypair)
        return self._wallet_address
    
    async def __aenter__(self) -> Self:
        """Асинхронный контекст-менеджер: создание сессии"""
        self._session = aiohttp.ClientSession(proxy=self.account.proxy.as_url)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекст-менеджер: закрытие сессии"""
        if self._session and not self._session.closed:
            await self._session.close()
        
    async def _execute_http_request(
        self, 
        method: str, 
        url: str, 
        **kwargs
    ) -> dict[str, Any]:
        """
        Выполнение HTTP-запроса с автоматическими повторными попытками.
        
        Args:
            method: HTTP метод (GET, POST)
            url: URL для запроса
            **kwargs: Дополнительные параметры для запроса
            
        Returns:
            Десериализованный JSON ответ
            
        Raises:
            NetworkConnectionError: При проблемах с сетевым соединением
        """
        network_errors = (
            aiohttp.ClientConnectorError, 
            aiohttp.ServerDisconnectedError, 
            aiohttp.ClientOSError, 
            asyncio.TimeoutError
        )
        
        last_error = None
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                async with self._session.request(method, url, **kwargs, ssl=False) as response:
                    response_text = await response.text()
                    
                    if response.status != 200:
                        raise NetworkConnectionError(
                            f"HTTP {response.status}: {response_text}"
                        )
                    
                    try:
                        # Пытаемся преобразовать текст в JSON
                        return json.loads(response_text)
                    except json.JSONDecodeError:
                        # Если не получилось - возвращаем как plain text в структурированном виде
                        return {"response": response_text}
                        
            except network_errors as error:
                last_error = error
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await random_sleep("Captcha Solver", *RETRY_SLEEP_RANGE)
                else:
                    break
            
            except Exception as error:
                raise CaptchaServiceError(f"Unexpected error while executing a query: {error}")
        
        # Обработка финальной сетевой ошибки
        error_message = str(last_error).lower()
        connection_issues = ["forcibly severed", "connection", "ssl", "host"]
        
        if any(issue in error_message for issue in connection_issues):
            raise NetworkConnectionError(
                f"Problems with network connection after {MAX_RETRY_ATTEMPTS} attempts"
            )
        
        raise NetworkConnectionError(f"Unknown network error: {last_error}")

    def _get_available_api_keys(self) -> list[str]:
        """
        Получение списка доступных (не пустых) API ключей.
        
        Returns:
            Список валидных API ключей
            
        Raises:
            NoValidApiKeysError: Если нет ни одного валидного ключа
        """
        available_keys = [key for key in self.CAPTCHA_SERVICES.keys() if key]
        
        if not available_keys:
            raise NoValidApiKeysError("No valid API key was found")
            
        return available_keys
        
    async def _check_api_key_balance(self, api_key: str) -> bool:
        """
        Проверка баланса для конкретного API ключа.
        
        Args:
            api_key: API ключ для проверки
            
        Returns:
            True если баланс положительный, False иначе
        """
        service_url = self.CAPTCHA_SERVICES[api_key]
        
        balance_data = await self._execute_http_request(
            "POST",
            f"{service_url}/getBalance",
            json={"clientKey": api_key}
        )
        
        return balance_data.get("balance", 0) > 0
      
    async def _find_working_api_key(self) -> tuple[str, str]:
        """
        Поиск API ключа с положительным балансом.
        
        Returns:
            Кортеж (api_key, base_url) для рабочего сервиса
            
        Raises:
            InsufficientBalanceError: Если у всех ключей нулевой баланс
        """
        available_keys = self._get_available_api_keys()

        for api_key in available_keys:
            try:
                if await self._check_api_key_balance(api_key):
                    return api_key, self.CAPTCHA_SERVICES[api_key]
            except Exception as error:
                continue

        raise InsufficientBalanceError("Insufficient balance on all API keys")

    async def _create_captcha_task(self) -> str:
        """
        Создание задачи для решения капчи.
        
        Returns:
            ID созданной задачи
            
        Raises:
            TaskCreationError: При ошибке создания задачи
        """
        task_payload = {
            "clientKey": self._current_api_key,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": "https://zenithswap.xyz/faucet",
                "websiteKey": "0x4AAAAAABesmP1SWw2G_ear",
                "data": f"{self.wallet_address}_0xAD902CF99C2dE2f1Ba5ec4D642Fd7E49cae9EE37"
            }
        }
        
        response_data = await self._execute_http_request(
            "POST",
            f"{self._service_base_url}/createTask",
            json=task_payload
        )
        
        if response_data.get("errorId") != 0:
            error_code = response_data.get("errorCode", "Unknown")
            error_description = response_data.get("errorDescription", "No description")
            raise TaskCreationError(f"Error code: {error_code}. Description: {error_description}")
            
        return response_data["taskId"]
        
    async def _get_task_solution(self, task_id: str) -> dict[str, Any]:
        """
        Получение результата решения задачи капчи.
        
        Args:
            task_id: ID задачи
            
        Returns:
            Данные с результатом решения
            
        Raises:
            TaskSolutionError: При ошибке получения решения
        """
        solution_payload = {
            "clientKey": self._current_api_key,
            "taskId": task_id
        }
        
        response_data = await self._execute_http_request(
            "POST",
            f"{self._service_base_url}/getTaskResult",
            json=solution_payload
        )
        
        if response_data.get("errorId") != 0:
            error_code = response_data.get("errorCode", "Unknown")
            error_description = response_data.get("errorDescription", "No description")
            raise TaskSolutionError(f"Error code: {error_code}. Description: {error_description}")
            
        return response_data

    async def _wait_for_solution(self, task_id: str) -> str:
        """
        Ожидание готовности решения капчи с повторными проверками.
        
        Args:
            task_id: ID задачи для проверки
            
        Returns:
            Токен решения капчи
            
        Raises:
            TaskSolutionError: При ошибке получения решения или таймауте
        """
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                task_result = await self._get_task_solution(task_id)
                status = task_result.get("status")
                
                # Задача еще обрабатывается
                if status == "processing":
                    await random_sleep("Captcha Solver", 10, 30)
                    continue
                
                # Специальная обработка ошибки "недостаточно средств"
                if task_result.get("errorId") == 12:
                    raise InsufficientBalanceError("Insufficient funds on the balance sheet")
                
                # Задача готова и есть решение
                if status == "ready" and "solution" in task_result:
                    return task_result["solution"]["token"]
                    
            except (InsufficientBalanceError, TaskSolutionError):
                # Пробрасываем известные ошибки дальше
                raise
            except Exception as error:
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    raise TaskSolutionError(f"Error in receiving the solution: {error}")
                await random_sleep("Captcha Solver", *RETRY_SLEEP_RANGE)
                
        raise TaskSolutionError(f"Could not get a solution for {MAX_RETRY_ATTEMPTS} attempted")

    async def solve_captcha(self) -> str:
        """
        Основной метод для решения капчи.
        
        Returns:
            Токен решения капчи
            
        Raises:
            CaptchaServiceError: При любых ошибках в процессе решения
        """
        # Находим рабочий API ключ
        self._current_api_key, self._service_base_url = await self._find_working_api_key()
        
        # Пытаемся решить капчу с повторными попытками
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # Создаем задачу
                task_id = await self._create_captcha_task()
                
                # Ждем решения
                solution_token = await self._wait_for_solution(task_id)
                
                return solution_token
                
            except (TaskCreationError, TaskSolutionError, InsufficientBalanceError):
                # Пробрасываем специфические ошибки
                raise
            except Exception as error:
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    raise CaptchaServiceError(f"Critical error when solving captcha: {error}")
                await random_sleep("Captcha Solver", *RETRY_SLEEP_RANGE)
                
        raise CaptchaServiceError(f"Failed to solve the captcha in {MAX_RETRY_ATTEMPTS} attempts")
from typing import Self

from ..registration import ConnectWalletPharos
from configs import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE
from src.api.http import HTTPClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address, random_sleep


# Тип для HTTP-заголовков
Headers = dict[str, str]

class TwitterTasks(AsyncLogger):
    TASK_MSG = "Fulfilling twitter tasks on Pharos Network site"
    
    def __init__(self, account: Account) -> None:
        AsyncLogger.__init__(self)
        self.account = account
        self.api_client: HTTPClient | None = None
        self.jwt_token: str | None = None
        self._wallet_address: str | None = None 
        
    async def __aenter__(self) -> Self:        
        self.api_client = HTTPClient(
            "https://api.pharosnetwork.xyz",  self.account.proxy
        )
        await self.api_client.__aenter__()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
        
    @property
    def wallet_address(self) -> str:
        if self._wallet_address is None:
            self._wallet_address = get_address(self.account.keypair)
        return self._wallet_address
        
    @staticmethod
    async def process_connect_wallet(account: Account) -> tuple[bool, str]:
        async with ConnectWalletPharos(account) as pharosnetwork:
            return await pharosnetwork.run_connect_wallet(return_token=True)
        
    def get_headers(self) -> Headers:
        """Заголовки для запросов к Pharos API"""
        return {
            'accept': 'application/json, text/plain, */*',
            'authorization': f'Bearer {self.jwt_token}',
            'content-type': 'application/json',
            'origin': 'https://testnet.pharosnetwork.xyz',
            'referer': 'https://testnet.pharosnetwork.xyz/'
        }
        
    async def get_tasks(self) -> list:
        await self.logger_msg("Requesting information on Twitter tasks", "info", self.wallet_address)
        
        params = {
            'address': self.wallet_address
        }
        
        response = await self.api_client.send_request(
            method="GET",
            endpoint="/user/tasks",
            params=params,
            headers=self.get_headers()
        )
        
        response_data = response['data']
        
        if response_data.get('code') != 0:
            raise ValueError(f"API returned error code: {response_data}")
            
        return response_data.get("data", {}).get("user_tasks")
    
    async def verify_tasks(self, id: str) -> tuple[bool, str]:
        await self.logger_msg(f"Send a request for task verification ID: {id}", "info", self.wallet_address)
        
        data = {
            'address': self.wallet_address,
            'task_id': int(id),
        }
        
        response = await self.api_client.send_request(
            method="POST",
            endpoint="/task/verify",
            json=data,
            headers=self.get_headers()
        )
        
        response_data = response['data']
        
        status = response_data.get("code")
        if status == 0:
            success_msg = f"Task ID: {id} completed successfully"
            await self.logger_msg(success_msg, "success", self.wallet_address)
            return True, success_msg
        if status == 1:
            msg = response_data.get("msg")
            warning_msg = f"Task ID: {id} something went wrong: {msg}"
            await self.logger_msg(warning_msg, "warning", self.wallet_address)
            return False, msg
        
        error_msg = f"Task ID: {id} unknown error: {response}"
        await self.logger_msg(error_msg, "error", self.wallet_address)
        return False, error_msg
    
    async def get_task_info(self) -> tuple[bool, str]:
        tasks = await self.get_tasks()
        tasks = self.remove_existing_task_ids(tasks)
        if not tasks:
            success_msg = "All Twitter tasks successfully completed"
            await self.logger_msg(success_msg, "success", self.wallet_address)
            return True, success_msg
        
        return False, tasks
    
    @staticmethod
    def remove_existing_task_ids(user_tasks):
        all_tasks = [201, 202, 203]
        task_ids_in_data = {task["TaskId"] for task in user_tasks}
        return [task_id for task_id in all_tasks if task_id not in task_ids_in_data]
    
    async def run_twitter_tasks(self) -> tuple[bool, str]:
        # Словарь для преобразования ID задач в читаемые названия
        TASK_NAMES = {
            201: "Follow Pharos on Twitter",
            202: "Retweet the post on Twitter",
            203: "Reply the post on Twitter"
        }
        
        await self.logger_msg(f"Starting {self.TASK_MSG}", "info", self.wallet_address)
        
        result, self.jwt_token = await self.process_connect_wallet(self.account)
        if not result:
            return result, self.jwt_token
        
        # Получаем информацию о задачах перед выполнением
        initial_result, initial_tasks = await self.get_task_info()
        if initial_result:
            return True, initial_tasks
        
        total_tasks = len(initial_tasks)

        successful_tasks = []
        failed_tasks = []
        
        for task_id in initial_tasks:
            task_name = TASK_NAMES.get(task_id, f"Unknown Task ({task_id})")
            task_completed = False
            
            for attempt in range(MAX_RETRY_ATTEMPTS):
                await self.logger_msg(
                    f"Preparing data for task execution. Attempt {attempt + 1} / {MAX_RETRY_ATTEMPTS}", "info", self.wallet_address
                )   
                
                try:  
                    try:
                        status, result = await self.verify_tasks(str(task_id))
                        if status:
                            successful_tasks.append(task_id)
                            task_completed = True
                            break  # Успешно выполнили задачу, переходим к следующей
                            
                        if result == "user has not bound X account":
                            error_msg = "You need to link a Twitter account on Pharos Network site"
                            await self.logger_msg(error_msg, "error", self.wallet_address)
                            return False, error_msg
                            
                    except Exception as e:
                        error_msg = f"Error verifying task {task_name}: {str(e)}"
                        await self.logger_msg(error_msg, "error", self.wallet_address)
                    
                    if task_id != initial_tasks[-1]:
                        await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                
                except Exception as e:
                    error_msg = f"Error {self.TASK_MSG}: {str(e)}"
                    await self.logger_msg(error_msg, "error", self.wallet_address)
                    
                    if attempt == MAX_RETRY_ATTEMPTS - 1:
                        break
                        
                    await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
            # Добавляем задачу в список неудачных, если все попытки не удались
            if not task_completed:
                failed_tasks.append(task_id)

        # Формируем итоговое сообщение
        success_count = len(successful_tasks)
        failed_count = len(failed_tasks)
        
        if success_count == total_tasks:
            emoji = "🎉"
            title = "All Twitter tasks completed successfully!"
            log_type = "success"
        elif success_count == 0:
            emoji = "💥"
            title = "Failed to complete any Twitter tasks!"
            log_type = "error"
        else:
            emoji = "⚠️"
            title = "Twitter tasks partially completed"
            log_type = "warning"

        # Форматируем списки задач
        successful_list = "\n    • ".join([f"✅ {TASK_NAMES.get(tid, tid)}" for tid in successful_tasks])
        failed_list = "\n    • ".join([f"❌ {TASK_NAMES.get(tid, tid)}" for tid in failed_tasks])
        
        final_message = (
            f"{emoji} {title}\n"
            f"  Completed: {success_count}/{total_tasks}\n"
        )
        
        if successful_list:
            final_message += f"  Successful tasks:\n    • {successful_list}\n"
        if failed_list:
            final_message += f"  Failed tasks:\n    • {failed_list}\n"

        await self.logger_msg(final_message, log_type, self.wallet_address)
        
        if success_count == total_tasks:
            return True, final_message
        return False, final_message
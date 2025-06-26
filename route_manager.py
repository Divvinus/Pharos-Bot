import random
import sys
from typing import Any, Callable

from src.models import Account
from src.logger import AsyncLogger
from src.task_manager import PharosBot
from src.utils import random_sleep
from configs import ROUTE_TASK
from bot_loader import config

logger = AsyncLogger()


class TaskFunctionLoader:
    """Отвечает за загрузку функций-обработчиков задач"""
    
    @staticmethod
    def load_task_functions() -> dict[str, Callable]:
        """Загружает доступные функции модулей из PharosBot"""
        return {
            attr_name[8:]: getattr(PharosBot, attr_name)
            for attr_name in dir(PharosBot)
            if attr_name.startswith('process_')
        }


class RouteOptimizer:
    """Отвечает за создание и валидацию маршрутов"""
    
    def __init__(self, available_functions: dict[str, Callable]):
        self.available_functions = available_functions
    
    def create_optimized_route(self, tasks: list[str]) -> list[str]:
        """
        Создает оптимальный маршрут с приоритетами
        """
        if not tasks:
            return []
        
        route = []
        remaining_tasks = tasks.copy()
        
        # 1. Приоритет: full_registration
        if 'full_registration' in remaining_tasks:
            route.append('full_registration')
            remaining_tasks.remove('full_registration')
        
        # 2. Приоритет: connect_wallet
        if 'connect_wallet' in remaining_tasks:
            route.append('connect_wallet')
            remaining_tasks.remove('connect_wallet')
        
        # 3. Приоритет: подключения соцсетей (после кошелька)
        social_connections = ['connect_twitter', 'connect_discord']
        social_tasks = [task for task in remaining_tasks if task in social_connections]
        
        # Перемешиваем соцсети случайно
        random.shuffle(social_tasks)
        route.extend(social_tasks)
        
        # Удаляем добавленные соцсети из оставшихся задач
        for task in social_tasks:
            remaining_tasks.remove(task)
        
        # 4. Приоритет: full_faucets
        if 'full_faucets' in remaining_tasks:
            route.append('full_faucets')
            remaining_tasks.remove('full_faucets')
            
        # 5. Приоритет: краны
        faucet_list = ['phrs_faucet', 'zenith_faucet']
        faucets = [task for task in remaining_tasks if task in faucet_list]
        
        # Перемешиваем краны случайно
        random.shuffle(faucets)
        route.extend(faucets)
        
        # Удаляем добавленные краны из оставшихся задач
        for task in faucets:
            remaining_tasks.remove(task)
        
        # 6. Остальные задачи в случайном порядке (кроме statistics_account)
        statistics_task = None
        if 'statistics_account' in remaining_tasks:
            statistics_task = 'statistics_account'
            remaining_tasks.remove('statistics_account')
        
        random.shuffle(remaining_tasks)
        route.extend(remaining_tasks)
        
        # 7. statistics_account всегда в конце
        if statistics_task:
            route.append(statistics_task)
        
        return route
    
    async def validate_route(self, route: list[str]) -> list[str]:
        """Фильтрует задачи без соответствующих обработчиков"""
        valid_tasks = []
        
        for task in route:
            if task in self.available_functions:
                valid_tasks.append(task)
            else:
                await logger.logger_msg(
                    f"Task '{task}' is not realized and will be skipped", "warning"
                )
        
        return valid_tasks


class TaskDelayManager:
    """Управляет задержками между задачами"""
    
    @staticmethod
    async def apply_delay_if_needed(task_index: int) -> None:
        """Применяет задержку между задачами (кроме первой)"""
        if task_index == 0:
            return
            
        if not hasattr(config, 'delay_between_tasks'):
            return
            
        delay_config = config.delay_between_tasks
        min_delay = getattr(delay_config, 'min', 0)
        max_delay = getattr(delay_config, 'max', min_delay)
        
        if min_delay > 0:
            await random_sleep(min_sec=min_delay, max_sec=max_delay)


class TaskExecutor:
    """Выполняет отдельные задачи и обрабатывает результаты"""
    
    def __init__(self, task_functions: dict[str, Callable]):
        self.task_functions = task_functions
    
    async def execute_single_task(
        self, 
        account: Account, 
        task_name: str, 
        task_index: int, 
        total_tasks: int
    ) -> dict[str, Any]:
        """Выполняет одну задачу и возвращает результат"""
        try:
            await TaskDelayManager.apply_delay_if_needed(task_index)
            
            # Выполнение задачи
            process_func = self.task_functions[task_name]
            success, message = await process_func(account)
            
            return {"success": success, "message": message}
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            await logger.logger_msg(
                f"Task execution error{task_name}: {error_msg}", "error"
            )
            return {"success": False, "message": error_msg}


class RouteStatistics:
    """Подсчитывает и форматирует статистику выполнения маршрута"""
    
    @staticmethod
    def calculate_stats(results: dict[str, dict[str, Any]]) -> tuple[int, int, float, str]:
        """Вычисляет статистику выполнения"""
        success_count = sum(1 for result in results.values() if result["success"])
        total_count = len(results)
        success_rate = (success_count / total_count) * 100 if total_count else 0
        message = f"Completed: {success_count}/{total_count} ({success_rate:.1f}%)"
        
        return success_count, total_count, success_rate, message


class TelegramReporter:
    """Отправляет отчеты в Telegram"""
    
    @staticmethod
    async def send_report_if_available(
        account: Account, 
        success_count: int,
        message: str,
        results: dict[str, dict[str, Any]]
    ) -> None:
        """Отправляет результаты в Telegram при наличии модуля"""
        try:
            if "module_processor_reporter" not in sys.modules:
                return
                
            from src.utils.telegram_reporter import TelegramReporter as TgReporter
            reporter = sys.modules["module_processor_reporter"]
            
            if isinstance(reporter, TgReporter):
                # Формируем строку с результатами для отправки
                results_str = "\n".join(
                    f"{task}: {'✅' if result['success'] else '❌'} - {result['message']}"
                    for task, result in results.items()
                )
                
                reporter.add_execution_result(
                    account,
                    success_count > 0,
                    f"{message}\n\n{results_str}",
                    "auto_route"
                )
                
        except Exception as e:
            await logger.logger_msg(f"Sending error in Telegram: {str(e)}", "warning")


class RouteManager:
    """Главный класс для управления маршрутами"""
    
    def __init__(self):
        self.task_functions = TaskFunctionLoader.load_task_functions()
        self.route_optimizer = RouteOptimizer(self.task_functions)
        self.task_executor = TaskExecutor(self.task_functions)
    
    async def execute_route(self, account: Account, route: list[str]) -> dict[str, Any]:
        """Выполняет последовательность задач для аккаунта"""
        results = {}
        total_tasks = len(route)
        
        for idx, task_name in enumerate(route):
            task_result = await self.task_executor.execute_single_task(
                account, task_name, idx, total_tasks
            )
            results[task_name] = task_result
        
        return results


async def get_validated_route() -> list[str]:
    """Создает и валидирует маршрут из конфигурации"""
    if not ROUTE_TASK:
        await logger.logger_msg(
            "ROUTE_TASK not found in the configuration or empty", "warning"
        )
        return []
    
    # Создание компонентов
    task_functions = TaskFunctionLoader.load_task_functions()
    route_optimizer = RouteOptimizer(task_functions)
    
    # Создание и валидация маршрута
    initial_route = route_optimizer.create_optimized_route(ROUTE_TASK)
    validated_route = await route_optimizer.validate_route(initial_route)
    
    # Информирование об исключенных задачах
    excluded_count = len(initial_route) - len(validated_route)
    if excluded_count > 0:
        await logger.logger_msg(
            f"Excluded {excluded_count} of unavailable tasks from the route", "warning"
        )
    
    return validated_route


async def process_route(account: Account) -> tuple[bool, str]:
    """Основной процесс выполнения маршрута для аккаунта"""
    try:
        # Получение валидного маршрута
        route = await get_validated_route()
        if not route:
            return False, "Route is empty or unavailable"
        
        # Выполнение маршрута
        manager = RouteManager()
        results = await manager.execute_route(account, route)
        
        # Подсчет статистики
        success_count, total_count, success_rate, result_message = (
            RouteStatistics.calculate_stats(results)
        )
        
        # Отправка отчета
        await TelegramReporter.send_report_if_available(
            account, success_count, result_message, results
        )
        
        return success_count > 0, result_message
        
    except Exception as e:
        error_msg = f"Critical route error: {str(e)}"
        await logger.logger_msg(error_msg, type_msg="error")
        return False, error_msg
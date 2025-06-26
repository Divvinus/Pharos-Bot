import asyncio
import os
import random
from typing import Callable, Any

from src.console import Console
from src.task_manager import PharosBot
from bot_loader import config, semaphore
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address, random_sleep
from src.utils.telegram_reporter import TelegramReporter
from route_manager import get_validated_route
from configs import AUTO_ROUTE_DELAY_RANGE_HOURS, AUTO_ROUTE_REPEAT

logger = AsyncLogger()


class AccountProgress:
    """Класс для отслеживания прогресса выполнения аккаунтов"""
    def __init__(self, total_accounts: int = 0):
        self.processed = 0
        self.success = 0
        self.total = total_accounts

    def increment(self):
        self.processed += 1
        
    def reset(self):
        self.processed = 0
        self.success = 0


# Инициализируем прогресс
progress = AccountProgress(len(config.accounts))


class TaskFunctionManager:
    """Управляет загрузкой и доступом к функциям-обработчикам"""
    
    @staticmethod
    def load_task_functions() -> dict[str, Callable]:
        """Загружает все доступные функции обработчики модулей из PharosBot"""
        return {
            attr_name[8:]: getattr(PharosBot, attr_name)
            for attr_name in dir(PharosBot)
            if attr_name.startswith('process_')
        }


class AccountDelayManager:
    """Управляет задержками перед обработкой wallet(s)"""
    
    @staticmethod
    async def apply_start_delay() -> None:
        """Применяет задержку перед началом обработки аккаунта"""
        delay_config = config.delay_before_start
        if delay_config.min > 0:
            await random_sleep(min_sec=delay_config.min, max_sec=delay_config.max)


class StatisticsManager:
    """Управляет статистикой выполнения"""
    
    @staticmethod
    async def update_progress(success: bool) -> None:
        """Обновляет глобальную статистику выполнения"""
        if success:
            progress.success += 1
            
        progress.increment()
        
        success_rate = (
            round(progress.success / progress.processed * 100, 2) 
            if progress.processed else 0
        )
        
        await logger.logger_msg(
            f"Statistics: {progress.processed}/{progress.total} wallet(s) | "
            f"Successfully: {progress.success} ({success_rate}%)",
            type_msg="info"
        )
    
    @staticmethod
    async def log_final_statistics() -> None:
        """Логирует финальную статистику выполнения"""
        if progress.total == 0:
            return
            
        success_percent = round(progress.success / progress.total * 100, 2)
        errors = progress.total - progress.success
        error_percent = round(100 - success_percent, 2)
        
        stats_lines = [
            "FINAL STATISTICS",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Successfully: {progress.success}/{progress.total} ({success_percent}%)",
            f"Errors: {errors}/{progress.total} ({error_percent}%)",
            f"Processed: {progress.processed} wallet(s)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        for line in stats_lines:
            await logger.logger_msg(line, type_msg="info")


class ResultProcessor:
    """Обрабатывает результаты выполнения модулей"""
    
    @staticmethod
    def process_module_result(result: Any, module_name: str) -> tuple[bool, str]:
        """Обрабатывает результат выполнения модуля"""
        # Для авто-роута обрабатываем особый формат ответа
        if module_name == "auto_route" and isinstance(result, tuple):
            return result[0], result[1]  # (success, message)
        
        # Для остальных модулей
        if isinstance(result, tuple) and len(result) == 2:
            return result  # (success, message)
        
        success = bool(result)
        message = "Successfully" if success else "Errors"
        return success, message


class ExcelReportGenerator:
    """Генерирует детальные отчеты в Excel"""
    
    def __init__(self, telegram_reporter: TelegramReporter):
        self.telegram_reporter = telegram_reporter
    
    def prepare_report_data(self) -> dict[str, list]:
        """Подготавливает данные для Excel-отчета"""
        data = {
            'Address': [],
            'Success': [],
            'Total modules': [],
            'Success rate': [],
            'Errors': []
        }
        
        # Собираем все модули для заголовков
        all_modules = set()
        for result in self.telegram_reporter.account_results.values():
            all_modules.update(result.modules.keys())
        
        # Добавляем колонки для каждого модуля
        for module in sorted(all_modules):
            data[f"{module} Status"] = []
            data[f"{module} Message"] = []
        
        # Заполняем данные
        for address, result in self.telegram_reporter.account_results.items():
            data['Address'].append(address)
            data['Success'].append("✅" if result.success else "❌")
            data['Total modules'].append(result.total_modules)
            data['Success rate'].append(f"{result.success_rate}%")
            data['Errors'].append(result.total_modules - result.success_count)
            
            # Данные по модулям
            for module in all_modules:
                mod_result = result.modules.get(module)
                status = "✅" if mod_result and mod_result.success else "❌" if mod_result else "⚠️"
                message = mod_result.message if mod_result else "Not fulfilled"
                
                data[f"{module} Status"].append(status)
                data[f"{module} Message"].append(message)
        
        return data


class ModuleProcessor:
    """Основной класс для обработки модулей"""
    
    def __init__(self):
        self.console = Console()
        self.telegram_reporter = TelegramReporter()
        self.task_functions = TaskFunctionManager.load_task_functions()
        self.excel_generator = ExcelReportGenerator(self.telegram_reporter)
        self.auto_route_task = None
    
    async def process_single_account(
        self, 
        account: Account, 
        process_func: Callable
    ) -> tuple[bool, str]:
        """Обрабатывает один аккаунт через указанную функцию-обработчик"""
        address = get_address(account.keypair)
        module_name = config.module
        
        async with semaphore:
            try:
                # Применяем начальную задержку
                await AccountDelayManager.apply_start_delay()
                
                # Выполняем основной процесс
                result = await process_func(account)
                
                # Обрабатываем результат
                success, message = ResultProcessor.process_module_result(result, module_name)
                
                # Обновляем статистику
                await StatisticsManager.update_progress(success)
                
                # Добавляем результат в репортер
                self.telegram_reporter.add_execution_result(
                    account, success, message, module_name=module_name
                )
                
                return success, message
                
            except Exception as e:
                progress.increment()
                error_msg = str(e)
                
                await logger.logger_msg(
                    f"Account processing error: {error_msg}", "error", address, "process_single_account"
                )
                
                self.telegram_reporter.add_execution_result(
                    account, False, error_msg, module_name=module_name
                )
                
                return False, error_msg
    
    def initialize_module_processing(self, module_name: str) -> None:
        """Инициализирует прогресс и репортер для нового модуля"""
        progress.reset()
        progress.total = len(config.accounts)
        
        self.telegram_reporter.clear_all_results()
        self.telegram_reporter.configure_reporter(
            module_name=module_name,
            send_individual_reports=getattr(config, 'send_individual_reports', True)
        )
    
    async def execute_module_for_accounts(self, process_func: Callable) -> None:
        """Выполняет обработку wallet(s) для указанного модуля"""
        try:
            await self._process_accounts_in_batches(process_func)
        except Exception as e:
            first_address = (
                get_address(config.accounts[0].keypair) 
                if config.accounts else "N/A"
            )
            await logger.logger_msg(
                f"Module execution error: {str(e)}", "error", first_address, "execute_module_for_accounts"
            )
    
    async def _process_accounts_in_batches(self, process_func: Callable) -> None:
        """Обрабатывает аккаунты батчами с учетом настройки потоков"""
        batch_size = getattr(config, 'threads', len(config.accounts))
        
        for i in range(0, len(config.accounts), batch_size):
            batch = config.accounts[i:i + batch_size]
            tasks = [
                self.process_single_account(account, process_func) 
                for account in batch
            ]
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                await logger.logger_msg(
                    f"Batch processing error: {str(e)}", "error", "_process_accounts_in_batches"
                )
    
    async def handle_auto_route_module(self) -> bool:
        route = await get_validated_route()
        if not route:
            await logger.logger_msg(
                "Auto-root is not available. Check the configuration ROUTE_TASK.", "error", "handle_auto_route_module"
            )
            return False
        if "auto_route" not in self.task_functions:
            await logger.logger_msg(
                "No autoroute handler found!", "error", "handle_auto_route_module"
            )
            return False
        await logger.logger_msg(
            f"Starting auto-route with tasks: {', '.join(route)}", "info"
        )
        cycle = 1
        while True:
            await logger.logger_msg(f"Starting auto-route cycle {cycle}", "info")
            self.initialize_module_processing("auto_route")
            await self.execute_module_for_accounts(lambda account: PharosBot.process_auto_route(account))
            await self.finalize_module_execution()
            await logger.logger_msg(f"Completed auto-route cycle {cycle}", "info")
            if not AUTO_ROUTE_REPEAT:
                break
            min_hours, max_hours = AUTO_ROUTE_DELAY_RANGE_HOURS
            delay_hours = random.uniform(min_hours, max_hours)
            delay_seconds = delay_hours * 3600
            await logger.logger_msg(f"Waiting {delay_hours:.2f} hours before the next auto-route cycle", "info")
            await asyncio.sleep(delay_seconds)
            cycle += 1
        return False
    
    async def send_telegram_reports(self) -> None:
        """Отправляет отчеты в Telegram"""
        if not getattr(config, 'send_stats_to_telegram', False) or not config.accounts:
            # Явно логируем, что отчеты не будут отправлены из-за настройки
            await logger.logger_msg(
                f"Telegram reports are disabled (send_stats_to_telegram: {getattr(config, 'send_stats_to_telegram', False)})", 
                "info"
            )
            return
            
        try:
            # Основной текстовый отчет
            await self.telegram_reporter.send_summary_report(config.accounts[0])
        except Exception as e:
            await logger.logger_msg(
                f"Telegram sending error: {str(e)}", "error"
            )
    
    async def finalize_module_execution(self) -> None:
        """Завершает выполнение модуля - отправляет отчеты и статистику"""
        await self.send_telegram_reports()
        await StatisticsManager.log_final_statistics()
    
    async def process_module(self, module_name: str) -> bool:
        """Основной метод обработки модуля. Возвращает True если нужно завершить программу"""
        # Выход из программы
        if module_name == "exit":
            await logger.logger_msg("Program Completion...", "info")
            return True
        
        # Обработка авто-роута
        if module_name == "auto_route":
            await self.handle_auto_route_module()
            await self.finalize_module_execution()
            return False
        
        # Проверка доступности модуля
        if module_name not in self.task_functions:
            await logger.logger_msg(
                f"Module ‘{module_name}’ is not implemented!", "error", "process_module"
            )
            return False
        
        # Инициализация и запуск стандартного модуля
        self.initialize_module_processing(module_name)
        await self.execute_module_for_accounts(self.task_functions[module_name])
        await self.finalize_module_execution()
        
        return False
    
    async def cleanup_resources(self) -> None:
        """Очистка ресурсов и отмена задач при завершении"""
        # Отмена всех активных задач
        current_task = asyncio.current_task()
        active_tasks = [
            task for task in asyncio.all_tasks()
            if task is not current_task and not task.done()
        ]
        
        if not active_tasks:
            return
        
        for task in active_tasks:
            task.cancel()
        
        try:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        except Exception as e:
            await logger.logger_msg(
                f"Cleaning error: {str(e)}", "error", "cleanup_resources"
            )
    
    async def run_main_loop(self) -> bool:
        """Основной цикл выполнения программы. Возвращает True если нужно завершить работу"""
        while True:
            # Построение интерфейса и выбор действия
            exit_requested, selected_action = self.console.build()
            
            if exit_requested:
                return True  # Запрос на выход
                
            if selected_action:
                config.module = selected_action
                try:
                    # Выполнение выбранного модуля
                    should_exit = await self.process_module(config.module)
                    if should_exit:
                        return True
                except Exception as e:
                    await logger.logger_msg(
                        f"Module execution error: {str(e)}", "error", "run_main_loop"
                    )
            
            # Пауза перед возвратом в меню
            input("\nPress Enter to continue...")
            os.system("cls" if os.name == "nt" else "clear")


async def main_application_loop() -> None:
    """Главный цикл приложения"""
    await logger.logger_msg("The application is running", "info")
    
    processor = None
    try:
        while True:
            try:
                # Инициализация процессора
                if processor:
                    await processor.cleanup_resources()
                processor = ModuleProcessor()
                
                # Запуск основного цикла
                exit_requested = await processor.run_main_loop()
                if exit_requested:
                    break
                    
            except KeyboardInterrupt:
                await logger.logger_msg("Manual interruption", "warning")
                break
            except Exception as e:
                await logger.logger_msg(f"Critical error: {str(e)}", "error")
                
    finally:
        # Гарантированная очистка ресурсов
        if processor:
            await processor.cleanup_resources()
        
        await logger.logger_msg("Goodbye!", "info")
        os._exit(0)
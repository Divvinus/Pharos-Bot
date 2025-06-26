"""
Модуль для создания и отправки отчетов в Telegram о выполнении задач по аккаунтам.

Основные компоненты:
- ResultModelo: модели для хранения результатов выполнения
- ReportSection: базовые секции отчета и их реализации
- TelegramReporter: главный класс для генерации и отправки отчетов
"""

from dataclasses import dataclass, field
from collections import defaultdict
import asyncio

from src.models import Account
from src.utils import get_address
from src.utils.send_tg_message import SendTgMessage
from bot_loader import config


# =============================================================================
# МОДЕЛИ ДАННЫХ ДЛЯ ХРАНЕНИЯ РЕЗУЛЬТАТОВ
# =============================================================================

@dataclass
class ModuleExecutionResult:
    """
    Результат выполнения отдельного модуля.
    
    Attributes:
        is_successful: флаг успешного выполнения
        status_message: сообщение о статусе выполнения
    """
    is_successful: bool
    status_message: str


@dataclass
class AccountExecutionResult:
    """
    Результат выполнения всех модулей для конкретного аккаунта.
    
    Attributes:
        wallet_address: адрес кошелька аккаунта
        overall_success: общий статус выполнения для аккаунта
        summary_message: общее сообщение о выполнении
        module_results: словарь результатов по модулям
    """
    wallet_address: str
    overall_success: bool
    summary_message: str
    module_results: dict[str, ModuleExecutionResult] = field(default_factory=dict)
    
    @property
    def successful_modules_count(self) -> int:
        """Возвращает количество успешно выполненных модулей."""
        return sum(1 for result in self.module_results.values() if result.is_successful)
    
    @property
    def total_modules_count(self) -> int:
        """Возвращает общее количество модулей."""
        return len(self.module_results)
    
    @property
    def success_percentage(self) -> float:
        """Возвращает процент успешно выполненных модулей."""
        if self.total_modules_count == 0:
            return 0.0
        return round(self.successful_modules_count / self.total_modules_count * 100, 2)


# =============================================================================
# БАЗОВЫЙ КЛАСС И СЕКЦИИ ОТЧЕТА
# =============================================================================

class ReportSection:
    """
    Базовый класс для создания секций отчета.
    Наследуйтесь от этого класса для создания пользовательских секций.
    """
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        """
        Генерирует содержимое секции отчета.
        
        Args:
            reporter: ссылка на экземпляр TelegramReporter
            
        Returns:
            список строк для добавления в отчет
        """
        raise NotImplementedError("Метод generate_content должен быть реализован в наследуемом классе")


class ReportHeaderSection(ReportSection):
    """Секция заголовка отчета."""
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        return [
            f"{'=' * 40}",
            f"📊 REPORT: {reporter.current_module_name.upper()} 📊",
            f"{'=' * 40}"
        ]


class GlobalStatisticsSection(ReportSection):
    """Секция общей статистики по всем аккаунтам."""
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        successful_accounts = sum(1 for result in reporter.execution_results.values() 
                                if result.overall_success)
        total_accounts = len(reporter.execution_results)
        success_rate = round(successful_accounts / total_accounts * 100, 2) if total_accounts > 0 else 0
        failed_accounts = total_accounts - successful_accounts
        failure_rate = 100 - success_rate
        
        return [
            "GENERAL STATISTICS:",
            f"✅ Successfully: {successful_accounts}/{total_accounts} ({success_rate}%)",
            f"❌ Unsuccessful: {failed_accounts}/{total_accounts} ({failure_rate}%)",
            f"{'_' * 40}"
        ]


class ModuleStatisticsSection(ReportSection):
    """Секция статистики по модулям."""
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        report_lines = []
        
        # Собираем все уникальные модули из результатов
        all_modules = {module_name 
                      for account_result in reporter.execution_results.values() 
                      for module_name in account_result.module_results.keys()}
        
        if not all_modules:
            return report_lines
            
        report_lines.append("\n📦 MODULE STATISTICS:")
        
        for module_name in sorted(all_modules):
            module_stats = self._calculate_module_statistics(reporter, module_name)
            status_emoji = self._get_status_emoji(module_stats)
            
            report_lines.extend([
                f"\n{status_emoji} {module_name}:",
                f"  Successfully: {module_stats['successful']}/{module_stats['total']} "
                f"({module_stats['success_rate']}%)"
            ])
            
            # Добавляем информацию об ошибках, если они есть
            if module_stats['errors']:
                report_lines.append("  Common errors:")
                for error_message, error_count in module_stats['errors']:
                    report_lines.append(f"  • {error_message} ({error_count}x)")
        
        return report_lines
    
    def _calculate_module_statistics(self, reporter: 'TelegramReporter', module_name: str) -> dict:
        """Вычисляет статистику для конкретного модуля."""
        successful_count = 0
        total_count = 0
        error_counter = defaultdict(int)
        
        for account_result in reporter.execution_results.values():
            if module_result := account_result.module_results.get(module_name):
                total_count += 1
                if module_result.is_successful:
                    successful_count += 1
                else:
                    error_counter[module_result.status_message] += 1
        
        success_rate = round(successful_count / total_count * 100, 2) if total_count > 0 else 0
        
        # Сортируем ошибки по частоте (по убыванию)
        sorted_errors = sorted(error_counter.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'successful': successful_count,
            'total': total_count,
            'success_rate': success_rate,
            'errors': sorted_errors
        }
    
    def _get_status_emoji(self, module_stats: dict) -> str:
        """Возвращает эмодзи статуса на основе статистики модуля."""
        if module_stats['successful'] == module_stats['total']:
            return "🟢"  # Все успешно
        elif module_stats['successful'] == 0:
            return "🔴"  # Все неудачно
        else:
            return "🟡"  # Частично успешно


class ErrorSummarySection(ReportSection):
    """Секция сводки ошибок по всем аккаунтам."""
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        if not reporter.execution_results:
            return []
        
        # Подсчитываем все ошибки
        error_counter = defaultdict(int)
        for account_result in reporter.execution_results.values():
            for module_result in account_result.module_results.values():
                if not module_result.is_successful:
                    error_counter[module_result.status_message] += 1
        
        if not error_counter:
            return ["\n✅ No errors detected"]
        
        report_lines = ["\n🚨 SUMMARY OF ERRORS:"]
        
        # Сортируем ошибки по частоте (по убыванию)
        for error_message, error_count in sorted(error_counter.items(), 
                                               key=lambda x: x[1], reverse=True):
            report_lines.append(f"• {error_message} ({error_count}x)")
        
        return report_lines


class AccountDetailsSection(ReportSection):
    """Секция детальной информации об отдельном аккаунте."""
    
    def __init__(self, target_address: str):
        """
        Инициализирует секцию для конкретного адреса.
        
        Args:
            target_address: адрес аккаунта для отчета
        """
        self.target_address = target_address
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        account_result = reporter.execution_results.get(self.target_address)
        if not account_result:
            return []
        
        successful_modules = account_result.successful_modules_count
        total_modules = account_result.total_modules_count
        success_rate = account_result.success_percentage
        failed_modules = total_modules - successful_modules
        
        report_lines = [
            f"📊 Account statistics 📊",
            f"👤 Account: {self.target_address}",
            f"✅ Successful: {successful_modules}/{total_modules} ({success_rate}%)",
            f"❌ Errors: {failed_modules}",
            f"{'_' * 30}",
            "\n🔍 Details by module:"
        ]
        
        # Добавляем информацию по каждому модулю
        for module_name, module_result in account_result.module_results.items():
            status_emoji = "✅" if module_result.is_successful else "❌"
            report_lines.append(f"{status_emoji} {module_name}: {module_result.status_message}")
        
        return report_lines


class ReportFooterSection(ReportSection):
    """Секция завершения отчета."""
    
    async def generate_content(self, reporter: 'TelegramReporter') -> list[str]:
        return [f"\n{'=' * 40}"]


# =============================================================================
# ГЛАВНЫЙ КЛАСС ОТЧЕТНОСТИ
# =============================================================================

class TelegramReporter:
    """
    Главный класс для создания и отправки отчетов в Telegram.
    
    Этот класс собирает результаты выполнения различных модулей по аккаунтам,
    генерирует структурированные отчеты и отправляет их в Telegram.
    """
    
    def __init__(self, report_sections: list[ReportSection] | None = None):
        """
        Инициализирует репортер с настройками по умолчанию.
        
        Args:
            report_sections: список секций для включения в отчет
        """
        # Хранилище результатов выполнения по аккаунтам
        self.execution_results: dict[str, AccountExecutionResult] = {}
        
        # Название текущего модуля для отчета
        self.current_module_name = "Pharos Bot"
        
        # Секции отчета (по умолчанию стандартный набор)
        self.report_sections = report_sections or self._get_default_sections()
        
        # Флаг отправки индивидуальных отчетов по аккаунтам
        self.should_send_individual_reports = True
    
    def _get_default_sections(self) -> list[ReportSection]:
        """Возвращает стандартный набор секций отчета."""
        return [
            ReportHeaderSection(),
            GlobalStatisticsSection(),
            ModuleStatisticsSection(),
            ErrorSummarySection(),
            ReportFooterSection()
        ]
    
    def set_module_name(self, module_name: str) -> None:
        """
        Устанавливает название модуля для отчетов.
        
        Args:
            module_name: название модуля
        """
        self.current_module_name = module_name
    
    def add_execution_result(
        self,
        account: Account,
        is_successful: bool,
        status_message: str,
        module_name: str | None = None
    ) -> None:
        """
        Добавляет результат выполнения модуля для аккаунта.
        
        Args:
            account: аккаунт, для которого добавляется результат
            is_successful: флаг успешного выполнения
            status_message: сообщение о статусе
            module_name: название модуля (по умолчанию текущий модуль)
        """
        wallet_address = get_address(account.keypair)
        module_name = module_name or self.current_module_name
        
        # Создаем запись для аккаунта, если её ещё нет
        if wallet_address not in self.execution_results:
            self.execution_results[wallet_address] = AccountExecutionResult(
                wallet_address=wallet_address,
                overall_success=is_successful,
                summary_message=status_message
            )
        
        # Добавляем результат модуля
        account_result = self.execution_results[wallet_address]
        account_result.module_results[module_name] = ModuleExecutionResult(
            is_successful=is_successful,
            status_message=status_message
        )
        
        # Обновляем общий статус аккаунта на основе всех модулей
        if account_result.module_results:
            account_result.overall_success = all(
                module_result.is_successful 
                for module_result in account_result.module_results.values()
            )
        
        # Планируем отправку индивидуального отчета, если включено
        if self.should_send_individual_reports and getattr(config, 'send_stats_to_telegram', False):
            self._schedule_individual_account_report(account)
    
    def _schedule_individual_account_report(self, account: Account) -> None:
        """
        Планирует отправку индивидуального отчета по аккаунту.
        
        Args:
            account: аккаунт для отправки отчета
        """
        wallet_address = get_address(account.keypair)
        if wallet_address not in self.execution_results:
            return
        
        # Создаем задачу для отправки индивидуального отчета
        asyncio.create_task(self.send_individual_account_report(account))
    
    async def send_individual_account_report(self, account: Account) -> None:
        """
        Отправляет отчет для отдельного аккаунта.
        
        Args:
            account: аккаунт для отправки отчета
        """
        # Проверяем глобальную настройку Telegram
        if not getattr(config, 'send_stats_to_telegram', False):
            return
            
        wallet_address = get_address(account.keypair)
        if wallet_address not in self.execution_results:
            return
        
        # Создаем секции для индивидуального отчета
        individual_sections = [AccountDetailsSection(wallet_address)]
        
        # Генерируем содержимое отчета
        report_content = await self._generate_report_content(individual_sections)
        
        if report_content:
            try:
                await SendTgMessage(account).send_tg_message(
                    report_content,
                    disable_notification=True  # Тихое уведомление для индивидуальных отчетов
                )
            except Exception as error:
                # Логируем ошибку, но не прерываем основной поток выполнения
                await self._log_error(
                    f"Failed to send an individual account report: {str(error)}",
                    wallet_address
                )
    
    async def send_summary_report(self, reporting_account: Account) -> None:
        """
        Отправляет сводный отчет по всем аккаунтам.
        
        Args:
            reporting_account: аккаунт для отправки сводного отчета
        """
        # Проверка включен ли отчет в Telegram
        if not getattr(config, 'send_stats_to_telegram', False):
            return
            
        if not self.execution_results:
            return
        
        # Генерируем содержимое сводного отчета
        report_content = await self._generate_report_content(self.report_sections)
        
        if report_content:
            try:
                await SendTgMessage(reporting_account).send_tg_message(report_content)
            except Exception as error:
                raise Exception(f"Failed to send a summary report to Telegram: {str(error)}") from error
    
    async def _generate_report_content(self, sections: list[ReportSection]) -> list[str]:
        """
        Генерирует содержимое отчета на основе переданных секций.
        
        Args:
            sections: список секций для генерации
            
        Returns:
            список строк содержимого отчета
        """
        report_lines = []
        
        for section in sections:
            section_content = await section.generate_content(self)
            if section_content:
                report_lines.extend(section_content)
                report_lines.append("")  # Добавляем пустую строку между секциями
        
        return report_lines
    
    async def _log_error(self, error_message: str, wallet_address: str = "") -> None:
        """
        Логирует ошибку в системный лог.
        
        Args:
            error_message: сообщение об ошибке
            wallet_address: адрес кошелька (опционально)
        """
        try:
            from src.logger import AsyncLogger
            logger = AsyncLogger()
            await logger.logger_msg(
                error_message,
                type_msg="error",
                address=wallet_address
            )
        except Exception:
            # Если даже логирование не удалось, просто игнорируем
            pass
    
    def clear_all_results(self) -> None:
        """Очищает все сохраненные результаты выполнения."""
        self.execution_results.clear()
    
    def configure_reporter(
        self,
        report_sections: list[ReportSection] | None = None,
        module_name: str | None = None,
        send_individual_reports: bool | None = None
    ) -> None:
        """
        Настраивает параметры репортера.
        
        Args:
            report_sections: новый список секций отчета
            module_name: новое название модуля
            send_individual_reports: флаг отправки индивидуальных отчетов
        """
        if report_sections is not None:
            self.report_sections = report_sections
        if module_name is not None:
            self.current_module_name = module_name
        if send_individual_reports is not None:
            self.should_send_individual_reports = send_individual_reports
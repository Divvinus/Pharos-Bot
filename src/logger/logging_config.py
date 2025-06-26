import sys
import time
from pathlib import Path
from typing import Literal, ClassVar
from functools import lru_cache

import aiofiles
from aiologger import Logger
from aiologger.levels import LogLevel
from aiologger.handlers.base import Handler
from colorama import init, Fore, Style

init(autoreset=True)

ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
LOGS_FILE_PATH = ROOT_DIR / "logs"


class FileFormatter:
    __slots__ = ('_time_format',)
    
    def __init__(self):
        self._time_format = "%H:%M:%S"
    
    def format(self, record) -> str:
        formatted_time = time.strftime(
            self._time_format, 
            time.localtime(record.created)
        )
        levelname = record.levelname
        
        if record.levelname == "INFO" and record.msg.startswith("[success]"):
            levelname = "SUCCESS"
            record.msg = record.msg[10:].lstrip()
        
        max_level_length = 8
        padding = " " * (max_level_length - len(levelname))
        
        return (
            f"[{formatted_time}] | "
            f"[{levelname}]{padding} | {record.msg}"
        )


class AsyncLevelFileHandler(Handler):
    __slots__ = ('base_name', 'file_path', 'formatter', '_initialized')
    
    def __init__(self, base_name: str = "file", level=LogLevel.DEBUG) -> None:
        super().__init__(level=level)
        self.base_name = base_name
        self.file_path = LOGS_FILE_PATH / f"{base_name}.log"
        self.formatter = FileFormatter()
        self._initialized = False

    async def initialize(self) -> None:
        if not LOGS_FILE_PATH.exists():
            LOGS_FILE_PATH.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def emit(self, record) -> None:
        if not self._initialized:
            await self.initialize()
        message = self.formatter.format(record)
        async with aiofiles.open(self.file_path, mode="a", encoding="utf-8") as f:
            await f.write(message + "\n")

    async def close(self) -> None:
        self._initialized = False


class ColoredFormatter:
    __slots__ = ('_time_format',)
    
    LEVEL_COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.WHITE,
        "SUCCESS": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
    }
    
    def __init__(self):
        self._time_format = "%H:%M:%S"

    def format(self, record) -> str:
        formatted_time = time.strftime(
            self._time_format, 
            time.localtime(record.created)
        )
        levelname = record.levelname
        level_color = self.LEVEL_COLORS.get(levelname, Fore.WHITE)

        if record.levelname == "INFO" and record.msg.startswith("[success]"):
            levelname = "SUCCESS"
            level_color = self.LEVEL_COLORS["SUCCESS"]
            record.msg = record.msg[10:].lstrip()

        max_level_length = 8
        padding = " " * (max_level_length - len(levelname))

        time_part = f"{Fore.CYAN}[{formatted_time}]{Style.RESET_ALL}"
        level_part = f"{level_color}[{levelname}]{padding}{Style.RESET_ALL}"
        msg_part = f"{level_color}{record.msg}{Style.RESET_ALL}"

        return f"{time_part} | {level_part} | {msg_part}"


class AsyncConsoleHandler(Handler):
    __slots__ = ('formatter', '_initialized')
    
    def __init__(self, level=LogLevel.DEBUG) -> None:
        super().__init__(level=level)
        self.formatter = ColoredFormatter()
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def emit(self, record) -> None:
        message = self.formatter.format(record)
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    async def close(self) -> None:
        self._initialized = False


class AsyncLogger:
    __slots__ = ('_logger', '_log_type_methods')
    
    def __init__(
        self,
        name: str = "Pharos Bot",
        file_base_name: str = "app_log"
    ) -> None:
        self._logger = Logger(name=name, level=LogLevel.INFO)

        if not LOGS_FILE_PATH.exists():
            LOGS_FILE_PATH.mkdir(parents=True, exist_ok=True)

        console_handler = AsyncConsoleHandler(level=LogLevel.DEBUG)
        file_handler = AsyncLevelFileHandler(base_name=file_base_name, level=LogLevel.DEBUG)
        
        self._logger.add_handler(console_handler)
        self._logger.add_handler(file_handler)
        
        self._log_type_methods = {
            "success": self._logger.info,
            "info": self._logger.info,
            "error": self._logger.error,
            "warning": self._logger.warning,
            "debug": self._logger.debug
        }

    @lru_cache(maxsize=128)
    def _build_info(
        self,
        account_name: str | None,
        address: str | None,
        class_name: str | None,
        method_name: str | None,
    ) -> str:
        info_parts = []
        if account_name and account_name != "Account":
            info_parts.append(f"[{account_name}]")
        if address:
            info_parts.append(f"[{address}]")
        # Убрали class_name и method_name из логов
        return " | ".join(info_parts)

    async def logger_msg(
        self,
        msg: str = "",
        type_msg: Literal["info", "error", "success", "warning", "debug"] = "info",
        account_name: str | None = "Account",
        address: str | None = None,
        class_name: str | None = None,
        method_name: str | None = None,
    ) -> None:
        # Класс и метод больше не добавляются в логи
        info = self._build_info(
            account_name,
            address,
            None,  # class_name не используется
            None   # method_name не используется
        )
        full_msg = f"{info} {msg}" if info else msg
        
        log_method = self._log_type_methods[type_msg]

        if type_msg == "success":
            await log_method(f"[success] {full_msg}")
        else:
            await log_method(full_msg)

    def get_logger(self) -> Logger:
        return self._logger
import telebot
import re
import io
import pandas as pd

from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address
from bot_loader import config


class SendTgMessage(AsyncLogger):
    def __init__(self, account: Account):
        AsyncLogger.__init__(self)
        
        self.wallet_address = get_address(account.keypair)
        self.bot = telebot.TeleBot(config.tg_token)
        self.chat_id = config.tg_id

    async def send_tg_message(self, message_to_send: list[str], disable_notification: bool = False) -> None:
        try:
            # Escape special characters for Markdown
            markdown_escape_pattern = re.compile(r'([_*\[\]()~`>#+\-=|{}.!])')

            formatted = []
            for line in message_to_send:
                escaped_line = markdown_escape_pattern.sub(r'\\\1', line)
                # Highlight special lines with bold formatting
                if any(c in line for c in ['=', '-', '📊', '📈', '✅', '❌', '🟢', '🔴', '🟡']):
                    formatted.append(f"*{escaped_line}*")
                else:
                    formatted.append(escaped_line)
            
            str_send = '\n'.join(formatted)

            self.bot.send_message(
                self.chat_id, 
                str_send, 
                parse_mode='MarkdownV2', 
                disable_notification=disable_notification
            )
            
            await self.logger_msg(
                f"The message was sent in Telegram", "success", self.wallet_address
            )

        except Exception as error:
            await self.logger_msg(
                f"Telegram | Error API: {error}", "error", self.wallet_address, "send_tg_message"
            )
    
    async def send_table_report(self, data: dict, title: str = "Report") -> None:
        """
        Send a formatted table report to Telegram
        
        :param data: Dictionary with table data
        :param title: Report title
        """
        try:
            # Convert data to DataFrame and then to Excel
            df = pd.DataFrame(data)
            
            # Create Excel in memory
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False)
            excel_buffer.seek(0)
            
            # Send Excel file
            self.bot.send_document(
                self.chat_id,
                excel_buffer,
                caption=f"📊 {title}",
                visible_file_name=f"{title.replace(' ', '_')}.xlsx"
            )
            
            await self.logger_msg(
                f"Excel report was sent in Telegram", "success", self.wallet_address
            )
        except Exception as error:
            await self.logger_msg(
                f"Telegram | Error sending Excel report: {error}", "error", self.wallet_address, "send_table_report"
            )
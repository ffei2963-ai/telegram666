"""TG Cloud Controller - 入口 (Telethon引擎)"""

import asyncio
import signal
import sys
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)
from db.database import Database
from core.account_manager import AccountManager
from core.ai_service import AIService
from core.telethon_engine import get_engine
from core.message_monitor import get_monitor
from core.group_scraper import GroupScraper
from core.translator import get_translator
from bot.handlers import BotHandlers
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger("tg-controller", config.log_level)


class TGController:
    def __init__(self):
        self.db = Database(config.db_path)
        self.account_mgr = AccountManager(self.db, config.sessions_dir, config.uploads_dir)
        max_cc = int(self.db.get_setting("max_concurrent", str(config.max_concurrent_accounts)))
        batch_delay = float(self.db.get_setting("batch_delay", "0.5"))
        rand_min = float(self.db.get_setting("random_delay_min", "0.8"))
        rand_max = float(self.db.get_setting("random_delay_max", "3.5"))
        self.ai = AIService(
            api_key=self.db.get_setting("deepseek_api_key", config.deepseek_api_key),
            model=self.db.get_setting("deepseek_model", config.deepseek_model),
            base_url=config.deepseek_base_url,
        )
        self.engine = get_engine(db=self.db, sessions_dir=config.sessions_dir,
                                 max_concurrent=max_cc, batch_delay=batch_delay,
                                 random_delay_min=rand_min, random_delay_max=rand_max)
        self.monitor = get_monitor(self.db, self.engine)
        self.scraper = GroupScraper(self.db, self.engine)
        self.translator = get_translator()
        self.handlers = BotHandlers(self.db, self.account_mgr, self.ai, self.engine,
                                    self.monitor, self.scraper, self.translator)
        self.app = None

    def start(self):
        if not config.bot_token:
            logger.error("未配置 TG_BOT_TOKEN！请在 .env 文件或环境变量中设置。")
            sys.exit(1)

        logger.info("TG Cloud Controller v4.0 (Telethon引擎) 启动中...")
        logger.info("Bot Token: %s...", config.bot_token[:8])
        logger.info("管理员IDs: %s", config.admin_user_ids or "无限制")

        self.app = Application.builder().token(config.bot_token).build()
        self.app.add_handler(CommandHandler("start", self.handlers.start))
        self.app.add_handler(CommandHandler("menu", self.handlers.start))
        self.app.add_handler(CommandHandler("reply", self.handlers._handle_reply_command))
        self.app.add_handler(CallbackQueryHandler(self.handlers.button_handler))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handlers.handle_document))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_text))
        self.app.add_error_handler(self.handlers.error_handler)

        logger.info("Bot 已启动，使用 Telethon MTProto 引擎")
        self.app.run_polling(allowed_updates=["message", "callback_query"])

    def stop(self):
        if self.app:
            try:
                asyncio.run(self.app.shutdown())
            except Exception:
                pass
        try:
            asyncio.run(self.engine.disconnect_all())
        except Exception:
            pass


def main():
    controller = TGController()
    try:
        controller.start()
    except KeyboardInterrupt:
        controller.stop()
    except Exception as e:
        logger.error("启动失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

"""消息监听 + 自动翻译回复服务"""

import asyncio
from telethon import events
from core.telethon_engine import get_engine
from core.translator import get_translator
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MessageMonitor:
    def __init__(self, db, engine=None):
        self.db = db
        self.engine = engine or get_engine()
        self.translator = get_translator()
        self._running = {}
        self._bot = None

    def set_bot(self, bot_app):
        self._bot = bot_app

    async def start_monitoring(self, account_id: int):
        if account_id in self._running:
            return

        client = await self.engine.get_client(account_id)
        if not client:
            logger.warning("账号 %d 无法连接，跳过监听", account_id)
            return

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            await self._on_message(account_id, event)

        self._running[account_id] = client
        logger.info("账号 %d 消息监听已启动", account_id)

    async def stop_monitoring(self, account_id: int):
        if account_id in self._running:
            del self._running[account_id]
            logger.info("账号 %d 消息监听已停止", account_id)

    async def stop_all(self):
        for aid in list(self._running.keys()):
            await self.stop_monitoring(aid)

    async def _on_message(self, account_id: int, event):
        try:
            msg = event.message
            if not msg.message:
                return

            sender = await event.get_sender()
            sender_id = sender.id if sender else 0
            sender_name = (sender.first_name or "") if sender else ""
            sender_username = sender.username if sender else ""
            content_raw = msg.message

            content_zh = self.translator.to_chinese(content_raw)

            msg_id = self.db.add_message(
                account_id=account_id,
                chat_id=event.chat_id,
                sender_id=sender_id,
                sender_username=sender_username or sender_name,
                content_raw=content_raw[:2000],
                content_zh=content_zh[:2000],
                direction="received",
            )

            acc = self.db.get_account(account_id) or {"name": f"ID:{account_id}", "phone": ""}

            if self._bot:
                admin_ids_str = self.db.get_setting("admin_ids", "")
                admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
                for uid in admin_ids:
                    try:
                        await self._bot.send_message(
                            chat_id=uid,
                            text=(
                                f"📩 *新消息 #{msg_id}*\n"
                                f"账号: `{acc['name']}` (+{acc['phone']})\n"
                                f"来自: {sender_name} (@{sender_username})\n\n"
                                f"原文:\n{content_raw[:400]}\n\n"
                                f"翻译:\n{content_zh[:400]}"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass

            logger.info("[监听] 账号%d 收到消息: %s", account_id, content_raw[:50])

        except Exception as e:
            logger.error("消息处理失败 (aid=%d): %s", account_id, e)

    async def send_reply(self, account_id: int, chat_id: int, text_cn: str) -> dict:
        """发送中文回复 (自动翻译成英文)"""
        client = await self.engine.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}

        translated = self.translator.to_english(text_cn)
        try:
            await client.send_message(chat_id, translated)
            self.db.add_message(
                account_id=account_id, chat_id=chat_id,
                sender_id=0, sender_username="",
                content_raw=translated, content_zh=text_cn,
                direction="sent",
            )
            return {"success": True, "translated": translated}
        except Exception as e:
            return {"success": False, "error": str(e)}


_monitor = None


def get_monitor(db=None, engine=None) -> MessageMonitor:
    global _monitor
    if _monitor is None and db is not None:
        _monitor = MessageMonitor(db, engine)
    return _monitor

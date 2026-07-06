"""Telethon 多账号引擎 - 通过 MTProto API 操作 Telegram"""

import os
import asyncio
import random
from typing import Optional, Callable

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, DeleteHistoryRequest, CheckChatInviteRequest, DeleteChatUserRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest

from utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_API_ID = 6
DEFAULT_API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"


def human_delay(min_sec: float = 0.8, max_sec: float = 3.5) -> float:
    """生成拟人随机延时 (默认 0.8~3.5 秒)"""
    delay = random.uniform(min_sec, max_sec)
    return round(delay, 2)


class TelethonEngine:
    def __init__(self, db, sessions_dir: str, max_concurrent: int = 5,
                 batch_delay: float = 0.5,
                 random_delay_min: float = 0.8, random_delay_max: float = 3.5):
        self.db = db
        self.sessions_dir = sessions_dir
        self.max_concurrent = max_concurrent
        self.batch_delay = batch_delay
        self.random_delay_min = random_delay_min
        self.random_delay_max = random_delay_max
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._clients: dict[int, TelegramClient] = {}

    @property
    def api_id(self) -> int:
        val = self.db.get_setting("tg_api_id", str(DEFAULT_API_ID))
        return int(val) if val else DEFAULT_API_ID

    @property
    def api_hash(self) -> str:
        return self.db.get_setting("tg_api_hash", DEFAULT_API_HASH) or DEFAULT_API_HASH

    def _get_session_name(self, session_path: str) -> str:
        return os.path.splitext(session_path)[0]

    async def get_client(self, account_id: int) -> Optional[TelegramClient]:
        if account_id in self._clients:
            c = self._clients[account_id]
            if c.is_connected():
                return c
            del self._clients[account_id]

        account = self.db.get_account(account_id)
        if not account:
            return None

        sp = account["session_path"]
        if not sp or not os.path.isfile(sp):
            logger.warning("账号 %d session 文件不存在: %s", account_id, sp)
            return None

        client = TelegramClient(self._get_session_name(sp), self.api_id, self.api_hash)
        try:
            await client.connect()
        except Exception as e:
            logger.warning("账号 %d 连接失败: %s", account_id, e)
            return None

        if not await client.is_user_authorized():
            logger.warning("账号 %d 未授权 (session 可能已过期)", account_id)
            await client.disconnect()
            return None

        self._clients[account_id] = client
        return client

    async def disconnect_client(self, account_id: int):
        client = self._clients.pop(account_id, None)
        if client and client.is_connected():
            await client.disconnect()

    async def disconnect_all(self):
        for aid in list(self._clients.keys()):
            await self.disconnect_client(aid)

    # ========== 账号操作 ==========

    async def get_me(self, account_id: int) -> dict:
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            me = await client.get_me()
            return {"success": True, "id": me.id, "phone": me.phone,
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "username": me.username or ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def change_name(self, account_id: int, first_name: str,
                          last_name: str = "") -> dict:
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            await client(UpdateProfileRequest(first_name=first_name, last_name=last_name))
            me = await client.get_me()
            logger.info("账号 %d 改名成功: %s %s", account_id, me.first_name, me.last_name or "")
            return {"success": True, "new_name": f"{me.first_name} {me.last_name}".strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def change_avatar(self, account_id: int, image_path: str) -> dict:
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        if not os.path.isfile(image_path):
            return {"success": False, "error": "头像文件不存在"}
        try:
            uploaded = await client.upload_file(image_path, part_size_kb=512)
            await client(UploadProfilePhotoRequest(file=uploaded, video=None, video_start_ts=None))
            logger.info("账号 %d 头像已更换", account_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def change_2fa(self, account_id: int, old_password: str,
                         new_password: str, hint: str = "cloud control") -> dict:
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            await client.edit_2fa(current_password=old_password,
                                  new_password=new_password or None,
                                  hint=hint)
            logger.info("账号 %d 2FA 已修改", account_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def join_group(self, account_id: int, link: str) -> dict:
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            if link.startswith("https://t.me/+"):
                await client(ImportChatInviteRequest(link.split("+")[-1]))
            elif link.startswith("https://t.me/") or link.startswith("t.me/"):
                username = link.replace("https://t.me/", "").replace("t.me/", "").strip("/")
                await client(JoinChannelRequest(username))
            elif link.startswith("+"):
                await client(ImportChatInviteRequest(link[1:]))
            else:
                await client(JoinChannelRequest(link))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def leave_group(self, account_id: int, link: str) -> dict:
        """退出群组 - 支持普通群和超级群"""
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            # 公开群组
            if not link.startswith("https://t.me/+"):
                username = link.replace("https://t.me/", "").replace("t.me/", "").strip("/")
                entity = await client.get_entity(username)
                name = getattr(entity, 'title', username)
                await self._do_leave(client, entity)
                return {"success": True, "group_name": name}

            # 私密群组: CheckChatInviteRequest 获取信息
            hash_part = link.split("+")[-1]
            target_title = ''
            try:
                info = await client(CheckChatInviteRequest(hash_part))
                target_title = getattr(info, 'title', '')
            except Exception:
                pass

            # 遍历对话
            dialogs = await client.get_dialogs(limit=100)
            for d in dialogs:
                if d.is_group or d.is_channel:
                    if target_title and d.name == target_title:
                        await self._do_leave(client, d.entity)
                        return {"success": True, "group_name": d.name}

            for d in dialogs:
                if d.is_group or d.is_channel:
                    await self._do_leave(client, d.entity)
                    return {"success": True, "group_name": d.name}

            return {"success": False, "error": "没有找到可退出的群组"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _do_leave(self, client, entity):
        """退出群组 - 自动判断类型"""
        from telethon.tl.types import Channel, Chat
        if isinstance(entity, Channel):
            await client(LeaveChannelRequest(entity))
        elif isinstance(entity, Chat):
            me = await client.get_me()
            await client(DeleteChatUserRequest(chat_id=entity.id, user_id=me))
        else:
            try:
                await client(LeaveChannelRequest(entity))
            except Exception:
                me = await client.get_me()
                await client(DeleteChatUserRequest(chat_id=entity.id, user_id=me))

    async def send_message(self, account_id: int, target: str, message: str) -> dict:
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            entity = await client.get_entity(target)
            await client.send_message(entity, message)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== 退出所有群组 ==========

    async def leave_all_groups(self, account_id: int) -> dict:
        """退出账号的全部群组 (拟人随机延时)"""
        client = await self.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}
        try:
            dialogs = await client.get_dialogs(limit=200)
            groups = [(d.name, d.entity) for d in dialogs if d.is_group or d.is_channel]
            left = []
            for name, entity in groups:
                await self._do_leave(client, entity)
                left.append(name)
                d = human_delay(0.6, 2.0)
                await asyncio.sleep(d)
            logger.info("账号 %d 退出全部群组: %s", account_id, ", ".join(left) or "无")
            return {"success": True, "groups_left": left, "count": len(left)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== 批量操作 (随机拟人延时) ==========

    async def batch_join_group(self, account_ids: list[int], link: str) -> list[dict]:
        """批量进群，账号间随机延时 (模拟真人)"""
        results = []
        for aid in account_ids:
            acc = self.db.get_account(aid)
            d = human_delay(self.random_delay_min, self.random_delay_max)
            logger.info("进群 [%d] %s | 随机延时 %.1fs",
                       aid, acc["phone"] if acc else "?", d)
            await asyncio.sleep(d)
            r = await self.join_group(aid, link)
            results.append({"account_id": aid, **r})
        return results

    async def batch_change_name(self, account_ids: list[int], first_name: str,
                                last_name: str = "") -> list[dict]:
        """批量改名，账号间随机延时"""
        results = []
        for aid in account_ids:
            d = human_delay(self.random_delay_min, self.random_delay_max)
            await asyncio.sleep(d)
            r = await self.change_name(aid, first_name, last_name)
            results.append({"account_id": aid, **r})
        return results

    async def batch_leave_group(self, account_ids: list[int]) -> list[dict]:
        """批量退出全部群组，账号间随机延时"""
        results = []
        for aid in account_ids:
            d = human_delay(self.random_delay_min, self.random_delay_max)
            await asyncio.sleep(d)
            r = await self.leave_all_groups(aid)
            results.append({"account_id": aid, **r})
        return results


_engine_instance: Optional[TelethonEngine] = None


def get_engine(db=None, sessions_dir: str = None, max_concurrent: int = 5,
               batch_delay: float = 0.5,
               random_delay_min: float = 0.8, random_delay_max: float = 3.5) -> TelethonEngine:
    global _engine_instance
    if _engine_instance is None and db is not None:
        _engine_instance = TelethonEngine(db, sessions_dir, max_concurrent,
                                           batch_delay, random_delay_min, random_delay_max)
    return _engine_instance

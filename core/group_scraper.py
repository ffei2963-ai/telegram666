"""群组搜索与成员提取 - 基于 Telethon API"""

import asyncio
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from utils.logger import setup_logger

logger = setup_logger(__name__)


class GroupScraper:

    def __init__(self, db, engine=None):
        self.db = db
        self.engine = engine

    async def search_groups(self, account_id: int, keyword: str, limit: int = 20) -> dict:
        """搜索公开群组"""
        client = await self.engine.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}

        try:
            results = []
            dialogs = await client.get_dialogs(limit=200)
            for d in dialogs:
                if (d.is_group or d.is_channel) and keyword.lower() in d.name.lower():
                    results.append({
                        "id": d.id, "title": d.name,
                        "username": getattr(d.entity, "username", "") or "",
                        "members": getattr(d.entity, "participants_count", 0) or 0,
                    })

            if not results:
                try:
                    search = await client(SearchRequest(
                        q=keyword, limit=min(limit, 100),
                    ))
                    for chat in search.chats:
                        results.append({
                            "id": chat.id, "title": chat.title,
                            "username": getattr(chat, "username", "") or "",
                            "members": getattr(chat, "participants_count", 0) or 0,
                        })
                except Exception:
                    pass

            return {"success": True, "count": len(results), "groups": results[:limit]}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_members(self, account_id: int, group_username: str, limit: int = 200) -> dict:
        """提取群组成员"""
        client = await self.engine.get_client(account_id)
        if not client:
            return {"success": False, "error": "无法连接"}

        try:
            entity = await client.get_entity(group_username)
            title = getattr(entity, "title", group_username)
            gid = getattr(entity, "id", 0)

            participants = await client.get_participants(entity, limit=limit)
            saved = 0
            for p in participants:
                try:
                    self.db.conn.execute(
                        """INSERT OR IGNORE INTO group_members
                           (account_id, group_id, group_title, user_id,
                            username, first_name, last_name, phone)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (account_id, gid, title, p.id,
                         p.username or "", p.first_name or "",
                         p.last_name or "", getattr(p, "phone", "") or "")
                    )
                    saved += 1
                except Exception:
                    pass
            self.db.conn.commit()

            logger.info("提取成员: %s (%d人)", title, saved)
            return {"success": True, "group": title, "count": saved,
                    "members": [{"id": p.id, "username": p.username or "",
                                 "name": (p.first_name or "") + " " + (p.last_name or "")}
                                for p in participants[:50]]}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_saved_members(self, group_title: str = None, limit: int = 100) -> list:
        if group_title:
            rows = self.db.conn.execute(
                "SELECT * FROM group_members WHERE group_title=? LIMIT ?",
                (group_title, limit)
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT * FROM group_members ORDER BY scraped_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_members(self, group_title: str = None) -> int:
        if group_title:
            row = self.db.conn.execute(
                "SELECT COUNT(*) as c FROM group_members WHERE group_title=?", (group_title,)
            ).fetchone()
        else:
            row = self.db.conn.execute("SELECT COUNT(*) as c FROM group_members").fetchone()
        return row["c"] if row else 0

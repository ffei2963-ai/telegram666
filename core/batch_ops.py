"""批量操作引擎 - 并行执行批量 Telegram 操作"""

import asyncio
from typing import Union, Optional
from dataclasses import dataclass

from core.telethon_engine import get_engine
from utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class BatchTask:
    task_db_id: int
    task_type: str
    account_ids: list
    params: dict
    status: str = "pending"
    results: list = None

    def __post_init__(self):
        self.results = []


class BatchOpsEngine:
    def __init__(self, db):
        self.db = db

    def _get_account_ids(self, target_type: str, target_ids: list) -> list:
        if not target_ids:
            return [a["id"] for a in self.db.list_accounts(limit=1000)]

        if target_type == "groups":
            ids = set()
            for gid in target_ids:
                accounts = self.db.list_accounts(group_id=gid, limit=10000)
                ids.update(a["id"] for a in accounts)
            return list(ids)

        if target_type == "accounts":
            return target_ids

        return target_ids

    async def run_task(self, task_id: int) -> dict:
        task = self.db.get_task(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        if task["status"] not in ("pending",):
            return {"success": False, "error": f"任务状态异常: {task['status']}"}

        import json
        target_ids = json.loads(task["target_ids"])
        params = json.loads(task["params"])
        account_ids = self._get_account_ids(task["target_type"], target_ids)
        task_type = task["task_type"]

        if not account_ids:
            self.db.update_task(task_id, status="failed", result="没有可用的账号")
            return {"success": False, "error": "没有可用的账号"}

        total = len(account_ids)
        self.db.update_task(task_id, status="running", progress=f"0/{total}")

        engine = get_engine()
        results = []
        completed = 0

        sem = asyncio.Semaphore(5)

        async def process_one(aid):
            nonlocal completed
            async with sem:
                try:
                    if task_type == "join_group":
                        r = await engine.join_group(aid, params.get("link", ""))
                    elif task_type == "change_avatar":
                        r = await engine.change_avatar(aid, params.get("avatar_path", ""))
                    elif task_type == "change_name":
                        r = await engine.change_name(aid, params.get("first_name"),
                                                     params.get("last_name"),
                                                     params.get("bio"))
                    elif task_type == "change_2fa":
                        r = await engine.change_2fa(aid, params.get("old_password", ""),
                                                    params.get("new_password", ""),
                                                    params.get("email", ""))
                    elif task_type == "mass_dm":
                        r = await engine.send_message(aid, params.get("target", ""),
                                                      params.get("message", ""))
                    elif task_type == "get_participants":
                        r = await engine.get_participants(aid, params.get("group", ""),
                                                          params.get("limit", 200))
                    else:
                        r = {"success": False, "error": f"未知任务类型: {task_type}"}
                except Exception as e:
                    r = {"success": False, "error": str(e)}

                results.append({**r, "account_id": aid})
                completed += 1
                if completed % 10 == 0 or completed == total:
                    self.db.update_task(task_id, progress=f"{completed}/{total}")
                    logger.info("任务 %d 进度: %d/%d", task_id, completed, total)

        await asyncio.gather(*[process_one(aid) for aid in account_ids])

        success_count = sum(1 for r in results if r.get("success"))
        fail_count = total - success_count

        import json
        result_summary = json.dumps({
            "total": total,
            "success": success_count,
            "failed": fail_count,
            "details": results[:100],
        }, ensure_ascii=False)

        final_status = "completed" if fail_count == 0 else "partial"
        self.db.update_task(task_id, status=final_status, progress=f"{total}/{total}",
                           result=result_summary)

        # If this was a participants extraction, save to DB
        if task_type == "get_participants":
            for r in results:
                if r.get("success") and r.get("result"):
                    group_id = params.get("group", "")
                    for member in r["result"]:
                        try:
                            self.db.conn.execute(
                                """INSERT OR IGNORE INTO group_members
                                   (account_id, group_id, group_title, user_id,
                                    username, first_name, last_name, phone)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (r["account_id"], 0, group_id,
                                 member["user_id"], member["username"],
                                 member["first_name"], member["last_name"],
                                 member.get("phone", ""))
                            )
                        except Exception:
                            pass
                self.db.conn.commit()

        return {"success": True, "results": results[:20], "total": total,
                "success_count": success_count, "fail_count": fail_count}

    def create_task(self, task_type: str, target_type: str, target_ids: list,
                    params: dict) -> int:
        valid_types = ("join_group", "change_avatar", "change_name",
                      "change_2fa", "mass_dm", "get_participants")
        if task_type not in valid_types:
            raise ValueError(f"无效的任务类型: {task_type}")
        return self.db.add_task(task_type, target_type, target_ids, params)

    def get_task_status(self, task_id: int) -> Optional[dict]:
        return self.db.get_task(task_id)

    def list_tasks(self, status: str = None, limit: int = 20) -> list:
        return self.db.list_tasks(status=status, limit=limit)

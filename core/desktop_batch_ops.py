"""桌面版批量操作引擎 - 基于 Telegram Desktop UI 自动化"""

import asyncio
from core.desktop_manager import get_desktop
from core.desktop_automation import DesktopAutomation
from utils.logger import setup_logger

logger = setup_logger(__name__)

BATCH_TYPES = {
    "join_group": "批量进群",
    "change_name": "批量修改名字",
    "mass_dm": "群发私信",
}


class DesktopBatchOps:

    def __init__(self, db):
        self.db = db
        self.desktop = get_desktop()
        self.auto = DesktopAutomation(self.desktop._display)

    def _get_account_ids(self, target_type: str, target_ids: list) -> list:
        if not target_ids:
            return [a["id"] for a in self.db.list_accounts(limit=1000)]
        if target_type == "groups":
            ids = set()
            for gid in target_ids:
                accounts = self.db.list_accounts(group_id=gid, limit=10000)
                ids.update(a["id"] for a in accounts)
            return list(ids)
        return target_ids

    def run_task_sync(self, task_id: int) -> dict:
        """同步执行批量任务（一次一个账号，逐个操作）"""
        import json
        task = self.db.get_task(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}

        target_ids = json.loads(task["target_ids"])
        params = json.loads(task["params"])
        account_ids = self._get_account_ids(task["target_type"], target_ids)
        task_type = task["task_type"]

        if not account_ids:
            self.db.update_task(task_id, status="failed", result="没有可用的账号")
            return {"success": False, "error": "没有可用的账号"}

        total = len(account_ids)
        self.db.update_task(task_id, status="running", progress=f"0/{total}")

        results = []
        for i, aid in enumerate(account_ids):
            account = self.db.get_account(aid)
            if not account:
                results.append({"account_id": aid, "success": False, "error": "账号不存在"})
                continue

            name = account["name"]
            if not self.desktop.account_has_tdata(name):
                results.append({"account_id": aid, "success": False, "error": "无tdata"})
                continue

            try:
                self.desktop.switch_to_account(name)
                result = {"account_id": aid, "success": False}

                if task_type == "join_group":
                    r = self.auto.join_group(params.get("link", ""))
                elif task_type == "change_name":
                    r = self.auto.modify_profile(
                        first_name=params.get("first_name"),
                        last_name=params.get("last_name"),
                    )
                elif task_type == "mass_dm":
                    r = self.auto.send_message(
                        params.get("target", ""),
                        params.get("message", ""),
                    )
                else:
                    r = {"success": False, "error": f"未知类型: {task_type}"}

                results.append(r)
            except Exception as e:
                results.append({"account_id": aid, "success": False, "error": str(e)})

            self.db.update_task(task_id, progress=f"{i+1}/{total}")
            logger.info("任务 %d 进度: %d/%d", task_id, i + 1, total)

        success = sum(1 for r in results if r.get("success"))
        final_status = "completed" if success == total else "partial"
        self.db.update_task(
            task_id, status=final_status, progress=f"{total}/{total}",
            result=json.dumps({"total": total, "success": success, "failed": total - success},
                             ensure_ascii=False)
        )

        return {"success": True, "total": total, "success_count": success}

    def create_task(self, task_type: str, target_type: str, target_ids: list,
                    params: dict) -> int:
        valid = ("join_group", "change_name", "mass_dm")
        if task_type not in valid:
            raise ValueError(f"无效任务类型: {task_type}")
        return self.db.add_task(task_type, target_type, target_ids, params)

    def get_task_status(self, task_id: int) -> dict:
        return self.db.get_task(task_id)

    def list_tasks(self, status: str = None, limit: int = 20) -> list:
        return self.db.list_tasks(status=status, limit=limit)

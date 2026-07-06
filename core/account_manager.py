"""账号管理 - ZIP导入、分组、列表查询"""

import os
import shutil
import uuid
from typing import Optional

from db.database import Database
from core.tdata_handler import extract_account_info
from utils.logger import setup_logger

logger = setup_logger(__name__)


class AccountManager:

    def __init__(self, db: Database, sessions_dir: str, uploads_dir: str):
        self.db = db
        self.sessions_dir = sessions_dir
        self.uploads_dir = uploads_dir
        os.makedirs(sessions_dir, exist_ok=True)
        os.makedirs(uploads_dir, exist_ok=True)

    def import_from_zip(self, zip_path: str) -> list[dict]:
        """从 ZIP 导入账号"""
        import zipfile
        results = []
        extract_base = os.path.join(self.uploads_dir, f"extract_{uuid.uuid4().hex[:8]}")
        os.makedirs(extract_base, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_base)
            logger.info("ZIP解压完成: %s -> %s", zip_path, extract_base)
        except Exception as e:
            logger.error("ZIP解压失败: %s", e)
            return [{"success": False, "error": f"ZIP解压失败: {e}"}]

        items = sorted(os.listdir(extract_base))
        subdirs = [d for d in items if os.path.isdir(os.path.join(extract_base, d))]

        if not subdirs:
            info = extract_account_info(extract_base)
            result = self._import_single(info, extract_base)
            results.append(result)
        else:
            for subdir in subdirs:
                folder_path = os.path.join(extract_base, subdir)
                info = extract_account_info(folder_path)
                result = self._import_single(info, folder_path)
                results.append(result)

        return results

    def _import_single(self, info: dict, source_folder: str) -> dict:
        name = info["name"] or f"account_{uuid.uuid4().hex[:6]}"
        phone = info["phone"]

        existing = self.db.get_account_by_phone(phone) if phone else None
        if existing:
            logger.info("账号已存在: %s (%s)", name, phone)
            return {"success": True, "skipped": True, "name": name, "phone": phone,
                    "account_id": existing["id"], "reason": "账号已存在"}

        clean_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        safe_name = f"{clean_name}_{uuid.uuid4().hex[:6]}"

        has_session = info.get("has_session", False)
        has_tdata = info.get("has_tdata", False)

        session_path = ""
        if has_session and info.get("session_file") and os.path.isfile(info["session_file"]):
            session_dest = os.path.join(self.sessions_dir, f"{safe_name}.session")
            shutil.copy2(info["session_file"], session_dest)
            session_path = session_dest
        if has_tdata and info.get("tdata_path"):
            tdata_dest = os.path.join(self.sessions_dir, f"{safe_name}_tdata")
            if os.path.exists(tdata_dest):
                shutil.rmtree(tdata_dest)
            shutil.copytree(info["tdata_path"], tdata_dest)
        if not session_path:
            if has_tdata:
                session_path = os.path.join(self.sessions_dir, f"{safe_name}.tdata_pending")
                with open(session_path, "w") as f:
                    f.write(f"# tdata source: {info['tdata_path']}\n")
            else:
                session_path = os.path.join(self.sessions_dir, f"{safe_name}.no_session")

        metadata = {
            "source_folder": source_folder,
            "has_tdata": has_tdata,
            "has_session": has_session,
        }

        account_id = self.db.add_account(
            name=safe_name, phone=phone, session_path=session_path,
            twofa_password=info.get("twofa_password", ""),
            metadata=metadata,
        )

        logger.info("账号导入: %s (ID=%d, phone=%s, session=%s)", name, account_id, phone,
                     "有" if has_session else "tdata_only")
        return {
            "success": True, "skipped": False,
            "name": name, "phone": phone,
            "account_id": account_id,
            "has_session": has_session,
            "has_tdata": has_tdata,
        }

    def create_group(self, name: str, description: str = "") -> dict:
        existing = self.db.get_group_by_name(name)
        if existing:
            return {"success": False, "error": f"分组已存在: {name}"}
        gid = self.db.add_group(name, description)
        return {"success": True, "group_id": gid, "name": name}

    def assign_to_group(self, account_id: int, group_id: int) -> bool:
        acc = self.db.get_account(account_id)
        grp = self.db.get_group(group_id)
        if not acc: raise ValueError(f"账号不存在: {account_id}")
        if not grp: raise ValueError(f"分组不存在: {group_id}")
        self.db.assign_account_to_group(account_id, group_id)
        return True

    def batch_assign_to_group(self, account_ids: list, group_id: int) -> dict:
        success, failed = [], []
        for aid in account_ids:
            try:
                self.assign_to_group(aid, group_id)
                success.append(aid)
            except Exception as e:
                failed.append({"account_id": aid, "error": str(e)})
        return {"success": success, "failed": failed}

    def list_accounts(self, group_id: int = None, page: int = 0,
                      page_size: int = 10) -> dict:
        offset = page * page_size
        accounts = self.db.list_accounts(group_id=group_id, offset=offset, limit=page_size)
        total = self.db.count_accounts(group_id=group_id)
        return {
            "accounts": accounts, "total": total, "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }

    def list_ungrouped_accounts(self, page: int = 0, page_size: int = 10) -> dict:
        offset = page * page_size
        accounts = self.db.list_ungrouped_accounts(offset=offset, limit=page_size)
        total = self.db.count_ungrouped_accounts()
        return {
            "accounts": accounts, "total": total, "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }

    def move_ungrouped_to_group(self, group_id: int, account_ids: list = None) -> dict:
        if account_ids:
            ungrouped = [self.db.get_account(aid) for aid in account_ids]
            ungrouped = [a for a in ungrouped if a is not None]
        else:
            ungrouped = self.db.list_ungrouped_accounts(limit=10000)
        success, failed = [], []
        for acc in ungrouped:
            try:
                self.assign_to_group(acc["id"], group_id)
                success.append(acc["id"])
            except Exception as e:
                failed.append({"account_id": acc["id"], "error": str(e)})
        return {"success": success, "failed": failed, "total": len(ungrouped)}

    def renumber_accounts(self) -> dict:
        accounts = self.db.list_accounts(limit=10000)
        group_maps = {}
        for a in accounts:
            group_maps[a["id"]] = [g["id"] for g in self.db.get_account_groups(a["id"])]
        self.db.conn.execute("DELETE FROM account_group_map")
        self.db.conn.execute("DELETE FROM tasks")
        self.db.conn.execute("DELETE FROM messages")
        self.db.conn.execute("DELETE FROM accounts")
        self.db.conn.execute("DELETE FROM sqlite_sequence WHERE name='accounts'")
        self.db.conn.commit()
        old_to_new = {}
        for i, a in enumerate(accounts, 1):
            cur = self.db.conn.execute(
                """INSERT INTO accounts (name, phone, session_path, status, twofa_password, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (a["name"], a["phone"], a["session_path"], "active",
                 a.get("twofa_password", ""), a.get("metadata", "{}"))
            )
            old_to_new[a["id"]] = cur.lastrowid
        for old_id, gids in group_maps.items():
            if old_id in old_to_new:
                for gid in gids:
                    self.db.assign_account_to_group(old_to_new[old_id], gid)
        self.db.conn.commit()
        logger.info("账号重新编号完成: %d 个 -> ID 1~%d", len(accounts), len(accounts))
        return {"success": True, "count": len(accounts), "mapping": [{"old": k, "new": v} for k, v in old_to_new.items()]}

    def get_account_detail(self, account_id: int) -> Optional[dict]:
        account = self.db.get_account(account_id)
        if account:
            import json
            groups = self.db.get_account_groups(account_id)
            account["groups"] = groups
            try:
                account["metadata"] = json.loads(account.get("metadata", "{}"))
            except Exception:
                pass
        return account

    def export_to_zip(self, output_path: str, account_ids: list = None,
                      group_id: int = None) -> dict:
        import zipfile, json
        if account_ids:
            accounts = [self.db.get_account(aid) for aid in account_ids]
            accounts = [a for a in accounts if a is not None]
        elif group_id:
            accounts = self.db.list_accounts(group_id=group_id, limit=10000)
        else:
            accounts = self.db.list_accounts(limit=10000)
        if not accounts:
            return {"success": False, "error": "没有可导出的账号", "count": 0}
        count = 0
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for acc in accounts:
                name = acc["name"]
                phone = acc["phone"]
                folder = phone if phone else name
                sp = acc["session_path"]
                session_file = os.path.basename(sp) if sp else ""
                tdata_dir = self._find_tdata_for_account(acc)
                session_str = self._read_session_string(sp) if sp and os.path.isfile(sp) else ""

                json_data = {
                    "phone": phone,
                    "name": name,
                    "api_id": 2040,
                    "api_hash": "b18441a1ff607e10a989891a5462e627",
                    "first_name": name,
                    "last_name": "",
                    "session_file": folder,
                    "session_string": session_str,
                    "twofa": acc.get("twofa_password", ""),
                    "password": acc.get("twofa_password", ""),
                    "device_model": "TG Cloud Controller",
                    "system_version": "Linux",
                    "app_version": "4.0",
                    "lang_code": "en",
                }
                zf.writestr(f"{folder}/{folder}.json",
                            json.dumps(json_data, ensure_ascii=False, indent=2))
                if acc.get("twofa_password"):
                    zf.writestr(f"{folder}/2fa.txt", acc["twofa_password"])
                if sp and os.path.isfile(sp):
                    zf.write(sp, f"{folder}/{folder}.session")
                if session_str:
                    zf.writestr(f"{folder}/{folder}_密钥", session_str)
                if tdata_dir:
                    for root, dirs, files in os.walk(tdata_dir):
                        for fn in files:
                            fp = os.path.join(root, fn)
                            an = os.path.relpath(fp, tdata_dir)
                            zf.write(fp, f"{folder}/tdata/{an}")
                count += 1
        logger.info("导出完成: %d 个账号 -> %s", count, output_path)
        return {"success": True, "path": output_path, "count": count}

    def _read_session_string(self, session_path: str) -> str:
        try:
            from telethon.sessions import StringSession
            client = TelegramClient(session_path, 6, "eb06d4abfb49dc3eeb1aeb98ae0f581e")
            loop = asyncio.new_event_loop()
            session_str = loop.run_until_complete(self._get_session_str(client))
            loop.close()
            return session_str
        except Exception:
            return ""

    async def _get_session_str(self, client):
        from telethon.sessions import StringSession
        await client.connect()
        ss = StringSession.save(client.session)
        await client.disconnect()
        return ss

    def _find_tdata_for_account(self, account: dict) -> str:
        import json
        name = account["name"]
        candidates = [
            os.path.join("data", "accounts", name, "tdata"),
            os.path.join(self.sessions_dir, f"{name}_tdata"),
        ]
        try:
            meta = json.loads(account.get("metadata", "{}"))
            wd = meta.get("workdir", "")
            if wd:
                candidates.insert(0, os.path.join(wd, "tdata"))
            src = meta.get("source_folder", "")
            if src:
                candidates.append(os.path.join(src, "tdata"))
        except Exception:
            pass
        for c in candidates:
            if os.path.isdir(c) and os.listdir(c):
                return c
        return None
        p = proxy_str.strip()
        host, port = None, None
        username, password = None, None
        try:
            if p.startswith("["):
                end = p.index("]")
                host = p[1:end]
                rest = p[end + 1:].lstrip(":").split(":")
                if rest and rest[0].isdigit():
                    port = int(rest[0])
                username = rest[1] if len(rest) > 1 else None
                password = rest[2] if len(rest) > 2 else None
            else:
                parts = p.split(":")
                host = parts[0]
                if len(parts) > 1 and parts[1].isdigit():
                    port = int(parts[1])
                username = parts[2] if len(parts) > 2 else None
                password = parts[3] if len(parts) > 3 else None
        except (ValueError, IndexError):
            return None
        if host and port:
            return ("socks5", host, port, True, username, password)
        return None

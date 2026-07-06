"""tdata 文件处理 - 识别、解析、转换"""

import os
import re
import shutil
import sqlite3
from utils.logger import setup_logger

logger = setup_logger(__name__)


def detect_account_structure(folder_path: str) -> dict:
    result = {
        "has_tdata": False,
        "has_session": False,
        "has_json": False,
        "has_twofa": False,
        "tdata_path": "",
        "session_file": "",
        "json_file": "",
        "twofa_file": "",
        "account_name": os.path.basename(folder_path),
        "phone": "",
    }

    if not os.path.isdir(folder_path):
        logger.warning("账号目录不存在: %s", folder_path)
        return result

    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)

        if item == "tdata" and os.path.isdir(item_path):
            result["has_tdata"] = True
            result["tdata_path"] = item_path

        elif item.endswith(".session") and not item.endswith(".session-journal"):
            result["has_session"] = True
            result["session_file"] = item_path

        elif item.endswith(".json") and not item.startswith("_"):
            result["has_json"] = True
            result["json_file"] = item_path
            try:
                import json
                with open(item_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result["phone"] = data.get("phone", "")
                result["account_name"] = data.get("name", result["account_name"])
            except Exception:
                pass

        elif item.endswith(".txt") or item == "2fa.txt" or item == "password.txt":
            result["has_twofa"] = True
            result["twofa_file"] = item_path

    return result


def extract_account_info(folder_path: str) -> dict:
    info = detect_account_structure(folder_path)
    folder_name = os.path.basename(folder_path)

    phone = info["phone"]
    if not phone:
        phone_match = re.findall(r'\+?\d{7,15}', folder_name)
        if phone_match:
            phone = phone_match[0]

    twofa_password = ""
    if info["has_twofa"] and os.path.isfile(info["twofa_file"]):
        try:
            with open(info["twofa_file"], "r", encoding="utf-8") as f:
                content = f.read().strip()
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        twofa_password = line
                        break
        except Exception as e:
            logger.warning("读取2FA文件失败: %s", e)

    return {
        "folder_path": folder_path,
        "name": info["account_name"] or folder_name,
        "phone": phone,
        "has_tdata": info["has_tdata"],
        "has_session": info["has_session"],
        "tdata_path": info["tdata_path"],
        "session_file": info["session_file"],
        "json_file": info["json_file"],
        "twofa_file": info["twofa_file"],
        "twofa_password": twofa_password,
    }


def tdata_to_telethon_session(tdata_dir: str, dest_session: str, api_id: int, api_hash: str) -> bool:
    """将 tdata 目录转换为 Telethon .session 文件"""
    try:
        from opentele.td import TDesktop
        from opentele.tl import TelegramClient
        from opentele.api import UseCurrentSession, CreateNewSession

        if not os.path.isdir(tdata_dir):
            logger.error("tdata目录不存在: %s", tdata_dir)
            return False

        tdesk = TDesktop(tdata_dir)
        if not tdesk.isLoaded():
            logger.error("无法加载tdata: %s", tdata_dir)
            return False

        client = TelegramClient(
            session=UseCurrentSession,
            api_id=api_id,
            api_hash=api_hash,
        )

        tdesk.ToTelethon(session=dest_session, flag=UseCurrentSession)
        logger.info("tdata转换成功: %s -> %s", tdata_dir, dest_session)
        return True

    except ImportError:
        logger.warning("opentele 未安装，无法转换 tdata")
        return False
    except Exception as e:
        logger.error("tdata转换失败: %s", e)
        return False

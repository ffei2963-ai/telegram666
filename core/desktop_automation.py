"""Telegram Desktop UI 自动化 - xdotool 完整控制"""

import os
import time
import subprocess
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)
TDESKTOP_WIN_CLASS = "TelegramDesktop"


class DesktopAutomation:

    def __init__(self, display: str = ":99"):
        self.display = display

    def _env(self):
        return {**os.environ, "DISPLAY": self.display}

    def _xrun(self, cmd: list, timeout: int = 10) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, env=self._env(), capture_output=True, timeout=timeout)

    def _get_window_id(self) -> Optional[str]:
        try:
            for _ in range(10):
                r = self._xrun(["xdotool", "search", "--class", TDESKTOP_WIN_CLASS, "--onlyvisible"])
                out = r.stdout.decode().strip()
                if out:
                    return out.split("\n")[0]
                time.sleep(0.5)
        except Exception:
            pass
        return None

    def _activate(self):
        wid = self._get_window_id()
        if wid:
            self._xrun(["xdotool", "windowactivate", wid])
            time.sleep(0.2)
        return wid

    def _type(self, text: str):
        self._xrun(["xdotool", "type", "--delay", "40", "--", text])

    def _key(self, key: str):
        time.sleep(0.15)
        self._xrun(["xdotool", "key", key])

    # ==================== 导航辅助 ====================

    def back_to_main(self):
        """按多次 Escape 确保回到主界面"""
        self._activate()
        time.sleep(0.3)
        for _ in range(3):
            self._key("Escape")
            time.sleep(0.2)

    def open_settings(self):
        self._activate()
        time.sleep(0.5)
        self._key("ctrl+1")
        time.sleep(1.5)

    def search_select(self, query: str):
        """Ctrl+F 搜索并回车选择第一个结果"""
        self._activate()
        time.sleep(0.3)
        self._key("ctrl+f")
        time.sleep(0.5)
        self._type(query)
        time.sleep(1)
        self._key("Return")
        time.sleep(1.5)

    def press_escape(self, count: int = 1):
        for _ in range(count):
            self._key("Escape")
            time.sleep(0.2)

    # ==================== 发送消息 ====================

    def send_message(self, target: str, message: str) -> dict:
        try:
            self.search_select(target)
            self._type(message)
            time.sleep(0.3)
            self._key("Return")
            logger.info("消息已发送: %s -> %s", target, message[:40])
            return {"success": True, "target": target}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== 加入群组 ====================

    def join_group(self, link: str) -> dict:
        try:
            self._activate()
            time.sleep(0.3)
            self._key("ctrl+f")
            time.sleep(0.5)
            self._type(link)
            time.sleep(1.5)
            self._key("Return")
            time.sleep(2)
            self._key("Return")
            time.sleep(1)
            self._key("Escape")
            logger.info("已尝试加入群组: %s", link)
            return {"success": True, "link": link}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== 修改个人资料 ====================

    def change_name(self, first_name: str) -> dict:
        try:
            self.open_settings()
            self._key("Return")
            time.sleep(0.8)
            self._key("ctrl+a")
            time.sleep(0.1)
            self._type(first_name)
            time.sleep(0.3)
            self._key("Return")
            time.sleep(0.5)
            self._key("Escape")
            self._key("Escape")
            logger.info("名字已修改: %s", first_name)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def change_avatar(self, avatar_path: str) -> dict:
        try:
            if not os.path.isfile(avatar_path):
                return {"success": False, "error": "头像文件不存在"}
            self.open_settings()
            self._key("Return")
            time.sleep(1)
            self._key("Tab")
            time.sleep(0.3)
            self._key("Tab")
            time.sleep(0.3)
            self._key("Return")
            time.sleep(1)
            abs_path = os.path.abspath(avatar_path)
            self._type(abs_path)
            time.sleep(0.5)
            self._key("Return")
            time.sleep(2)
            self._key("Escape")
            self._key("Escape")
            self._key("Escape")
            logger.info("头像已尝试更换: %s", avatar_path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def change_2fa(self, old_password: str, new_password: str = "") -> dict:
        try:
            self.open_settings()
            for _ in range(5):
                self._key("Tab")
                time.sleep(0.2)
            self._key("Return")
            time.sleep(1.5)
            self._type(old_password)
            time.sleep(0.3)
            self._key("Return")
            time.sleep(1.5)
            if new_password:
                self._type(new_password)
                time.sleep(0.3)
                self._key("Return")
                time.sleep(0.5)
                self._type(new_password)
                time.sleep(0.3)
                self._key("Return")
                time.sleep(1)
            self._key("Escape")
            self._key("Escape")
            self._key("Escape")
            logger.info("2FA 已修改")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== 群组成员提取 ====================

    def open_group_info(self, group_name: str):
        """打开群组并进入信息页"""
        self.search_select(group_name)
        time.sleep(1)
        self._key("ctrl+i")
        time.sleep(1)

    def scroll_members(self, count: int = 100):
        """在群信息页面滚动成员列表"""
        for _ in range(count):
            self._key("Down")
            time.sleep(0.02)

    # ==================== 一键任务 ====================

    def quick_setup(self, link: str, first_name: str) -> dict:
        """一键: 进群 + 改名"""
        results = {}
        r1 = self.join_group(link)
        results["join_group"] = r1
        time.sleep(2)
        r2 = self.change_name(first_name)
        results["change_name"] = r2
        return results

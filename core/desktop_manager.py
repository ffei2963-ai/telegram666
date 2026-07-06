"""Telegram Desktop 进程管理器

负责生命周期管理：启动/停止/tdata切换/截图
每个账号使用独立的 -workdir，互不干扰。
"""

import os
import subprocess
import time
import signal
import glob
import shutil
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

TDESKTOP_BIN = "/usr/bin/telegram-desktop"
DEFAULT_DISPLAY = ":99"
SCREEN_GEOMETRY = "1024x768x24"
XVFB_BIN = "/usr/bin/Xvfb"


class DesktopManager:

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.accounts_dir = os.path.join(data_dir, "accounts")
        os.makedirs(self.accounts_dir, exist_ok=True)
        self._xvfb_proc: Optional[subprocess.Popen] = None
        self._tdesk_proc: Optional[subprocess.Popen] = None
        self._current_account: Optional[str] = None
        self._display = DEFAULT_DISPLAY
        self._start_xvfb()

    def _start_xvfb(self):
        lock_file = f"/tmp/.X99-lock"
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
        try:
            self._xvfb_proc = subprocess.Popen(
                [XVFB_BIN, self._display, "-screen", "0", SCREEN_GEOMETRY, "+extension", "RANDR"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            logger.info("Xvfb 已启动 (display=%s)", self._display)
        except Exception as e:
            logger.error("Xvfb 启动失败: %s", e)

    def _stop_xvfb(self):
        if self._xvfb_proc:
            self._xvfb_proc.terminate()
            try:
                self._xvfb_proc.wait(timeout=5)
            except Exception:
                self._xvfb_proc.kill()
            self._xvfb_proc = None

    @property
    def env(self) -> dict:
        return {**os.environ, "DISPLAY": self._display}

    def ensure_xvfb(self):
        if self._xvfb_proc is None or self._xvfb_proc.poll() is not None:
            self._start_xvfb()

    # ==================== 账号工作目录管理 ====================

    def get_account_workdir(self, account_name: str) -> str:
        return os.path.join(self.accounts_dir, account_name)

    def setup_account_workdir(self, account_name: str, tdata_source: str) -> bool:
        """为账号创建独立 workdir，将 tdata 放入正确位置"""
        workdir = self.get_account_workdir(account_name)
        tdata_dest = os.path.join(workdir, "tdata")
        os.makedirs(workdir, exist_ok=True)

        if os.path.isdir(tdata_dest):
            if os.listdir(tdata_dest):
                return True

        if os.path.isdir(tdata_source):
            if os.path.exists(tdata_dest):
                shutil.rmtree(tdata_dest)
            shutil.copytree(tdata_source, tdata_dest)
            logger.info("账号 %s 工作目录已创建: %s", account_name, workdir)
            return True

        logger.warning("tdata 源目录不存在: %s", tdata_source)
        return False

    def account_has_tdata(self, account_name: str) -> bool:
        workdir = self.get_account_workdir(account_name)
        tdata_dir = os.path.join(workdir, "tdata")
        return os.path.isdir(tdata_dir) and os.listdir(tdata_dir)

    # ==================== Desktop 生命周期 ====================

    def start_desktop(self, account_name: str, wait_ready: bool = True) -> bool:
        """为指定账号启动 Telegram Desktop"""
        self.ensure_xvfb()
        self.stop_desktop()

        workdir = self.get_account_workdir(account_name)
        if not self.account_has_tdata(account_name):
            logger.error("账号 %s 无 tdata，无法启动 Desktop", account_name)
            return False

        os.makedirs(workdir, exist_ok=True)

        try:
            cmd = [TDESKTOP_BIN, "-workdir", workdir, "-autostart"]
            self._tdesk_proc = subprocess.Popen(
                cmd,
                env=self.env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._current_account = account_name
            logger.info("Telegram Desktop 已启动 (账号=%s, workdir=%s)", account_name, workdir)

            if wait_ready:
                for _ in range(10):
                    time.sleep(0.5)
                    if self.is_running():
                        break
                time.sleep(1)
            return True
        except Exception as e:
            logger.error("Desktop 启动失败: %s", e)
            return False

    def stop_desktop(self):
        try:
            subprocess.run(["pkill", "-f", "telegram-desktop"], timeout=5,
                          capture_output=True)
        except Exception:
            pass
        if self._tdesk_proc:
            try:
                self._tdesk_proc.wait(timeout=3)
            except Exception:
                self._tdesk_proc.kill()
        self._tdesk_proc = None
        if self._current_account:
            logger.info("Telegram Desktop 已停止 (账号=%s)", self._current_account)
        self._current_account = None

    def is_running(self) -> bool:
        try:
            r = subprocess.run(["pgrep", "-f", "telegram-desktop"],
                             capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return self._tdesk_proc is not None and self._tdesk_proc.poll() is None

    def switch_to_account(self, account_name: str) -> bool:
        """切换到指定账号（停止当前 → 启动目标）"""
        if self._current_account == account_name and self.is_running():
            return True
        self.stop_desktop()
        return self.start_desktop(account_name)

    def get_current_account(self) -> Optional[str]:
        return self._current_account

    # ==================== 截图功能 ====================

    def screenshot(self, filename: str = None) -> Optional[str]:
        """对当前 Desktop 截图"""
        self.ensure_xvfb()
        if not filename:
            screenshot_dir = os.path.join(self.data_dir, "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            filename = os.path.join(screenshot_dir, f"screen_{int(time.time())}.png")

        try:
            subprocess.run(
                ["import", "-window", "root", "-display", self._display, filename],
                timeout=5,
                capture_output=True,
            )
            if os.path.isfile(filename):
                return filename
        except Exception as e:
            logger.warning("截图失败: %s", e)
        return None

    # ==================== 清理 ====================

    def shutdown(self):
        self.stop_desktop()
        self._stop_xvfb()
        logger.info("Desktop Manager 已关闭")


_desktop_instance: Optional[DesktopManager] = None


def get_desktop(data_dir: str = "data") -> DesktopManager:
    global _desktop_instance
    if _desktop_instance is None:
        _desktop_instance = DesktopManager(data_dir)
    return _desktop_instance

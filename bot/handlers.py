"""TG Cloud Controller - Bot 处理器 (Telethon引擎 完整版)

所有操作基于 Telethon MTProto API，直接操作 Telegram 服务器。
Desktop 作为备选（实验性，需要 Xvfb+X11 环境）。
"""

import os, json, time, shutil, asyncio
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db.database import Database
from core.account_manager import AccountManager
from core.ai_service import AIService
from core.telethon_engine import TelethonEngine, get_engine, human_delay
from core.message_monitor import MessageMonitor
from core.group_scraper import GroupScraper
from core.translator import Translator
from bot.keyboards import (
    main_menu, accounts_menu, groups_menu, dm_menu,
    batch_menu, status_menu, settings_menu,
    pagination_menu, BACK_BTN,
)
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger(__name__)

BATCH_TYPES = {
    "join_group": "批量进群",
    "change_name": "批量修改名字",
    "change_2fa": "批量修改2FA",
    "change_avatar": "批量修改头像",
    "mass_dm": "群发私信",
}


class BotHandlers:

    def __init__(self, db: Database, account_mgr: AccountManager,
                 ai: AIService, engine: TelethonEngine = None,
                 monitor: MessageMonitor = None,
                 scraper: GroupScraper = None,
                 translator: Translator = None):
        self.db = db
        self.account_mgr = account_mgr
        self.ai = ai
        self.engine = engine or get_engine()
        self.monitor = monitor
        self.scraper = scraper
        self.translator = translator
        self.user_states = {}

    def _admin(self, uid):
        return not config.admin_user_ids or uid in config.admin_user_ids

    # ==================== /start ====================
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._admin(update.effective_user.id):
            await update.message.reply_text("🔒 无权访问")
            return
        await update.message.reply_text(
            "🤖 *TG Cloud Controller v4.0*\n\n"
            "基于 Telethon MTProto 的云控平台\n"
            "📋 账号管理 | 📨 群发私信 | 👥 群组管理\n"
            "⚙️ 批量操作 | 📊 状态 | 🔧 设置\n\n"
            "所有操作直接走 Telegram API，无需 Desktop。",
            parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu()
        )

    # ==================== 按钮路由 ====================
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data, uid = q.data, q.from_user.id
        if not self._admin(uid): return

        menu = {
            "menu_main": (main_menu, "📋 主菜单"),
            "menu_accounts": (accounts_menu, "📋 账号管理"),
            "menu_groups": (groups_menu, "👥 群组管理"),
            "menu_dm": (dm_menu, "📨 群发私信"),
            "menu_batch": (batch_menu, "⚙️ 批量操作"),
            "menu_status": (status_menu, "📊 运行状态"),
            "menu_settings": (settings_menu, "🔧 系统设置"),
        }
        if data in menu:
            f, t = menu[data]
            await q.edit_message_text(t, reply_markup=f())
            return
        if data == "cancel":
            self.user_states.pop(uid, None)
            await q.edit_message_text("❌ 已取消", reply_markup=main_menu())
            return
        if data == "noop": return
        await self._actions(data, q, context)

    # ==================== 操作分发 ====================
    async def _actions(self, data: str, q, ctx):
        uid = q.from_user.id
        d = data

        # --- 导入账号 ---
        if d == "act_import_accounts":
            self.user_states[uid] = {"state": "awaiting_zip"}
            await q.edit_message_text(
                "📤 上传账号 ZIP (含 .session + tdata)",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]]),
            )
            return

        # --- 账号列表 ---
        if d == "act_list_accounts":
            await self._show_accounts(q, 0); return
        if d.startswith("listacc_page_"):
            await self._show_accounts(q, int(d.replace("listacc_page_", ""))); return

        # --- 验证账号 ---
        if d == "act_verify_accounts":
            await q.edit_message_text(f"🔄 并行验证 {self.db.count_accounts()} 个账号...")
            accounts = self.db.list_accounts(limit=200)

            async def verify_one(acc):
                if not os.path.isfile(acc["session_path"]):
                    return {"id": acc["id"], "name": acc["name"], "status": "no_session"}
                r = await self.engine.get_me(acc["id"])
                return {**r, "id": acc["id"], "name": acc["name"]}

            sem = asyncio.Semaphore(self.engine.max_concurrent)
            async def limited(acc):
                async with sem:
                    return await verify_one(acc)

            results = await asyncio.gather(*[limited(a) for a in accounts])

            active = [r for r in results if r.get("success")]
            offline = [r for r in results if not r.get("success")]
            lines = [f"在线: {len(active)} / {len(results)}"]
            if active:
                lines.append("")
                for a in active[:20]:
                    lines.append(f"✅ [{a['id']}] {a['first_name']}")
            if offline and len(offline) <= 10:
                lines.append(f"\n离线: {len(offline)}")
                for a in offline[:10]:
                    lines.append(f"❌ [{a['id']}] {a['name']}")
            elif offline:
                lines.append(f"\n❌ 离线: {len(offline)} 个 (session过期)")
            await q.edit_message_text("\n".join(lines), reply_markup=accounts_menu())
            return

        # --- 删除账号 ---
        if d == "act_delete_account":
            await self._show_delete_list(q, 0); return
        if d.startswith("delacc_page_"):
            await self._show_delete_list(q, int(d.replace("delacc_page_", ""))); return
        if d.startswith("delacc_toggle_"):
            aid = int(d.replace("delacc_toggle_", ""))
            st = self.user_states.get(uid, {"sel": [], "pg": 0})
            sel = st.get("sel", [])
            if aid in sel: sel.remove(aid)
            else: sel.append(aid)
            st["sel"] = sel
            self.user_states[uid] = st
            await self._show_delete_list(q, st.get("pg", 0)); return
        if d == "delacc_confirm":
            st = self.user_states.pop(uid, {"sel": []})
            sel = st.get("sel", [])
            if not sel:
                await q.edit_message_text("❌ 未选择", reply_markup=accounts_menu()); return
            await q.edit_message_text(
                f"⚠️ 确认删除 {len(sel)} 个账号?", parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ 确认", callback_data="delacc_exec")],
                    [InlineKeyboardButton("🔙 取消", callback_data="cancel")],
                ]),
            )
            self.user_states[uid] = {"pending_del": sel}; return
        if d == "delacc_exec":
            st = self.user_states.pop(uid, {"pending_del": []})
            sel = st.get("pending_del", [])
            deleted = 0
            for aid in sel:
                try:
                    acc = self.db.get_account(aid)
                    if acc:
                        await self.engine.disconnect_client(aid)
                        sp = acc.get("session_path", "")
                        if sp and os.path.isfile(sp):
                            os.remove(sp)
                    self.db.delete_account(aid)
                    deleted += 1
                except Exception as e:
                    logger.error("删除失败: %s", e)
            await q.edit_message_text(f"🗑 已删除 {deleted} 个", reply_markup=accounts_menu()); return

        # --- 导出账号 ---
        if d == "act_export_accounts":
            if self.db.count_accounts() == 0:
                await q.edit_message_text("📝 暂无账号可导出", reply_markup=accounts_menu()); return
            await q.edit_message_text("📦 选择导出方式:", parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📁 按分组导出", callback_data="export_by_group"),
                     InlineKeyboardButton("☑️ 勾选账号导出", callback_data="export_by_ids")],
                    [BACK_BTN]])); return
        if d == "export_by_group":
            groups = self.db.list_groups()
            if not groups:
                await q.edit_message_text("📁 暂无分组", reply_markup=accounts_menu()); return
            kb = [[InlineKeyboardButton(f"📁 {g['name']} ({g['account_count']})", callback_data=f"export_grp_{g['id']}")] for g in groups]
            kb.append([BACK_BTN])
            await q.edit_message_text("选择要导出的分组:", reply_markup=InlineKeyboardMarkup(kb)); return
        if d.startswith("export_grp_"):
            gid = int(d.replace("export_grp_", ""))
            g = self.db.get_group(gid)
            await q.edit_message_text(f"⏳ 正在导出「{g['name']}」...")
            await self._do_export(q, uid, group_id=gid); return
        if d == "export_by_ids":
            self.user_states[uid] = {"sel": [], "pg": 0, "mode": "export"}
            await self._show_export_selection(q, uid, 0); return
        if d.startswith("export_tog_"):
            aid = int(d.replace("export_tog_", ""))
            st = self.user_states.get(uid, {"sel": [], "pg": 0})
            sel = st.get("sel", [])
            if aid in sel: sel.remove(aid)
            else: sel.append(aid)
            st["sel"] = sel; self.user_states[uid] = st
            await self._show_export_selection(q, uid, st.get("pg", 0)); return
        if d.startswith("export_pg_"):
            page = int(d.replace("export_pg_", ""))
            await self._show_export_selection(q, uid, page); return
        if d == "export_exec":
            st = self.user_states.pop(uid, {"sel": []})
            sel = st.get("sel", [])
            if not sel:
                await q.edit_message_text("❌ 未选择账号", reply_markup=accounts_menu()); return
            await q.edit_message_text(f"⏳ 正在导出 {len(sel)} 个账号...")
            await self._do_export(q, uid, account_ids=sel); return

        # --- 重新编号 ---
        if d == "act_renumber":
            count = self.db.count_accounts()
            if count == 0:
                await q.edit_message_text("📝 暂无账号", reply_markup=accounts_menu()); return
            await q.edit_message_text("⏳ 正在重新编号...")
            result = self.account_mgr.renumber_accounts()
            await q.edit_message_text(
                f"✅ 已重新编号: {result['count']} 个账号 → ID 1~{result['count']}",
                reply_markup=accounts_menu()); return

        # --- 分组 ---
        if d == "act_manage_groups":
            await self._show_groups(q); return
        if d == "act_create_group":
            self.user_states[uid] = {"state": "awaiting_group_name"}
            await q.edit_message_text("📝 输入新分组名称:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return
        if d == "act_delete_group":
            groups = self.db.list_groups()
            if not groups: await q.edit_message_text("暂无分组", reply_markup=groups_menu()); return
            kb = [[InlineKeyboardButton(f"🗑 {g['name']}", callback_data=f"delgroup_{g['id']}")] for g in groups]
            kb.append([BACK_BTN])
            await q.edit_message_text("选择要删除的分组:", reply_markup=InlineKeyboardMarkup(kb)); return
        if d.startswith("delgroup_"):
            gid = int(d.replace("delgroup_", ""))
            self.db.delete_group(gid)
            await q.edit_message_text("✅ 已删除", reply_markup=groups_menu()); return

        # --- 分配分组 ---
        if d == "act_assign_group":
            self.user_states[uid] = {"sel": [], "pg": 0, "step": "select"}
            await self._show_assign(q, 0); return
        if d.startswith("asgn_pg_"):
            await self._show_assign(q, int(d.replace("asgn_pg_", ""))); return
        if d.startswith("asgn_tog_"):
            aid = int(d.replace("asgn_tog_", ""))
            st = self.user_states.get(uid, {"sel": [], "pg": 0})
            sel = st.get("sel", [])
            if aid in sel: sel.remove(aid)
            else: sel.append(aid)
            st["sel"] = sel; self.user_states[uid] = st
            await self._show_assign(q, st.get("pg", 0)); return
        if d == "asgn_confirm":
            st = self.user_states.get(uid, {"sel": []})
            sel = st.get("sel", [])
            if not sel: await q.edit_message_text("❌ 未选择", reply_markup=groups_menu()); return
            st["step"] = "pick_group"; self.user_states[uid] = st
            groups = self.db.list_groups()
            if not groups: await q.edit_message_text("暂无分组", reply_markup=groups_menu()); return
            kb = [[InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"asgn_grp_{g['id']}")] for g in groups]
            kb.append([BACK_BTN])
            await q.edit_message_text(f"已选 {len(sel)} 个\n选择目标分组:", reply_markup=InlineKeyboardMarkup(kb)); return
        if d.startswith("asgn_grp_"):
            gid = int(d.replace("asgn_grp_", ""))
            st = self.user_states.pop(uid, {"sel": []})
            sel = st.get("sel", [])
            r = self.account_mgr.batch_assign_to_group(sel, gid)
            g = self.db.get_group(gid)
            await q.edit_message_text(f"✅ {len(r['success'])} 个已分配到「{g['name']}」", reply_markup=groups_menu()); return

        # --- 检测未分组账号 ---
        if d == "act_ungrouped_list":
            await self._show_ungrouped(q, 0); return
        if d.startswith("ungrouped_page_"):
            await self._show_ungrouped(q, int(d.replace("ungrouped_page_", ""))); return

        # --- 转移未分组账号 ---
        if d == "act_ungrouped_move":
            ungrouped_count = self.db.count_ungrouped_accounts()
            if ungrouped_count == 0:
                await q.edit_message_text("✅ 所有账号已分组", reply_markup=groups_menu()); return
            groups = self.db.list_groups()
            if not groups:
                await q.edit_message_text("❌ 请先创建分组", reply_markup=groups_menu()); return
            self.user_states[uid] = {"sel": [], "pg": 0}
            await self._show_ungrouped_move(q, uid, 0); return
        if d.startswith("ungrouped_move_tog_"):
            aid = int(d.replace("ungrouped_move_tog_", ""))
            st = self.user_states.get(uid, {"sel": [], "pg": 0})
            sel = st.get("sel", [])
            if aid in sel: sel.remove(aid)
            else: sel.append(aid)
            st["sel"] = sel; self.user_states[uid] = st
            await self._show_ungrouped_move(q, uid, st.get("pg", 0)); return
        if d.startswith("ungrouped_move_pg_"):
            page = int(d.replace("ungrouped_move_pg_", ""))
            await self._show_ungrouped_move(q, uid, page); return
        if d == "ungrouped_move_next":
            st = self.user_states.get(uid, {"sel": [], "pg": 0})
            sel = st.get("sel", [])
            if not sel:
                await q.edit_message_text("❌ 未选择账号", reply_markup=groups_menu()); return
            groups = self.db.list_groups()
            kb = [[InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"ungrouped_move_grp_{g['id']}")] for g in groups]
            kb.append([BACK_BTN])
            await q.edit_message_text(f"已选 {len(sel)} 个\\n选择目标分组:", reply_markup=InlineKeyboardMarkup(kb)); return
        if d.startswith("ungrouped_move_grp_"):
            gid = int(d.replace("ungrouped_move_grp_", ""))
            st = self.user_states.pop(uid, {"sel": []})
            sel = st.get("sel", [])
            r = self.account_mgr.move_ungrouped_to_group(gid, account_ids=sel if sel else None)
            g = self.db.get_group(gid)
            await q.edit_message_text(
                f"✅ {len(r['success'])} 个已转移到「{g['name']}」\n"
                f"失败: {len(r['failed'])}",
                reply_markup=groups_menu()); return

        # --- 取消分组 (将已分组账号移出) ---
        if d == "act_ungroup_from_group":
            groups = self.db.list_groups()
            if not groups:
                await q.edit_message_text("📁 暂无分组", reply_markup=groups_menu()); return
            kb = [[InlineKeyboardButton(f"📁 {g['name']} ({g['account_count']})", callback_data=f"ungroup_selgrp_{g['id']}")] for g in groups]
            kb.append([BACK_BTN])
            await q.edit_message_text("选择要移出账号的分组:", reply_markup=InlineKeyboardMarkup(kb)); return
        if d.startswith("ungroup_selgrp_"):
            gid = int(d.replace("ungroup_selgrp_", ""))
            self.user_states[uid] = {"sel": [], "pg": 0, "gid": gid}
            await self._show_ungroup_from(q, uid, gid, 0); return
        if d.startswith("ungroup_tog_"):
            aid = int(d.replace("ungroup_tog_", ""))
            st = self.user_states.get(uid, {"sel": [], "pg": 0, "gid": 0})
            sel = st.get("sel", [])
            if aid in sel: sel.remove(aid)
            else: sel.append(aid)
            st["sel"] = sel; self.user_states[uid] = st
            await self._show_ungroup_from(q, uid, st.get("gid", 0), st.get("pg", 0)); return
        if d.startswith("ungroup_pg_"):
            parts = d.replace("ungroup_pg_", "").split("_")
            st = self.user_states.get(uid, {"sel": [], "pg": 0, "gid": 0})
            page = int(parts[0]); gid = int(parts[1]) if len(parts) > 1 else st.get("gid", 0)
            st["pg"] = page; self.user_states[uid] = st
            await self._show_ungroup_from(q, uid, gid, page); return
        if d.startswith("ungroup_exec_"):
            gid = int(d.replace("ungroup_exec_", ""))
            st = self.user_states.pop(uid, {"sel": [], "gid": 0})
            sel = st.get("sel", [])
            if not sel:
                await q.edit_message_text("❌ 未选择", reply_markup=groups_menu()); return
            g = self.db.get_group(gid)
            for aid in sel:
                self.db.remove_account_from_group(aid, gid)
            await q.edit_message_text(f"✅ {len(sel)} 个已从「{g['name']}」移出", reply_markup=groups_menu()); return

        # --- 批量操作-选择目标 ---
        if d in ("act_batch_by_group", "act_batch_by_ids"):
            st = self.user_states.get(uid, {})
            if st.get("state") != "awaiting_batch":
                await q.edit_message_text("请先选择操作类型", reply_markup=batch_menu()); return
            if d == "act_batch_by_group":
                groups = self.db.list_groups()
                if not groups: await q.edit_message_text("暂无分组", reply_markup=batch_menu()); return
                kb = [[InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"batch_grp_{g['id']}")] for g in groups]
                kb.append([BACK_BTN])
                await q.edit_message_text("选择目标分组:", reply_markup=InlineKeyboardMarkup(kb)); return
            else:
                st["step"] = "enter_ids"; self.user_states[uid] = st
                await q.edit_message_text("输入ID列表 (逗号分隔):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return

        if d.startswith("batch_grp_"):
            gid = int(d.replace("batch_grp_", ""))
            st = self.user_states.get(uid, {})
            st["tgt_ids"] = [gid]; st["tgt_type"] = "groups"; st["step"] = "enter_params"
            self.user_states[uid] = st
            task_type = st.get("task_type", "")
            hints = {
                "join_group": "输入群组链接:",
                "change_name": "输入新名字:",
                "change_2fa": "输入: 旧密码 新密码",
                "mass_dm": "输入: @目标 消息内容 (用 | 分隔)",
            }
            await q.edit_message_text(hints.get(task_type, "输入参数:"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return

        # --- 批量进群 ---
        if d == "act_batch_join":
            self.user_states[uid] = {"state": "awaiting_batch", "task_type": "join_group"}
            await self._show_target_choice(q); return

        # --- 批量改名 ---
        if d == "act_change_name":
            self.user_states[uid] = {"state": "awaiting_batch", "task_type": "change_name"}
            await self._show_target_choice(q); return

        # --- 修改2FA ---
        if d == "act_change_2fa":
            self.user_states[uid] = {"state": "awaiting_batch", "task_type": "change_2fa"}
            await self._show_target_choice(q); return

        # --- 修改头像 ---
        if d == "act_change_avatar":
            self.user_states[uid] = {"state": "awaiting_avatar"}
            await q.edit_message_text("🖼 请发送头像图片:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return

        # --- 群发私信 ---
        if d == "act_new_dm":
            self.user_states[uid] = {"state": "awaiting_batch", "task_type": "mass_dm"}
            await self._show_target_choice(q); return

        # --- 查看任务 ---
        if d in ("act_view_tasks", "act_dm_status"):
            tasks = self.db.list_tasks(limit=20)
            if not tasks:
                await q.edit_message_text("📊 暂无任务", reply_markup=batch_menu()); return
            e = {"completed": "✅", "partial": "⚠️", "pending": "⏳", "running": "🔄", "failed": "❌"}
            lines = [f"{e.get(t['status'],'?')} #{t['id']} {BATCH_TYPES.get(t['task_type'],t['task_type'])} | {t['progress']}" for t in tasks]
            await q.edit_message_text("📊 *任务列表*\n\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=batch_menu()); return

        # --- 一键任务 ---
        if d == "act_quick_task":
            self.user_states[uid] = {"state": "awaiting_batch", "task_type": "quick_setup"}
            await self._show_target_choice(q); return

        # --- 回复消息 ---
        if d == "act_view_replies":
            msgs = self.db.get_unreplied_messages()
            if not msgs: await q.edit_message_text("💬 暂无待回复", reply_markup=dm_menu()); return
            lines = [f"#{m['id']} @{m['sender_username']}: {m['content_raw'][:60]}" for m in msgs[:15]]
            await q.edit_message_text("💬 *待回复*\n\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=dm_menu()); return

        # --- 搜索 ---
        if d == "menu_search":
            self.user_states[uid] = {"state": "awaiting_search"}
            await q.edit_message_text("🔍 输入搜索关键词:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return

        # --- 提取成员 ---
        if d == "act_scrape_members":
            self.user_states[uid] = {"state": "awaiting_scrape"}
            await q.edit_message_text("📊 输入群组 username:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return

        # --- 状态 ---
        if d == "act_refresh_status":
            total = self.db.count_accounts()
            groups = self.db.list_groups()
            tasks = self.db.list_tasks(status="pending")
            text = f"📊 *状态*\n• 账号: {total} | 分组: {len(groups)}\n• 待处理: {len(tasks)}\n• AI: {'✅' if self.ai.is_available() else '❌'}"
            await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=status_menu()); return

        if d == "act_system_info":
            import psutil
            m = psutil.virtual_memory()
            d2 = psutil.disk_usage("/")
            s = psutil.swap_memory()
            text = f"🖥 RAM:{m.used>>20}/{m.total>>20}MB | Disk:{d2.used>>30}/{d2.total>>30}GB | Swap:{s.percent}%"
            await q.edit_message_text(text, reply_markup=status_menu()); return

        # --- 设置 ---
        if d == "act_set_api_key":
            self.user_states[uid] = {"state": "awaiting_api_key"}
            await q.edit_message_text("🔑 输入 DeepSeek API Key:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return
        if d == "act_set_concurrency":
            self.user_states[uid] = {"state": "awaiting_concurrency"}
            cur = self.db.get_setting("max_concurrent", "5")
            await q.edit_message_text(f"⚡ 当前并发:{cur} 输入1-20:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return
        if d == "act_set_delay":
            self.user_states[uid] = {"state": "awaiting_delay"}
            cur_min = self.db.get_setting("random_delay_min", "0.8")
            cur_max = self.db.get_setting("random_delay_max", "3.5")
            await q.edit_message_text(f"⏱ 当前随机延时:{cur_min}~{cur_max}秒\n输入范围 (格式: min max):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return
        if d == "act_set_proxy":
            self.user_states[uid] = {"state": "awaiting_api_creds"}
            await q.edit_message_text("🌐 输入: `API_ID API_HASH`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return

    # ==================== 文件处理 ====================
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        st = self.user_states.get(uid, {})

        if st.get("state") == "awaiting_zip":
            doc = update.message.document
            if not doc.file_name.endswith(".zip"):
                await update.message.reply_text("❌ 请上传 .zip", reply_markup=main_menu())
                self.user_states.pop(uid, None); return
            await update.message.reply_text("⏳ 处理中...")
            fobj = BytesIO()
            tf = await context.bot.get_file(doc.file_id)
            await tf.download_to_memory(fobj); fobj.seek(0)
            tmp = os.path.join(config.uploads_dir, f"upload_{uid}_{doc.file_name}")
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            with open(tmp, "wb") as f: f.write(fobj.read())
            results = self.account_mgr.import_from_zip(tmp)
            os.remove(tmp); self.user_states.pop(uid, None)
            imp = [r for r in results if r.get("success") and not r.get("skipped")]
            skp = [r for r in results if r.get("skipped")]
            fl = [r for r in results if not r.get("success")]
            text = f"📥 成功:{len(imp)} | 跳过:{len(skp)} | 失败:{len(fl)}\n"
            if imp:
                text += "\n".join(f"  • [{a['account_id']}] {a['name']}" for a in imp[:15])
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu()); return

        if st.get("state") == "awaiting_avatar":
            doc = update.message.document
            av_path = os.path.join(config.uploads_dir, f"avatar_{uid}_{doc.file_name}")
            tf = await context.bot.get_file(doc.file_id)
            await tf.download_to_drive(av_path)
            st["avatar_path"] = av_path; self.user_states[uid] = st
            await update.message.reply_text(f"✅ 头像已接收。请回复目标账号ID (逗号分隔):", reply_markup=accounts_menu()); return

    # ==================== 文本处理 ====================
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        st = self.user_states.get(uid, {})
        text = update.message.text.strip()

        if not st:
            if text.startswith("/reply"):
                await self._handle_reply_command(update, text); return
            await update.message.reply_text("使用 /start 开始", reply_markup=main_menu()); return

        state = st.get("state", "")

        # --- 创建分组 ---
        if state == "awaiting_group_name":
            r = self.account_mgr.create_group(text)
            self.user_states.pop(uid, None)
            await update.message.reply_text(
                f"✅ `{text}` 已创建" if r["success"] else f"❌ {r['error']}",
                parse_mode=ParseMode.MARKDOWN, reply_markup=groups_menu()); return

        # --- API Key ---
        if state == "awaiting_api_key":
            self.db.set_setting("deepseek_api_key", text)
            self.user_states.pop(uid, None)
            await update.message.reply_text("✅ 已保存", reply_markup=settings_menu()); return

        # --- 并发 ---
        if state == "awaiting_concurrency":
            try:
                n = int(text)
                if 1 <= n <= 20:
                    self.db.set_setting("max_concurrent", str(n))
                    self.user_states.pop(uid, None)
                    await update.message.reply_text(f"✅ 并发={n}", reply_markup=settings_menu()); return
            except ValueError: pass
            await update.message.reply_text("❌ 1-20 的数字"); return

        # --- 随机延时范围 ---
        if state == "awaiting_delay":
            parts = text.split()
            try:
                if len(parts) >= 2:
                    mn = float(parts[0])
                    mx = float(parts[1])
                else:
                    mn = 0.5
                    mx = float(parts[0])
                if 0 <= mn <= mx <= 60:
                    self.db.set_setting("random_delay_min", str(mn))
                    self.db.set_setting("random_delay_max", str(mx))
                    self.user_states.pop(uid, None)
                    await update.message.reply_text(f"✅ 随机延时 {mn}~{mx}秒", reply_markup=settings_menu()); return
            except ValueError: pass
            await update.message.reply_text("❌ 格式: min max (如 1 5)"); return

        # --- API 凭据 ---
        if state == "awaiting_api_creds":
            parts = text.split()
            if len(parts) >= 2:
                try:
                    self.db.set_setting("tg_api_id", str(int(parts[0])))
                    self.db.set_setting("tg_api_hash", parts[1])
                    self.user_states.pop(uid, None)
                    await update.message.reply_text("✅ 已保存", reply_markup=settings_menu()); return
                except ValueError: pass
            await update.message.reply_text("❌ 格式: `123456 abcdef`"); return

        # --- 头像 ---
        if state == "awaiting_avatar" and "avatar_path" in st:
            try:
                ids = [int(x.strip()) for x in text.replace("，", ",").split(",") if x.strip().isdigit()]
            except:
                await update.message.reply_text("❌ ID格式错误"); return
            if not ids:
                ids = [a["id"] for a in self.db.list_accounts(limit=100)]
            av_path = st["avatar_path"]
            self.user_states.pop(uid, None)
            await update.message.reply_text(f"⏳ 正在为 {len(ids)} 个账号换头像...")
            results = []
            for aid in ids:
                if not os.path.isfile(av_path): continue
                r = await self.engine.change_avatar(aid, av_path)
                results.append(r)
            ok = sum(1 for r in results if r.get("success"))
            await update.message.reply_text(f"✅ 头像修改: {ok}/{len(ids)}", reply_markup=accounts_menu()); return

        # --- 搜索 ---
        if state == "awaiting_search":
            accounts = self.db.list_accounts(limit=1)
            if accounts:
                r = await self.engine.get_me(accounts[0]["id"])
                await update.message.reply_text(
                    f"🔍 搜索: {text}\n当前账号: {r.get('first_name','?')}\n可在 Telegram Desktop 中 Ctrl+F 搜索。",
                    reply_markup=groups_menu())
            self.user_states.pop(uid, None); return

        # --- 提取成员 ---
        if state == "awaiting_scrape":
            accounts = self.db.list_accounts(limit=1)
            if accounts:
                r = await self.engine.join_group(accounts[0]["id"], text)
                await update.message.reply_text(
                    f"📊 加入群 {text}: {'✅' if r.get('success') else '❌ ' + r.get('error', '')}",
                    reply_markup=groups_menu())
            self.user_states.pop(uid, None); return

        # --- 批量操作参数 ---
        if state == "awaiting_batch":
            if st.get("step") == "enter_ids":
                try:
                    ids = [int(x.strip()) for x in text.replace("，", ",").split(",") if x.strip().isdigit()]
                    if not ids: await update.message.reply_text("❌ 未找到有效ID"); return
                    st["tgt_ids"] = ids; st["step"] = "enter_params"; self.user_states[uid] = st
                    task_type = st.get("task_type", "")
                    hints = {"join_group": "群组链接:", "change_name": "新名字:",
                             "change_2fa": "旧密码 新密码", "mass_dm": "@目标 | 消息内容",
                             "quick_setup": "群组链接 | 新名字"}
                    await update.message.reply_text(hints.get(task_type, "参数:"),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 取消", callback_data="cancel")]])); return
                except:
                    await update.message.reply_text("❌ ID格式错误"); return

            if st.get("step") == "enter_params":
                task_type = st.get("task_type", "")
                tgt_type = st.get("tgt_type", "accounts")
                tgt_ids = st.get("tgt_ids", [])
                params = {}

                if task_type == "join_group":
                    params["link"] = text
                elif task_type == "change_name":
                    params["first_name"] = text
                elif task_type == "change_2fa":
                    parts = text.split()
                    params["old_password"] = parts[0] if parts else ""
                    params["new_password"] = parts[1] if len(parts) > 1 else ""
                elif task_type == "mass_dm":
                    if "|" in text:
                        p = text.split("|", 1)
                        params["target"] = p[0].strip()
                        params["message"] = p[1].strip()
                    else:
                        params["message"] = text
                elif task_type == "quick_setup":
                    if "|" in text:
                        p = text.split("|", 1)
                        params["link"] = p[0].strip()
                        params["first_name"] = p[1].strip() if len(p) > 1 else ""
                    else:
                        params["link"] = text

                self.user_states.pop(uid, None)

                if tgt_type == "groups":
                    actual_ids = set()
                    for gid in tgt_ids:
                        for a in self.db.list_accounts(group_id=gid, limit=1000):
                            actual_ids.add(a["id"])
                    tgt_ids = list(actual_ids)

                await update.message.reply_text(f"⏳ 正在执行: {BATCH_TYPES.get(task_type, task_type)} ({len(tgt_ids)} 个账号)...")
                results = await self._execute_batch(task_type, tgt_ids, params)

                ok = sum(1 for r in results if r.get("success"))
                errors = [r for r in results if not r.get("success")]
                msg = f"✅ *完成*: {ok}/{len(tgt_ids)} 成功"
                if errors:
                    msg += f"\n❌ {len(errors)} 失败:\n" + "\n".join(
                        f"  [{r.get('account_id','?')}] {r.get('error','?')[:60]}" for r in errors[:5])
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=batch_menu())
                return

        self.user_states.pop(uid, None)
        await update.message.reply_text("❌ 输入无效", reply_markup=main_menu())

    # ==================== 批量执行引擎 ====================
    async def _execute_batch(self, task_type: str, account_ids: list, params: dict) -> list:
        from core.telethon_engine import human_delay
        results = []
        for i, aid in enumerate(account_ids):
            if i > 0:
                d = human_delay(
                    float(self.db.get_setting("random_delay_min", "0.8")),
                    float(self.db.get_setting("random_delay_max", "3.5"))
                )
                await asyncio.sleep(d)
            try:
                if task_type == "join_group":
                    r = await self.engine.join_group(aid, params.get("link", ""))
                elif task_type == "change_name":
                    r = await self.engine.change_name(aid, params.get("first_name", ""))
                elif task_type == "change_2fa":
                    r = await self.engine.change_2fa(aid, params.get("old_password", ""),
                                                      params.get("new_password", ""))
                elif task_type == "mass_dm":
                    r = await self.engine.send_message(aid, params.get("target", ""),
                                                       params.get("message", ""))
                elif task_type == "quick_setup":
                    r = await self.engine.join_group(aid, params.get("link", ""))
                    results.append({"account_id": aid, **r})
                    if r.get("success") and params.get("first_name"):
                        r2 = await self.engine.change_name(aid, params["first_name"])
                        results.append({"account_id": aid, "type": "name", **r2})
                        continue
                else:
                    r = {"success": False, "error": f"未知类型: {task_type}"}
                results.append({"account_id": aid, **r})
            except Exception as e:
                results.append({"account_id": aid, "success": False, "error": str(e)})
        return results

    # ==================== 回复消息 ====================
    async def _handle_reply_command(self, update, text):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("格式: /reply <消息ID> <中文回复>"); return
        try:
            msg_id = int(parts[1])
            reply_text = parts[2]
        except:
            await update.message.reply_text("消息ID必须是数字"); return
        msgs = self.db.get_unreplied_messages()
        target = next((m for m in msgs if m["id"] == msg_id), None)
        if not target:
            await update.message.reply_text(f"消息 #{msg_id} 不存在"); return
        r = await self.engine.send_message(target["account_id"], str(target["sender_id"]), reply_text)
        if r.get("success"):
            self.db.mark_replied(msg_id)
            await update.message.reply_text(f"✅ 已回复 #{msg_id}", reply_markup=dm_menu())
        else:
            await update.message.reply_text(f"❌ {r.get('error')}")

    # ==================== 辅助显示 ====================
    async def _show_accounts(self, q, page):
        r = self.account_mgr.list_accounts(page=page, page_size=10)
        if r["total"] == 0:
            await q.edit_message_text("📝 暂无账号", reply_markup=accounts_menu()); return
        lines = [f"📝 *账号 ({r['total']})*\n"]
        for a in r["accounts"]:
            has = "🟢" if os.path.isfile(a["session_path"]) else "⚪"
            lines.append(f"`{a['id']}` {has} {a['name']} | {a['phone']}")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN,
            reply_markup=pagination_menu(page, max(r["total_pages"], 1), "listacc", ""))

    async def _show_groups(self, q):
        groups = self.db.list_groups()
        if not groups:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ 创建", callback_data="act_create_group")],
                [InlineKeyboardButton("📤 分配账号到分组", callback_data="act_assign_group")],
                [InlineKeyboardButton("🔍 检测未分组账号", callback_data="act_ungrouped_list")],
                [InlineKeyboardButton("📤 移出分组", callback_data="act_ungroup_from_group")],
                [BACK_BTN]])
            await q.edit_message_text("📁 暂无分组", reply_markup=kb); return
        lines = [f"• *{g['name']}* ({g['account_count']})" for g in groups]
        await q.edit_message_text("📁 *分组*\n\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ 创建", callback_data="act_create_group"),
                 InlineKeyboardButton("🗑 删除", callback_data="act_delete_group")],
                [InlineKeyboardButton("📤 分配账号到分组", callback_data="act_assign_group")],
                [InlineKeyboardButton("🔍 检测未分组账号", callback_data="act_ungrouped_list"),
                 InlineKeyboardButton("📦 转移未分组到组", callback_data="act_ungrouped_move")],
                [InlineKeyboardButton("📤 移出分组", callback_data="act_ungroup_from_group")],
                [BACK_BTN]]))

    async def _show_delete_list(self, q, page):
        uid = q.from_user.id
        r = self.account_mgr.list_accounts(page=page, page_size=10)
        st = self.user_states.get(uid, {"sel": [], "pg": 0})
        sel = st.get("sel", []); st["pg"] = page; self.user_states[uid] = st
        if r["total"] == 0: await q.edit_message_text("📝 暂无", reply_markup=accounts_menu()); return
        kb = [[InlineKeyboardButton(f"{'☑️' if a['id'] in sel else '⬜'} {a['name']}", callback_data=f"delacc_toggle_{a['id']}")] for a in r["accounts"]]
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"delacc_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{max(r['total_pages'],1)}", callback_data="noop"))
        if page < r["total_pages"] - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"delacc_page_{page+1}"))
        if nav: kb.append(nav)
        kb.append([InlineKeyboardButton(f"🗑 确认 ({len(sel)})", callback_data="delacc_confirm"), BACK_BTN])
        await q.edit_message_text(f"🗑 选择要删除的账号 ({r['total']})", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

    async def _show_assign(self, q, page):
        uid = q.from_user.id
        r = self.account_mgr.list_accounts(page=page, page_size=10)
        st = self.user_states.get(uid, {"sel": [], "pg": 0})
        sel = st.get("sel", []); st["pg"] = page; self.user_states[uid] = st
        if r["total"] == 0: await q.edit_message_text("📝 暂无", reply_markup=groups_menu()); return
        kb = [[InlineKeyboardButton(f"{'☑️' if a['id'] in sel else '⬜'} {a['name']}", callback_data=f"asgn_tog_{a['id']}")] for a in r["accounts"]]
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"asgn_pg_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{max(r['total_pages'],1)}", callback_data="noop"))
        if page < r["total_pages"] - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"asgn_pg_{page+1}"))
        if nav: kb.append(nav)
        kb.append([InlineKeyboardButton(f"✅ 确认 ({len(sel)})", callback_data="asgn_confirm"), BACK_BTN])
        await q.edit_message_text(f"📤 分配账号到分组", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

    async def _show_ungrouped(self, q, page):
        r = self.account_mgr.list_ungrouped_accounts(page=page, page_size=10)
        if r["total"] == 0:
            await q.edit_message_text("✅ 所有账号已分组", reply_markup=groups_menu()); return
        lines = [f"🔍 *未分组账号 ({r['total']})*\n"]
        for a in r["accounts"]:
            has = "🟢" if os.path.isfile(a["session_path"]) else "⚪"
            lines.append(f"`{a['id']}` {has} {a['name']} | {a['phone']}")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN,
            reply_markup=pagination_menu(page, max(r["total_pages"], 1), "ungrouped", ""))

    async def _show_ungrouped_move(self, q, uid, page):
        r = self.account_mgr.list_ungrouped_accounts(page=page, page_size=10)
        st = self.user_states.get(uid, {"sel": [], "pg": 0})
        sel = st.get("sel", []); st["pg"] = page; self.user_states[uid] = st
        if r["total"] == 0:
            await q.edit_message_text("✅ 所有账号已分组", reply_markup=groups_menu()); return
        kb = [[InlineKeyboardButton(
            f"{'☑️' if a['id'] in sel else '⬜'} {a['name']}", callback_data=f"ungrouped_move_tog_{a['id']}")]
            for a in r["accounts"]]
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"ungrouped_move_pg_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{max(r['total_pages'],1)}", callback_data="noop"))
        if page < r["total_pages"] - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"ungrouped_move_pg_{page+1}"))
        if nav: kb.append(nav)
        kb.append([InlineKeyboardButton(f"✅ 选择分组 ({len(sel)})", callback_data="ungrouped_move_next"), BACK_BTN])
        await q.edit_message_text(
            f"📦 选择未分组账号转移到目标组 ({r['total']})", parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(kb))

    async def _show_ungroup_from(self, q, uid, gid, page):
        r = self.account_mgr.list_accounts(group_id=gid, page=page, page_size=10)
        st = self.user_states.get(uid, {"sel": [], "pg": 0, "gid": gid})
        sel = st.get("sel", []); st["pg"] = page; self.user_states[uid] = st
        g = self.db.get_group(gid)
        if r["total"] == 0:
            await q.edit_message_text(f"「{g['name']}」内无账号", reply_markup=groups_menu()); return
        kb = [[InlineKeyboardButton(
            f"{'☑️' if a['id'] in sel else '⬜'} {a['name']}", callback_data=f"ungroup_tog_{a['id']}")]
            for a in r["accounts"]]
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"ungroup_pg_{page-1}_{gid}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{max(r['total_pages'],1)}", callback_data="noop"))
        if page < r["total_pages"] - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"ungroup_pg_{page+1}_{gid}"))
        if nav: kb.append(nav)
        kb.append([InlineKeyboardButton(f"✅ 移出 ({len(sel)})", callback_data=f"ungroup_exec_{gid}"), BACK_BTN])
        await q.edit_message_text(
            f"📤 从「{g['name']}」移出账号 ({r['total']})", parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(kb))

    async def _show_export_selection(self, q, uid, page):
        r = self.account_mgr.list_accounts(page=page, page_size=10)
        st = self.user_states.get(uid, {"sel": [], "pg": 0})
        sel = st.get("sel", []); st["pg"] = page; self.user_states[uid] = st
        if r["total"] == 0:
            await q.edit_message_text("📝 暂无账号", reply_markup=accounts_menu()); return
        kb = [[InlineKeyboardButton(
            f"{'☑️' if a['id'] in sel else '⬜'} {a['name']}", callback_data=f"export_tog_{a['id']}")]
            for a in r["accounts"]]
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"export_pg_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{max(r['total_pages'],1)}", callback_data="noop"))
        if page < r["total_pages"] - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"export_pg_{page+1}"))
        if nav: kb.append(nav)
        kb.append([InlineKeyboardButton(f"📦 导出 ({len(sel)})", callback_data="export_exec"), BACK_BTN])
        await q.edit_message_text(
            f"📦 选择要导出的账号 ({r['total']})", parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(kb))

    async def _do_export(self, q, uid, account_ids: list = None, group_id: int = None):
        zip_path = os.path.join(config.uploads_dir, f"export_{uid}_{int(time.time())}.zip")
        result = self.account_mgr.export_to_zip(zip_path, account_ids=account_ids, group_id=group_id)
        if result["success"]:
            try:
                with open(zip_path, "rb") as f:
                    await q.message.reply_document(
                        document=f,
                        filename=f"accounts_{result['count']}.zip",
                        caption=f"📦 导出 {result['count']} 个账号",
                    )
            except Exception as e:
                logger.error("发送导出文件失败: %s", e)
            os.remove(zip_path)
            await q.edit_message_text(f"✅ 已导出 {result['count']} 个账号", reply_markup=accounts_menu())
        else:
            await q.edit_message_text(f"❌ {result.get('error', '导出失败')}", reply_markup=accounts_menu())

    async def _show_target_choice(self, q):
        await q.edit_message_text("🔄 选择目标:\n👥 按分组 / 📋 按ID", parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 按分组", callback_data="act_batch_by_group"),
                 InlineKeyboardButton("📋 按ID", callback_data="act_batch_by_ids")],
                 [BACK_BTN]]))

    async def error_handler(self, update, context):
        logger.error("Bot错误: %s", context.error, exc_info=True)

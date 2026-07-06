"""Bot 菜单键盘 - 完整版"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

BACK_BTN = InlineKeyboardButton("🔙 返回主菜单", callback_data="menu_main")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 账号管理", callback_data="menu_accounts"),
         InlineKeyboardButton("📨 群发私信", callback_data="menu_dm")],
        [InlineKeyboardButton("👥 群组管理", callback_data="menu_groups"),
         InlineKeyboardButton("🔍 群组搜索", callback_data="menu_search")],
        [InlineKeyboardButton("⚙️ 批量操作", callback_data="menu_batch"),
         InlineKeyboardButton("📊 运行状态", callback_data="menu_status")],
        [InlineKeyboardButton("🔧 系统设置", callback_data="menu_settings")],
    ])


def accounts_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ 导入账号 (上传ZIP)", callback_data="act_import_accounts")],
        [InlineKeyboardButton("🔄 验证账号", callback_data="act_verify_accounts"),
         InlineKeyboardButton("📝 账号列表", callback_data="act_list_accounts")],
        [InlineKeyboardButton("📁 分组管理", callback_data="act_manage_groups"),
         InlineKeyboardButton("🗑 删除账号", callback_data="act_delete_account")],
        [InlineKeyboardButton("📦 导出账号 (ZIP)", callback_data="act_export_accounts"),
         InlineKeyboardButton("🔢 重新编号", callback_data="act_renumber")],
        [BACK_BTN],
    ])


def groups_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 提取群成员", callback_data="act_scrape_members")],
        [BACK_BTN],
    ])


def dm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 新建群发任务", callback_data="act_new_dm")],
        [InlineKeyboardButton("📊 查看任务状态", callback_data="act_dm_status")],
        [InlineKeyboardButton("💬 查看回复消息", callback_data="act_view_replies")],
        [InlineKeyboardButton("🔔 开始监听", callback_data="act_monitor_start"),
         InlineKeyboardButton("🔕 停止监听", callback_data="act_monitor_stop")],
        [BACK_BTN],
    ])


def batch_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 按分组操作", callback_data="act_batch_by_group"),
         InlineKeyboardButton("📋 按指定账号", callback_data="act_batch_by_ids")],
        [InlineKeyboardButton("✏️ 批量改名", callback_data="act_change_name"),
         InlineKeyboardButton("🔗 批量进群", callback_data="act_batch_join")],
        [InlineKeyboardButton("🔑 批量改2FA", callback_data="act_change_2fa"),
         InlineKeyboardButton("🖼 批量换头像", callback_data="act_change_avatar")],
        [InlineKeyboardButton("⚡ 一键任务 (进群+改名)", callback_data="act_quick_task"),
         InlineKeyboardButton("📊 查看进度", callback_data="act_view_tasks")],
        [BACK_BTN],
    ])


def status_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 刷新状态", callback_data="act_refresh_status")],
        [InlineKeyboardButton("📈 系统资源", callback_data="act_system_info")],
        [BACK_BTN],
    ])


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 DeepSeek API Key", callback_data="act_set_api_key")],
        [InlineKeyboardButton("⚡ 并发数量", callback_data="act_set_concurrency")],
        [InlineKeyboardButton("⏱ 随机延时范围(秒)", callback_data="act_set_delay")],
        [InlineKeyboardButton("🌐 API 凭据 (ID/Hash)", callback_data="act_set_proxy")],
        [BACK_BTN],
    ])


def pagination_menu(page: int, total_pages: int, prefix: str, extra: str = "") -> InlineKeyboardMarkup:
    kb = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"{prefix}_page_{page-1}_{extra}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"{prefix}_page_{page+1}_{extra}"))
    if nav: kb.append(nav)
    kb.append([BACK_BTN])
    return InlineKeyboardMarkup(kb)


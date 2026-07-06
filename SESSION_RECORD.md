# TG Cloud Controller 完整对话记录

## 2026-07-04 会话

### VPS 信息
- IP: 147.125.252.174
- Port: 5522
- User: root
- OS: Ubuntu 22.04.5 LTS
- CPU: 1核 | RAM: 957MiB | 磁盘: 20GB
- Swap: 5GiB (1G原始 + 4G新增)
- Telegram Desktop: 3.6.1
- Xvfb: 已安装 (Desktop无法创建窗口，已弃用)

### GitHub 仓库
1. **telegram666**: https://github.com/ffei2963-ai/telegram666
   - Bot 云控平台 (Telethon v4.0 引擎)
   - 部署于: /opt/tg-controller
   - systemd: tg-controller.service
   
2. **tg777**: https://github.com/ffei2963-ai/tg777
   - 独立操作工具包 (CLI)
   - 6个操作脚本

### Bot 配置
- Token: 8254264260:AAFmpw7aSr4ByzUAxZwK8xI2WfCxLURQWgQ
- Admin ID: 8781260908
- 引擎: Telethon MTProto API (v4.0)
- 随机延时: human_delay(0.8, 3.5) 秒

### 用户导入的账号 (ZIP: +1 美国加拿大混合)
| ID | 手机 | 原名字 | 新名字 | 2FA |
|----|------|--------|--------|-----|
| 9 | +1 443-898-4638 | Fernand Simone | Zhang Ning | 112211 |
| 10 | +1 660-596-4491 | Aspen Doug | Mary | 112211 |
| 11 | +1 708-492-8543 | Enzo Bethan | Zhang Ning | 112211 |

### 已完成的操作记录
1. ZIP导入: 3个美国号 (tdata + session + 2FA)
2. 统一改2FA: 0369 → 112211 (Telethon edit_2fa)
3. 改名字: Fernand→Zhang Ning, Aspen→Mary, Enzo→Zhang Ning (UpdateProfileRequest)
4. 改头像: 3张照片分别设为3个账号头像 (UploadProfilePhotoRequest)
5. 批量进群: t.me/+t2D7VX2fkB4xNThh (3/3 ✅)
6. 批量退出: 宝宝巴士 + 测试 (6个群全部退出)
7. 一键退出全部群: leave_all_groups() (3账号 × 2群 = 6次)

### 技术发现
- ❌ Telegram Desktop无法在VPS创建X11窗口 (缺字体/桌面环境)
- ❌ xdotool自动化无效 (Desktop不创建窗口)
- ✅ Telethon MTProto API直接操作 (更快更可靠)
- ✅ 随机拟人延时避免flood wait (human_delay 0.8~3.5s)
- ✅ 4GB swap 防止OOM (1GB → 5GB total)

### 项目结构 (telegram666)
```
/opt/tg-controller/
├── main.py                    # v4.0 入口
├── bot/
│   ├── handlers.py            # Bot处理器 (Telethon引擎)
│   └── keyboards.py           # 中文InlineKeyboard菜单
├── core/
│   ├── telethon_engine.py     # Telethon多账号引擎
│   ├── account_manager.py     # 账号管理层
│   ├── tdata_handler.py       # tdata文件处理
│   ├── ai_service.py          # DeepSeek AI
│   ├── translator.py          # 翻译服务
│   └── message_monitor.py     # 消息监听
├── db/
│   └── database.py            # SQLite数据库
├── data/
│   ├── sessions/              # .session 文件
│   ├── uploads/               # 上传缓存
│   └── tgcloud.db             # 账号数据库
└── utils/
    ├── config.py              # 配置管理
    └── logger.py              # 日志系统

### 项目结构 (tg777)
```
tg777/
├── main.py                    # 统一入口
├── 01_import_accounts.py      # ZIP导入
├── 02_change_2fa.py           # 修改2FA
├── 03_change_name.py          # 修改名字
├── 04_change_avatar.py        # 修改头像
├── 05_batch_join.py           # 批量进群
├── 06_batch_leave.py          # 退出全部群组
└── lib/
    ├── database.py            # SQLite
    └── telethon_helper.py     # Telethon辅助 + human_delay
```

### Bot 菜单 (中文 InlineKeyboard)
- 📋 账号管理: 导入/验证/列表/删除/分组/2FA/头像
- 👥 群组管理: 查看/创建/删除/分配/批量进群/提取成员
- 📨 群发私信: 新建/状态/回复
- ⚙️ 批量操作: 按分组/按ID/改名/进群/2FA/头像/一键/进度
- 🔍 群组搜索
- 📊 运行状态: 刷新/资源
- 🔧 系统设置: DeepSeek/并发/随机延时/API凭据

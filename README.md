<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg" alt="Docker">
</p>

<p align="center">
  <h1 align="center">🤖 TG Cloud Controller</h1>
  <p align="center">Enterprise-grade Telegram Cloud Control Platform</p>
  <p align="center">企业级 Telegram 云控矩阵管理平台</p>
</p>

---

## 📖 简介

TG Cloud Controller 是一个基于 Python 的 Telegram 账号矩阵云控管理系统。通过统一的 Telegram Bot 界面，你可以轻松管理数十、数百个 Telegram 账号，实现批量操作自动化。

### ✨ 核心功能

| 功能模块 | 说明 | 状态 |
|---------|------|------|
| 📋 账号管理 | ZIP 批量导入、tdata 自动识别、分组管理 | ✅ 已完成 |
| 🤖 Bot 控制 | 中文 InlineKeyboard 菜单、指令路由 | ✅ 已完成 |
| 🧠 AI 集成 | 接入 DeepSeek API，智能指令解析 | ✅ 已完成 |
| 📨 群发私信 | 批量发送、监听回复、中英双向翻译 | ✅ 已完成 |
| 👥 批量进群 | 指定账号/分组批量加入群组 | ✅ 已完成 |
| 🔑 批量修改 | 2FA/头像/名字一键批量修改 | ✅ 已完成 |
| 🔍 群组搜索 | 关键词搜索 + 自动加入 + 提取成员 | ✅ 已完成 |
| 🧠 DeepSeek AI | 智能指令解析、消息总结 | ✅ 已完成 |

---

## 🏗 架构

```
┌──────────────────────────────────────────┐
│              Management Bot              │
│         (python-telegram-bot)            │
│     中文 InlineKeyboard 菜单 / 指令路由    │
└──────────────┬───────────────────────────┘
               │
┌──────────────▼───────────────────────────┐
│           Core Services (Python)         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Account  │ │  Batch   │ │ Message  │ │
│  │ Manager  │ │   Ops    │ │ Monitor  │ │
│  └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Creator  │ │  Group   │ │ DeepSeek │ │
│  │ (注册)    │ │ Scraper  │ │   AI     │ │
│  └──────────┘ └──────────┘ └──────────┘ │
└──────────────┬───────────────────────────┘
               │
┌──────────────▼───────────────────────────┐
│       Telethon Engine (多会话并发)       │
│         SQLite 数据库 / tdata 处理        │
└──────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
- Docker & Docker Compose (推荐)
- Telegram Bot Token ([@BotFather](https://t.me/BotFather) 获取)
- DeepSeek API Key ([platform.deepseek.com](https://platform.deepseek.com/api_keys) 获取)

### 方式一：Docker 部署 (推荐)

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/tg-cloud-controller.git
cd tg-cloud-controller

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 Bot Token 和 API Key

# 3. 启动
docker compose up -d

# 4. 查看日志
docker compose logs -f
```

### 方式二：直接运行

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
cp .env.example .env
# 编辑 .env 填入配置

# 4. 运行
python main.py
```

### 配置说明

| 环境变量 | 必填 | 说明 |
|---------|------|------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot Token |
| `TG_ADMIN_IDS` | ❌ | 管理员用户ID (逗号分隔) |
| `DEEPSEEK_API_KEY` | ❌ | DeepSeek API Key |
| `DEEPSEEK_MODEL` | ❌ | 模型名称 (默认 deepseek-chat) |
| `MAX_CONCURRENT_ACCOUNTS` | ❌ | 最大并发账号数 (默认 5) |

---

## 📁 项目结构

```
tg-cloud-controller/
├── main.py                  # 入口文件
├── config.yaml              # 配置文件
├── Dockerfile               # Docker 构建
├── docker-compose.yml       # Docker 编排
├── requirements.txt         # Python 依赖
├── bot/
│   ├── handlers.py          # Bot 指令处理
│   └── keyboards.py         # InlineKeyboard 菜单定义
├── core/
│   ├── account_manager.py   # 账号管理服务
│   ├── tdata_handler.py     # tdata 文件解析
│   └── ai_service.py        # DeepSeek AI 集成
├── db/
│   └── database.py          # SQLite 数据库操作
├── utils/
│   ├── config.py            # 配置管理
│   └── logger.py            # 日志工具
└── data/                    # 运行时数据 (volume)
    ├── sessions/            # Telethon session 文件
    ├── uploads/             # ZIP 上传缓存
    └── tgcloud.db           # SQLite 数据库
```

---

## 📤 账号导入

### ZIP 文件格式

每个子目录对应一个独立 Telegram 账号，支持的目录结构：

```
accounts_package.zip
├── account_1/
│   ├── tdata/              # Telegram Desktop 数据目录
│   │   ├── key_datas
│   │   └── D877F783D5D3EF8C*
│   ├── account.session     # Telethon session 文件 (可选)
│   ├── info.json           # 账号信息 {phone, name}
│   └── password.txt        # 2FA 密码 (可选)
├── account_2/
│   ├── tdata/
│   ├── account.session
│   └── info.json
└── account_3/
    ├── tdata/
    └── ...
```

### 导入方式

1. 在 Bot 中点击「📋 账号管理」→「➕ 导入账号」
2. 上传 ZIP 文件
3. 系统自动解析并导入所有账号

---

## 🧠 AI 智能管理

集成 **DeepSeek API**，支持：

- 自然语言指令解析
- 消息智能总结
- 自动回复建议
- 批量任务智能调度

配置 API Key 后在 Bot 中点击「🔧 系统设置」→「🔑 设置API Key」输入即可。

---

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Bot 框架 | python-telegram-bot 21.x |
| 账号引擎 | Telethon 1.36 |
| AI 模型 | DeepSeek (API) |
| 数据库 | SQLite |
| 容器化 | Docker |

---

## 📄 License

MIT License

---

## 🧪 测试结果

测试环境: 1CPU / 957MiB RAM / Ubuntu 22.04

| 测试类型 | 结果 | 说明 |
|---------|------|------|
| 功能测试 (test_suite.py) | ✅ 62/62 (100%) | 数据库/导入/tdata/AI/菜单/日志 |
| 压力测试 (stress_test.py) | ✅ 26/26 (100%) | 5000账号/200分组/10000任务/10线程并发 |
| 稳定性 (stability_test.py) | ✅ 599/600 (99.8%) | 600轮模拟60天, 内存增长6.1%, 无泄漏 |

```bash
# 运行测试
python3 test_suite.py      # 功能测试
python3 stress_test.py     # 压力测试
python3 stability_test.py  # 稳定性测试
```

---

## ⚠️ 免责声明

本工具仅供学习研究使用。请遵守 Telegram 服务条款，不要将此工具用于任何非法活动。使用者需自行承担所有风险和责任。

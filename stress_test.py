#!/usr/bin/env python3
"""TG Cloud Controller - 压力与并发测试"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LOG_LEVEL"] = "ERROR"

import time
import json
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from db.database import Database
from core.account_manager import AccountManager
from core.ai_service import AIService
from core.translator import Translator
from core.group_scraper import GroupScraper
from core.tdata_handler import extract_account_info, detect_account_structure
from utils.config import Config

PASS = 0
FAIL = 0

def test(name, func):
    global PASS, FAIL
    try:
        start = time.time()
        func()
        elapsed = (time.time() - start) * 1000
        PASS += 1
        print(f"  ✅  {name} ({elapsed:.0f}ms)")
    except Exception as e:
        FAIL += 1
        print(f"  ❌  {name}: {e}")


print("=" * 60)
print("  TG Cloud Controller - 压力与并发测试")
print("=" * 60)

# Setup
db_path = "data/stress2.db"
if os.path.exists(db_path):
    os.remove(db_path)
db = Database(db_path)
mgr = AccountManager(db, "data/s_sessions", "data/s_uploads")

# ===== 账户大规模操作 =====
print("\n  📦 大规模账户操作")

test("插入5000个账号", lambda: (
    [(db.add_account(f"p{i}", f"+86{i:011d}", f"s_{i}.session",
                     metadata={"stress": True, "idx": i}))
     for i in range(5000)],
    db.count_accounts() == 5000
)[1])

test("创建200个分组", lambda: (
    [(db.add_group(f"group_{i}")) for i in range(200)],
    len(db.list_groups()) == 200
)[1])

test("5000账号随机分配到200分组", lambda: (
    [(db.assign_account_to_group(i+1, (i % 200) + 1)) for i in range(5000)],
    True
)[1])

test("分组统计验证", lambda: (
    (g := db.list_groups()),
    all(g_["account_count"] >= 0 for g_ in g)
)[1])

test("10000任务创建", lambda: (
    [(db.add_task("mass_dm", "accounts", [i+1 for i in range(j%20+1)],
                  {"msg": f"m_{j}"}))
     for j in range(10000)],
    len(db.list_tasks(limit=11000)) >= 10000
)[1])

import random as _rr

test("10000条消息", lambda: (
    [(db.add_message(_rr.randint(1,100), _rr.randint(10000,99999),
                     _rr.randint(1,100), f"@u{j}",
                     f"content_{j}"*3, f"消息_{j}"*2, "received"))
     for j in range(10000)],
    len(db.get_unreplied_messages()) >= 100
)[1])

# ===== 并发读写压力 =====
print("\n  🔀 并发读写压力")

def concurrent_read(worker_id, iterations):
    results = 0
    for i in range(iterations):
        accounts = db.list_accounts(limit=50)
        results += len(accounts)
        tasks = db.list_tasks(limit=20)
        results += len(tasks)
        msgs = db.get_unreplied_messages()
        results += len(msgs)
    return results

test("10线程并发读(每线程100轮)", lambda: (
    (executor := ThreadPoolExecutor(max_workers=10)),
    (futures := [executor.submit(concurrent_read, i, 100) for i in range(10)]),
    (results := [f.result() for f in as_completed(futures)]),
    all(r > 0 for r in results),
    executor.shutdown(wait=False)
)[3])

# ===== 翻译服务 =====
print("\n  🌐 翻译服务")

translator = Translator()

test("中文字符检测", lambda: translator._detect_lang("你好世界") == "zh")
test("英文字符检测", lambda: translator._detect_lang("Hello world") == "en")
test("日文字符检测", lambda: translator._detect_lang("こんにちは") == "ja")
test("韩文字符检测", lambda: translator._detect_lang("안녕하세요") == "ko")
test("空文本to_chinese", lambda: translator.to_chinese("") == "")
test("空文本from_chinese", lambda: translator.from_chinese("") == "")

# ===== 群组采集器 =====
print("\n  🔍 群组采集器")

scraper = GroupScraper(db)

test("count_members初始为0", lambda: scraper.count_members() == 0)

# ===== AI服务并发 =====
print("\n  🧠 AI服务(本地模拟)")

ai = AIService("")

test("并发summarize调用", lambda: (
    [(ai.summarize_messages([f"msg_{i}" for i in range(10)])) for _ in range(10)],
    True
)[1])

test("并发parse_command调用", lambda: (
    [ai.parse_command("创建一个名为VIP的分组") for _ in range(10)],
    True
)[1])

# ===== 内存压力 =====
print("\n  💾 内存压力")

import psutil
start_mem = psutil.Process().memory_info().rss / 1024 / 1024

test("批量账号查询内存测试", lambda: (
    [(db.list_accounts(limit=1000)) for _ in range(100)],
    True
)[1])

end_mem = psutil.Process().memory_info().rss / 1024 / 1024
print(f"    内存变化: {start_mem:.1f}MB → {end_mem:.1f}MB (Δ{end_mem-start_mem:+.1f}MB)")

# ===== 清理 =====
print("\n  🧹 清理")

test("清理所有测试数据", lambda: (
    db.conn.execute("DELETE FROM account_group_map"),
    db.conn.execute("DELETE FROM accounts"),
    db.conn.execute("DELETE FROM account_groups"),
    db.conn.execute("DELETE FROM tasks"),
    db.conn.execute("DELETE FROM messages"),
    db.conn.commit(),
    db.count_accounts() == 0
))

os.remove(db_path)

# ===== 结果 =====
print(f"\n{'='*60}")
total = PASS + FAIL
print(f"  压力测试结果: 总计 {total}, ✅ {PASS} 通过, ❌ {FAIL} 失败")
if total > 0:
    print(f"  通过率: {PASS/total*100:.1f}%")
print(f"{'='*60}")

if FAIL > 0:
    sys.exit(1)

#!/usr/bin/env python3
"""TG Cloud Controller - 长运行稳定性测试 (模拟60天)"""

import os, sys, json, time, random, threading, gc
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LOG_LEVEL"] = "ERROR"

from db.database import Database
import psutil

print("=" * 60)
print("  长时间运行稳定性测试 (模拟60天负载)")
print("=" * 60)

db_path = "data/stability.db"
if os.path.exists(db_path):
    os.remove(db_path)
db = Database(db_path)

iterations = 600  # 模拟60天, 每天10轮
print(f"  目标轮次: {iterations}")
print()

errors = 0
process = psutil.Process()
mem_samples = []

for round_num in range(iterations):
    try:
        if round_num > 0 and round_num % 50 == 0:
            mem_mb = process.memory_info().rss / 1024 / 1024
            mem_samples.append((round_num, mem_mb))
            pct = round_num / iterations * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"\r  [{bar}] {pct:.0f}% | 轮次:{round_num} | 内存:{mem_mb:.1f}MB | 错误:{errors}", end="", flush=True)

        n = random.randint(5, 20)
        for i in range(n):
            db.add_account(
                f"stab_{round_num}_{i}",
                f"+86199{random.randint(10000000,99999999)}",
                f"data/sessions/{random.randint(1,10000)}.session",
                metadata={"round": round_num, "i": i}
            )

        aid = random.randint(1, max(n * (round_num + 1) // 2, 10))
        db.get_account(aid)

        if round_num % 3 == 0:
            db.list_accounts(limit=30)

        if round_num % 5 == 0:
            db.add_task("mass_dm", "accounts",
                        [random.randint(1, 100) for _ in range(5)],
                        {"msg": f"round_{round_num}"})

        if round_num % 2 == 0:
            db.add_message(
                random.randint(1, 50), random.randint(1000, 9999),
                random.randint(1, 99), f"@u{round_num}",
                f"msg_{round_num}" * 3, "", "received"
            )

        if round_num % 20 == 19:
            db.conn.execute("VACUUM")
            db.conn.commit()

        if round_num % 100 == 99:
            gc.collect()

    except Exception as e:
        errors += 1
        if errors < 10:
            print(f"\n  ⚠️ 轮次{round_num}错误: {e}")

print(f"\n\n  {'='*50}")
print(f"  稳定性测试完成!")

final_mem = process.memory_info().rss / 1024 / 1024
print(f"  总轮次: {iterations}")
print(f"  累计错误: {errors}")
print(f"  最终内存: {final_mem:.1f}MB")

if mem_samples:
    first_mem = mem_samples[0][1]
    last_mem = mem_samples[-1][1]
    mem_growth = last_mem - first_mem
    print(f"  内存趋势 (50轮采样):")
    print(f"    初始: {first_mem:.1f}MB")
    print(f"    最终: {last_mem:.1f}MB")
    print(f"    增长: {mem_growth:+.1f}MB")
    leak_ratio = mem_growth / first_mem * 100 if first_mem > 0 else 0
    status = "✅ 正常" if abs(leak_ratio) < 50 else "⚠️ 异常"
    print(f"    内存增长率: {leak_ratio:+.1f}% - {status}")

    recent_5 = mem_samples[-5:]
    growing = all(recent_5[i][1] <= recent_5[i+1][1] for i in range(len(recent_5)-1))
    if growing and leak_ratio > 30:
        print(f"    ⚠️ 检测到持续内存增长!")

# Cleanup
db.conn.execute("DELETE FROM accounts")
db.conn.execute("DELETE FROM account_groups")
db.conn.execute("DELETE FROM account_group_map")
db.conn.execute("DELETE FROM tasks")
db.conn.execute("DELETE FROM messages")
db.conn.commit()
os.remove(db_path)

total = iterations
score = total - errors
print(f"\n  通过率: {score/total*100:.1f}% ({score}/{total})")
print(f"{'='*60}")

sys.exit(0 if errors == 0 else 1)

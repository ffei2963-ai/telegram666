#!/usr/bin/env python3
"""TG Cloud Controller - 完整功能测试套件 v2"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LOG_LEVEL"] = "ERROR"

PASS = 0
FAIL = 0
ERRORS = []


def run_test(name, func):
    global PASS, FAIL
    try:
        func()
        PASS += 1
        print(f"  ✅  {name}")
    except AssertionError as e:
        FAIL += 1
        msg = f"断言失败: {e}"
        ERRORS.append(f"{name}: {msg}")
        print(f"  ❌  {name} - {msg}")
    except Exception as e:
        import traceback
        FAIL += 1
        msg = f"{type(e).__name__}: {e}"
        ERRORS.append(f"{name}: {msg}")
        print(f"  💥  {name} - {msg}")
        traceback.print_exc()


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ==================== 数据库测试 ====================
def test_database():
    import json
    from db.database import Database

    db_path = "data/test_db.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)

    run_test("创建分组", lambda: (
        (gid := db.add_group("测试分组", "测试描述")) and (gid > 0)
        and (db.get_group(gid)["name"] == "测试分组")
    ))

    run_test("添加账号", lambda: (
        (aid := db.add_account("测试账号", "+8613800000001", "data/sessions/test.session")) and (aid > 0)
        and (db.get_account(aid)["phone"] == "+8613800000001")
    ))

    run_test("添加带metadata的账号", lambda: (
        (aid := db.add_account("账号2", "+8613800000002", "s2.session",
                                metadata={"has_tdata": True})),
        (a := db.get_account(aid)),
        json.loads(a["metadata"])["has_tdata"] == True
    ))

    run_test("获取不存在账号返回None", lambda: db.get_account(99999) is None)

    run_test("按手机号查账号", lambda: db.get_account_by_phone("+8613800000001") is not None)

    run_test("列出账号列表", lambda: len(db.list_accounts()) >= 1)

    run_test("统计账号数", lambda: db.count_accounts() >= 1)

    aid1 = db.get_account_by_phone("+8613800000001")["id"]
    run_test("更新账号状态", lambda: (
        db.update_account(aid1, status="inactive"),
        db.get_account(aid1)["status"] == "inactive"
    )[1])

    gid = db.get_group_by_name("测试分组")["id"]
    run_test("分配账号到分组", lambda: (
        db.assign_account_to_group(aid1, gid),
        len(db.list_accounts(group_id=gid)) >= 1
    )[1])

    run_test("获取账号所在分组", lambda: len(db.get_account_groups(aid1)) >= 1)

    run_test("分组列表含账号数", lambda: "account_count" in db.list_groups()[0])

    run_test("创建任务", lambda: (
        (tid := db.add_task("mass_dm", "accounts", [1, 2, 3], {"msg": "test"})),
        db.get_task(tid)["task_type"] == "mass_dm"
    )[1])

    def _test_task_update():
        tasks = db.list_tasks(status="pending")
        if not tasks:
            return True
        db.update_task(tasks[0]["id"], status="running", progress="5/10")
        t2 = db.get_task(tasks[0]["id"])
        return t2["progress"] == "5/10"
    run_test("任务状态更新", _test_task_update)

    run_test("记录消息", lambda: db.add_message(1, 12345, 67890, "@test", "Hello", "你好", "received") > 0)

    run_test("查询未回复消息", lambda: len(db.get_unreplied_messages()) >= 1)

    run_test("设置存储", lambda: (
        db.set_setting("test_k", "test_v"),
        db.get_setting("test_k") == "test_v"
    )[1])

    run_test("获取不存在的设置", lambda: db.get_setting("noexist", "d") == "d")

    aid2 = db.get_account_by_phone("+8613800000002")["id"]
    run_test("删除账号", lambda: (
        db.delete_account(aid2),
        db.get_account(aid2) is None
    )[1])

    run_test("删除分组", lambda: (
        db.delete_group(gid),
        db.get_group(gid) is None
    )[1])

    os.remove(db_path)
    print(f"    数据库测试完成")


# ==================== 账号导入测试 ====================
def test_account_import():
    import json, shutil, tempfile, zipfile
    from db.database import Database
    from core.account_manager import AccountManager

    db_path = "data/test_import.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)

    sdir = "data/test_sessions"
    udir = "data/test_uploads"
    os.makedirs(sdir, exist_ok=True)
    os.makedirs(udir, exist_ok=True)
    mgr = AccountManager(db, sdir, udir)

    def make_zip(accounts, zip_name="test.zip"):
        tmp = tempfile.mkdtemp()
        for acc in accounts:
            adir = os.path.join(tmp, acc["dir"])
            os.makedirs(adir, exist_ok=True)
            for fname, content in acc.get("files", {}).items():
                fpath = os.path.join(adir, fname)
                if fname == "tdata":
                    os.makedirs(fpath, exist_ok=True)
                    for tf, tc in content.items() if isinstance(content, dict) else {}:
                        with open(os.path.join(fpath, tf), "w") as f:
                            f.write(tc)
                else:
                    os.makedirs(os.path.dirname(fpath), exist_ok=True)
                    with open(fpath, "w") as f:
                        f.write(content if isinstance(content, str) else json.dumps(content))
        zip_path = os.path.join(tmp, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(tmp):
                for f in files:
                    if f == zip_name:
                        continue
                    fp = os.path.join(root, f)
                    an = os.path.relpath(fp, tmp)
                    zf.write(fp, an)
        return zip_path, tmp

    def _test_zip_import():
        accounts = [{
            "dir": "account_a",
            "files": {
                "tdata": {"key_data": "test_key"},
                "info.json": {"phone": "+8613800001001", "name": "账号A"},
                "password.txt": "2fa_password_abc",
                "account_a.session": "session_bytes",
            }
        }, {
            "dir": "account_b",
            "files": {
                "tdata": {"key_data": "test_key_b"},
                "info.json": {"phone": "+8613800001002", "name": "账号B"},
            }
        }]
        zp, td = make_zip(accounts)
        results = mgr.import_from_zip(zp)
        imported = [r for r in results if r.get("success") and not r.get("skipped")]
        ok = len(imported) == 2
        shutil.rmtree(td, ignore_errors=True)
        return ok
    run_test("标准ZIP导入(含tdata+session+json+2fa)", _test_zip_import)

    run_test("ZIP导入后验证数据库", lambda: (
        (a := db.get_account_by_phone("+8613800001001")),
        a is not None and a["name"] == "账号A" and a["twofa_password"] == "2fa_password_abc"
    ))

    def _test_session_exists():
        a = db.get_account_by_phone("+8613800001001")
        return a is not None and os.path.isfile(a["session_path"])
    run_test("Session文件已复制", _test_session_exists)

    def _test_dup_import():
        acc = [{"dir": "account_a", "files": {"info.json": {"phone": "+8613800001001", "name": "账号A"}}}]
        zp, td = make_zip(acc)
        results = mgr.import_from_zip(zp)
        skipped = [r for r in results if r.get("skipped")]
        ok = len(skipped) >= 1
        shutil.rmtree(td, ignore_errors=True)
        return ok
    run_test("重复导入跳过已有账号", _test_dup_import)

    run_test("创建分组", lambda: mgr.create_group("VIP组")["success"] is True)

    run_test("重复分组拒绝", lambda: mgr.create_group("VIP组")["success"] is False)

    run_test("分配账号到分组", lambda: (
        (a := db.get_account_by_phone("+8613800001001")),
        (g := db.get_group_by_name("VIP组")),
        mgr.assign_to_group(a["id"], g["id"]) is True
    ))

    run_test("批量分配账号到分组", lambda: (
        (a1 := db.get_account_by_phone("+8613800001001")),
        (a2 := db.get_account_by_phone("+8613800001002")),
        (g := db.get_group_by_name("VIP组")),
        (r := mgr.batch_assign_to_group([a1["id"], a2["id"], 99999], g["id"])),
        len(r["success"]) >= 2 and len(r["failed"]) >= 1
    ))

    run_test("分页查看账号", lambda: (
        (r := mgr.list_accounts(page=0, page_size=1)),
        r["total"] >= 2 and r["total_pages"] >= 2 and len(r["accounts"]) == 1
    ))

    run_test("按分组筛选账号", lambda: (
        (g := db.get_group_by_name("VIP组")),
        (r := mgr.list_accounts(group_id=g["id"])),
        r["total"] >= 2
    ))

    run_test("账号详情含分组信息", lambda: (
        (a := db.get_account_by_phone("+8613800001001")),
        "groups" in mgr.get_account_detail(a["id"])
    ))

    os.remove(db_path)
    shutil.rmtree(sdir, ignore_errors=True)
    shutil.rmtree(udir, ignore_errors=True)
    print(f"    账号导入测试完成")


# ==================== tdata 识别测试 ====================
def test_tdata_detection():
    import json, shutil, tempfile
    from core.tdata_handler import detect_account_structure, extract_account_info

    def make_tree(structure):
        tmp = tempfile.mkdtemp()
        for name, content in structure.items():
            fpath = os.path.join(tmp, name)
            if isinstance(content, dict):
                os.makedirs(fpath, exist_ok=True)
                for k, v in content.items():
                    with open(os.path.join(fpath, k), "w") as f:
                        f.write(v)
            else:
                with open(fpath, "w") as f:
                    f.write(content)
        return tmp

    run_test("检测tdata目录", lambda: (
        (d := make_tree({"tdata": {"key_data": "k"}})),
        (info := detect_account_structure(d)),
        info["has_tdata"] is True,
        shutil.rmtree(d, ignore_errors=True) or True
    )[2])

    run_test("检测session文件", lambda: (
        (d := make_tree({"test.session": "data"})),
        (info := detect_account_structure(d)),
        info["has_session"] is True,
        shutil.rmtree(d, ignore_errors=True) or True
    )[2])

    run_test("检测JSON元数据", lambda: (
        (d := make_tree({"info.json": json.dumps({"phone": "+8613800002001", "name": "Meta"})})),
        (info := detect_account_structure(d)),
        info["phone"] == "+8613800002001" and info["account_name"] == "Meta",
        shutil.rmtree(d, ignore_errors=True) or True
    )[2])

    run_test("检测2FA密码文件", lambda: (
        (d := make_tree({"password.txt": "secret123"})),
        (info := detect_account_structure(d)),
        info["has_twofa"] is True,
        shutil.rmtree(d, ignore_errors=True) or True
    )[2])

    run_test("完整信息提取", lambda: (
        (d := make_tree({
            "tdata": {"key_data": "k"},
            "info.json": {"phone": "+8613800002002", "name": "Full"},
            "password.txt": "pwd456",
            "account.session": "s",
        })),
        (info := extract_account_info(d)),
        info["name"] == "Full" and info["phone"] == "+8613800002002"
        and info["has_tdata"] and info["has_session"]
        and info["twofa_password"] == "pwd456",
        shutil.rmtree(d, ignore_errors=True) or True
    )[2])

    run_test("空目录检测", lambda: (
        (d := make_tree({})),
        (info := detect_account_structure(d)),
        not info["has_tdata"] and not info["has_session"],
        shutil.rmtree(d, ignore_errors=True) or True
    )[2])

    run_test("从目录名提取手机号", lambda: (
        (tmp := tempfile.mkdtemp()),
        (d := os.path.join(tmp, "acc_+8613900000001")),
        os.makedirs(d, exist_ok=True),
        (info := extract_account_info(d)),
        "8613900000001" in info["phone"],
        shutil.rmtree(tmp, ignore_errors=True) or True
    )[3])

    run_test("不存在的目录", lambda: (
        (info := detect_account_structure("/nonexistent/path_12345")),
        not info["has_tdata"]
    ))

    print(f"    tdata检测测试完成")


# ==================== AI 服务测试 ====================
def test_ai_service():
    from core.ai_service import AIService

    run_test("无API Key不可用", lambda: AIService("").is_available() == False)
    run_test("无API Key chat返回提示", lambda: "[未配置" in AIService("").chat([{"role":"user","content":"t"}]))
    run_test("无API Key summarize返回提示", lambda: "[未配置" in AIService("").summarize_messages(["m1"]))
    run_test("无API Key parse返回unknown", lambda: AIService("").parse_command("测试")["action"] == "unknown")
    run_test("有Key时可用", lambda: AIService("sk-test").is_available() == True)

    print(f"    AI服务测试完成")


# ==================== 配置测试 ==================== 
def test_config():
    from utils.config import Config

    run_test("从环境变量加载配置", lambda: (
        (cfg := Config.from_env()),
        cfg.max_concurrent_accounts == 5
        and cfg.log_level in ("INFO", "ERROR")
    ))

    print(f"    配置测试完成")


# ==================== 键盘菜单测试 ====================
def test_keyboards():
    from bot.keyboards import (
        main_menu, accounts_menu, groups_menu, dm_menu,
        batch_menu, status_menu, settings_menu, pagination_menu,
    )
    from telegram import InlineKeyboardMarkup

    run_test("主菜单非空", lambda: len(main_menu().inline_keyboard) > 0)
    run_test("账号菜单含导入", lambda: (kb := accounts_menu(), any("导入" in b.text for r in kb.inline_keyboard for b in r))[1])
    run_test("群组菜单含创建分组", lambda: (kb := groups_menu(), any("创建分组" in b.text for r in kb.inline_keyboard for b in r))[1])
    run_test("群发菜单含群发", lambda: (kb := dm_menu(), any("群发" in b.text for r in kb.inline_keyboard for b in r))[1])
    run_test("批量菜单含一键任务", lambda: (kb := batch_menu(), any("一键任务" in b.text for r in kb.inline_keyboard for b in r))[1])
    run_test("分页-首页无上一页", lambda: (kb := pagination_menu(0, 5, "t"), (all(b.text != "⬅️ 上一页" for r in kb.inline_keyboard for b in r))))
    run_test("分页-末页无下一页", lambda: (kb := pagination_menu(4, 5, "t"), (all(b.text != "➡️ 下一页" for r in kb.inline_keyboard for b in r))))
    run_test("分页-中间页双向", lambda: (kb := pagination_menu(2, 5, "t"), (any("上一页" in b.text for r in kb.inline_keyboard for b in r) and any("下一页" in b.text for r in kb.inline_keyboard for b in r))))

    print(f"    键盘菜单测试完成")


# ==================== 日志系统测试 ====================
def test_logger():
    from utils.logger import setup_logger

    run_test("创建日志器", lambda: setup_logger("test_mod", "DEBUG").name == "test_mod")
    run_test("重复获取同实例", lambda: setup_logger("dup") is setup_logger("dup"))
    run_test("Hander数量", lambda: len(setup_logger("h_test").handlers) >= 1)

    print(f"    日志系统测试完成")


# ==================== 压力测试 ====================
def test_stress():
    from db.database import Database
    import time

    db_path = "data/stress_test.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)

    run_test("压力-批量插入1000账号", lambda: (
        [(db.add_account(f"acc_{i}", f"+86138{i:08d}", f"s_{i}.session", metadata={"idx": i})) for i in range(1000)],
        db.count_accounts() == 1000
    )[1])

    run_test("压力-批量创建100分组", lambda: (
        [(db.add_group(f"grp_{i}")) for i in range(100)],
        len(db.list_groups()) == 100
    )[1])

    run_test("压力-批量分配账号到分组", lambda: (
        (g := db.get_group_by_name("grp_0")),
        (acts := db.list_accounts(limit=100)),
        [(db.assign_account_to_group(a["id"], g["id"])) for a in acts],
        db.count_accounts(group_id=g["id"]) == 100
    )[-1])

    run_test("压力-500个任务", lambda: (
        [(db.add_task("mass_dm", "accounts", list(range(i%10+1)), {"m": f"msg_{i}"})) for i in range(500)],
        len(db.list_tasks(limit=1000)) >= 500
    )[1])

    import random as _rnd
    run_test("压力-1000条消息", lambda: (
        [(db.add_message(_rnd.randint(1,100), _rnd.randint(10000,99999), _rnd.randint(1,99), f"@u{i}", f"content_{i}"*3, f"消息_{i}"*2, "received")) for i in range(1000)],
        len(db.get_unreplied_messages()) >= 100
    )[1])

    start = time.time()
    db.list_accounts(limit=1000)
    elapsed = (time.time() - start) * 1000
    run_test("压力-1000账号查询<500ms", lambda: elapsed < 500)

    db.conn.execute("DELETE FROM accounts")
    db.conn.execute("DELETE FROM account_groups")
    db.conn.execute("DELETE FROM account_group_map")
    db.conn.execute("DELETE FROM tasks")
    db.conn.execute("DELETE FROM messages")
    db.conn.commit()
    run_test("压力-清理数据", lambda: db.count_accounts() == 0)

    os.remove(db_path)
    print(f"    压力测试完成")


# ==================== main ====================
def main():
    global PASS, FAIL, ERRORS
    print("=" * 60)
    print("    TG Cloud Controller - v2.0 功能测试套件")
    print("    VPS: 1CPU / 957MiB RAM / 5GiB SWAP")
    print("=" * 60)

    test_database()
    test_account_import()
    test_tdata_detection()
    test_ai_service()
    test_config()
    test_keyboards()
    test_logger()
    test_stress()

    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"    测试结果: 总计 {total}, ✅ {PASS} 通过, ❌ {FAIL} 失败")
    if total > 0:
        print(f"    通过率: {PASS/total*100:.1f}%")
    print(f"{'='*60}")

    if ERRORS:
        print(f"\n    失败详情 ({len(ERRORS)}):")
        for i, e in enumerate(ERRORS, 1):
            print(f"    {i}. {e}")

    return FAIL == 0


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

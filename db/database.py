import sqlite3
import os
import json
import threading
from datetime import datetime
from typing import Optional, Any
from utils.logger import setup_logger

logger = setup_logger(__name__)


class Database:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            session_path TEXT NOT NULL,
            group_id INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'active',
            twofa_password TEXT DEFAULT '',
            proxy TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS account_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS account_group_map (
            account_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (account_id, group_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES account_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            target_type TEXT NOT NULL DEFAULT 'accounts',
            target_ids TEXT NOT NULL DEFAULT '[]',
            params TEXT NOT NULL DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            progress TEXT DEFAULT '0/0',
            result TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL DEFAULT 0,
            sender_username TEXT DEFAULT '',
            content_raw TEXT DEFAULT '',
            content_zh TEXT DEFAULT '',
            direction TEXT DEFAULT 'received',
            replied INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            group_title TEXT DEFAULT '',
            user_id INTEGER NOT NULL,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(account_id, group_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        conn.commit()
        conn.close()
        logger.info("数据库初始化完成: %s", self.db_path)

    def add_account(self, name: str, phone: str = "", session_path: str = "",
                    group_id: Optional[int] = None, twofa_password: str = "",
                    metadata: dict = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO accounts (name, phone, session_path, group_id, twofa_password, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, phone, session_path, group_id, twofa_password,
             json.dumps(metadata or {}, ensure_ascii=False))
        )
        self.conn.commit()
        return cur.lastrowid

    def get_account(self, account_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        return dict(row) if row else None

    def get_account_by_phone(self, phone: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM accounts WHERE phone=?", (phone,)).fetchone()
        return dict(row) if row else None

    def list_accounts(self, group_id: Optional[int] = None, status: str = "active",
                      offset: int = 0, limit: int = 50) -> list[dict]:
        if group_id:
            rows = self.conn.execute(
                """SELECT a.* FROM accounts a
                   INNER JOIN account_group_map m ON a.id = m.account_id
                   WHERE m.group_id = ? AND a.status = ?
                   ORDER BY a.id LIMIT ? OFFSET ?""",
                (group_id, status, limit, offset)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM accounts WHERE status=? ORDER BY id LIMIT ? OFFSET ?",
                (status, limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_accounts(self, group_id: Optional[int] = None, status: str = "active") -> int:
        if group_id:
            row = self.conn.execute(
                """SELECT COUNT(*) as c FROM accounts a
                   INNER JOIN account_group_map m ON a.id = m.account_id
                   WHERE m.group_id = ? AND a.status = ?""",
                (group_id, status)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as c FROM accounts WHERE status=?",
                (status,)
            ).fetchone()
        return row["c"] if row else 0

    def list_ungrouped_accounts(self, status: str = "active",
                                offset: int = 0, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM accounts WHERE status=?
               AND id NOT IN (SELECT account_id FROM account_group_map)
               ORDER BY id LIMIT ? OFFSET ?""",
            (status, limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

    def count_ungrouped_accounts(self, status: str = "active") -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) as c FROM accounts WHERE status=?
               AND id NOT IN (SELECT account_id FROM account_group_map)""",
            (status,)
        ).fetchone()
        return row["c"] if row else 0

    def update_account(self, account_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [account_id]
        self.conn.execute(f"UPDATE accounts SET {fields}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
        self.conn.commit()

    def delete_account(self, account_id: int):
        self.conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self.conn.commit()

    def add_group(self, name: str, description: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO account_groups (name, description) VALUES (?, ?)",
            (name, description)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_group(self, group_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM account_groups WHERE id=?", (group_id,)).fetchone()
        return dict(row) if row else None

    def get_group_by_name(self, name: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM account_groups WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def list_groups(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT g.*, COUNT(m.account_id) as account_count
               FROM account_groups g
               LEFT JOIN account_group_map m ON g.id = m.group_id
               GROUP BY g.id ORDER BY g.id"""
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_group(self, group_id: int):
        self.conn.execute("DELETE FROM account_groups WHERE id=?", (group_id,))
        self.conn.commit()

    def assign_account_to_group(self, account_id: int, group_id: int):
        self.conn.execute(
            "INSERT OR IGNORE INTO account_group_map (account_id, group_id) VALUES (?, ?)",
            (account_id, group_id)
        )
        self.conn.commit()

    def remove_account_from_group(self, account_id: int, group_id: int):
        self.conn.execute(
            "DELETE FROM account_group_map WHERE account_id=? AND group_id=?",
            (account_id, group_id)
        )
        self.conn.commit()

    def get_account_groups(self, account_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT g.* FROM account_groups g
               INNER JOIN account_group_map m ON g.id = m.group_id
               WHERE m.account_id = ?""",
            (account_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def add_task(self, task_type: str, target_type: str, target_ids: list,
                 params: dict = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO tasks (task_type, target_type, target_ids, params)
               VALUES (?, ?, ?, ?)""",
            (task_type, target_type,
             json.dumps(target_ids, ensure_ascii=False),
             json.dumps(params or {}, ensure_ascii=False))
        )
        self.conn.commit()
        return cur.lastrowid

    def update_task(self, task_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [task_id]
        self.conn.execute(f"UPDATE tasks SET {fields}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
        self.conn.commit()

    def get_task(self, task_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, status: str = None, limit: int = 20) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_message(self, account_id: int, chat_id: int, sender_id: int = 0,
                    sender_username: str = "", content_raw: str = "",
                    content_zh: str = "", direction: str = "received") -> int:
        cur = self.conn.execute(
            """INSERT INTO messages (account_id, chat_id, sender_id, sender_username,
               content_raw, content_zh, direction)
               VALUES (?,?,?,?,?,?,?)""",
            (account_id, chat_id, sender_id, sender_username, content_raw, content_zh, direction)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_unreplied_messages(self, account_id: int = None) -> list[dict]:
        if account_id:
            rows = self.conn.execute(
                """SELECT * FROM messages WHERE replied=0 AND direction='received'
                   AND account_id=? ORDER BY created_at DESC""",
                (account_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM messages WHERE replied=0 AND direction='received'
                   ORDER BY created_at DESC LIMIT 100"""
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_replied(self, message_id: int):
        self.conn.execute("UPDATE messages SET replied=1 WHERE id=?", (message_id,))
        self.conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()

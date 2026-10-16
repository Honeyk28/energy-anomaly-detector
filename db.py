import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

DB_PATH = os.path.join(os.path.dirname(__file__), 'app.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                meter TEXT NOT NULL,
                date TEXT NOT NULL,
                kwh REAL NOT NULL,
                PRIMARY KEY (meter, date)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT CHECK (role IN ('admin', 'viewer')) NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ok INTEGER NOT NULL,
                at TEXT NOT NULL,
                ip TEXT
            )
        """)
        conn.commit()

class User(UserMixin):
    def __init__(self, id, username, display_name, role, password_hash, is_active, created_at, last_login=None):
        self.id = id
        self.username = username
        self.display_name = display_name
        self.role = role
        self.password_hash = password_hash
        self._is_active = bool(is_active)
        self.created_at = created_at
        self.last_login = last_login

    @property
    def is_active(self):
        return self._is_active

    @property
    def is_admin(self):
        return self.role == 'admin'

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'role': self.role,
            'is_active': int(self._is_active),
            'created_at': self.created_at,
            'last_login': self.last_login
        }

def get_user_by_id(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return User(
                id=row['id'],
                username=row['username'],
                display_name=row['display_name'],
                role=row['role'],
                password_hash=row['password_hash'],
                is_active=row['is_active'],
                created_at=row['created_at'],
                last_login=row['last_login']
            )
    return None

def get_user_by_username(username):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            return User(
                id=row['id'],
                username=row['username'],
                display_name=row['display_name'],
                role=row['role'],
                password_hash=row['password_hash'],
                is_active=row['is_active'],
                created_at=row['created_at'],
                last_login=row['last_login']
            )
    return None

def get_all_users():
    with get_db() as conn:
        rows = conn.execute("SELECT id, username, display_name, role, is_active, created_at, last_login FROM users ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

def create_user(username, display_name, role, password):
    if role not in ('admin', 'viewer'):
        raise ValueError("Role must be 'admin' or 'viewer'")
    pwd_hash = generate_password_hash(password, method='pbkdf2:sha256')
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, display_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (username.strip(), display_name.strip(), role, pwd_hash, now))
        conn.commit()
        return cursor.lastrowid

def update_user_status(user_id, is_active, requester_id):
    if user_id == requester_id and not is_active:
        raise ValueError("You cannot disable your own account.")
    
    with get_db() as conn:
        target = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise ValueError("User not found.")
        
        if target['role'] == 'admin' and target['is_active'] == 1 and not is_active:
            active_admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]
            if active_admins <= 1:
                raise ValueError("Cannot disable the last active administrator.")
        
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()

def update_user_password(user_id, new_password):
    pwd_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    with get_db() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
        conn.commit()

def delete_user(user_id, requester_id):
    if user_id == requester_id:
        raise ValueError("You cannot delete your own account.")
    
    with get_db() as conn:
        target = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise ValueError("User not found.")
        
        if target['role'] == 'admin' and target['is_active'] == 1:
            active_admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]
            if active_admins <= 1:
                raise ValueError("Cannot delete the last active administrator.")
        
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

def update_last_login(user_id):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))
        conn.commit()

def record_login_attempt(username, ok, ip):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute("INSERT INTO login_log (username, ok, at, ip) VALUES (?, ?, ?, ?)",
                     (username, 1 if ok else 0, now, ip))
        conn.commit()

def is_username_locked(username):
    """Basic throttle: 5 failed attempts per username in last 60 seconds -> lockout."""
    cutoff = (datetime.utcnow() - timedelta(seconds=60)).strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM login_log
            WHERE username = ? AND ok = 0 AND at >= ?
        """, (username, cutoff)).fetchone()
        return row[0] >= 5

def get_recent_logins(limit=20):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, username, ok, at, ip FROM login_log
            ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

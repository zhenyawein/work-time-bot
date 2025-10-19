import sqlite3
import json
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_name: str = "work_tracker.db"):
        # На сервере используем абсолютный путь
        if os.getenv("RAILWAY_STATIC_URL") or os.getenv("HEROKU_APP_NAME"):
            self.db_name = "/tmp/work_tracker.db"  # На Heroku/Railway
        else:
            self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()

                # ... создание таблиц ...

                conn.commit()
                print(f"✅ База данных инициализирована: {self.db_name}")
        except Exception as e:
            print(f"❌ Ошибка базы данных: {e}")

    # ... остальные методы без изменений ...import sqlite3


import json
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_name: str = "work_tracker.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            # Таблица для рабочих дней
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS work_days (
                    user_id INTEGER,
                    date TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    PRIMARY KEY (user_id, date)
                )
            """
            )

            # Таблица для выполненных действий
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS work_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date TEXT,
                    action_description TEXT,
                    created_at TEXT
                )
            """
            )

            conn.commit()

    def add_work_day(
        self, user_id: int, work_date: str, start_time: str, end_time: str
    ):
        """Добавление/обновление рабочего дня"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO work_days (user_id, date, start_time, end_time)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, work_date, start_time, end_time),
            )
            conn.commit()

    def add_work_task(self, user_id: int, work_date: str, action_description: str):
        """Добавление выполненного действия"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO work_actions (user_id, date, action_description, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, work_date, action_description, datetime.now().isoformat()),
            )
            conn.commit()

    def get_work_day(self, user_id: int, work_date: str) -> Optional[Dict]:
        """Получение данных рабочего дня"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM work_days WHERE user_id = ? AND date = ?
            """,
                (user_id, work_date),
            )
            result = cursor.fetchone()

            if result:
                return {
                    "user_id": result[0],
                    "date": result[1],
                    "start_time": result[2],
                    "end_time": result[3],
                }
            return None

    def get_work_tasks(self, user_id: int, work_date: str) -> List[str]:
        """Получение списка действий за день"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT action_description FROM work_actions 
                WHERE user_id = ? AND date = ?
                ORDER BY created_at
            """,
                (user_id, work_date),
            )
            return [row[0] for row in cursor.fetchall()]

    def get_work_period(self, user_id: int, start_date: str, end_date: str) -> Dict:
        """Получение данных за период"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            # Получаем рабочие дни
            cursor.execute(
                """
                SELECT date, start_time, end_time FROM work_days 
                WHERE user_id = ? AND date BETWEEN ? AND ?
                ORDER BY date
            """,
                (user_id, start_date, end_date),
            )
            work_days = cursor.fetchall()

            # Получаем действия
            cursor.execute(
                """
                SELECT date, action_description FROM work_actions 
                WHERE user_id = ? AND date BETWEEN ? AND ?
                ORDER BY date, created_at
            """,
                (user_id, start_date, end_date),
            )
            tasks = cursor.fetchall()

            return {"work_days": work_days, "tasks": tasks}

import os
import logging
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, Tuple, List
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler,
)

# Настройка логирования для Railway
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN не найден! Проверьте переменные окружения на Railway.")
    exit(1)

# Глобальные переменные для хранения выбранных дат
user_selections = {}

# ============================
# БАЗА ДАННЫХ
# ============================


class Database:
    def __init__(self, db_name: str = "work_tracker.db"):
        self.db_name = db_name
        print(f"🔄 Инициализация базы данных: {self.db_name}")
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        try:
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
                print(f"✅ База данных {self.db_name} создана/подключена")

        except Exception as e:
            print(f"❌ Ошибка при создании базы данных: {e}")

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

    def get_work_day(self, user_id: int, work_date: str):
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

    def get_work_tasks(self, user_id: int, work_date: str):
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

    def get_work_period(self, user_id: int, start_date: str, end_date: str):
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


# Инициализация базы данных
db = Database()


def format_date(date_str: str) -> str:
    """Форматирование даты в формат DD.MM.YYYY"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%d.%m.%Y")
    except ValueError:
        return date_str


def calculate_work_hours(start_time: str, end_time: str) -> Tuple[float, float]:
    """Расчет рабочих часов: фактически и с учетом обеда"""
    try:
        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")

        # Расчет фактических часов
        actual_hours = (end - start).total_seconds() / 3600

        # Расчет часов с учетом обеда (минус 1 час)
        work_hours_with_lunch = actual_hours - 1.0

        return max(0, actual_hours), max(0, work_hours_with_lunch)
    except ValueError:
        return 0, 0


# ============================
# ОСНОВНЫЕ КОМАНДЫ
# ============================


def start(update, context):
    """Команда /start"""
    user = update.message.from_user
    welcome_text = f"""
👋 Привет, {user.first_name}!

Я бот для учета рабочего времени и выполненных действий.

📋 Доступные команды:
/start - Начало работы
/add_action - Добавить выполненное действие
/report - Выгрузить отчет за период
/today - Показать сегодняшний день
/reset_today - Сбросить сегодняшний день (для тестирования)

🎯 Используйте кнопки ниже для учета рабочего времени!
    """

    keyboard = [
        [
            KeyboardButton("🟢 Начало рабочего дня"),
            KeyboardButton("🔴 Конец рабочего дня"),
        ],
        [KeyboardButton("📝 Добавить действие"), KeyboardButton("📊 Отчет")],
        [KeyboardButton("📅 Сегодня")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(welcome_text, reply_markup=reply_markup)


def start_work_day(update, context):
    """Обработка нажатия кнопки начала рабочего дня"""
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)
    current_time = datetime.now().strftime("%H:%M")

    # Получаем текущие данные дня
    work_day = db.get_work_day(user_id, today)

    if work_day and work_day["start_time"]:
        # Предлагаем перезаписать или посмотреть текущее
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Перезаписать время",
                    callback_data=f"overwrite_start_{current_time}",
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_overwrite")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text(
            f"⏰ Начало рабочего дня уже было установлено: {work_day['start_time']}\n"
            f"Хотите перезаписать на текущее время ({current_time})?",
            reply_markup=reply_markup,
        )
    else:
        # Сохраняем только время начала, конец оставляем пустым
        db.add_work_day(user_id, today, current_time, "")

        update.message.reply_text(
            f"🟢 Начало рабочего дня установлено!\n"
            f"📅 Дата: {today_formatted}\n"
            f"🕐 Время: {current_time}\n"
            f"Хорошего рабочего дня! 💼"
        )


def end_work_day(update, context):
    """Обработка нажатия кнопки окончания рабочего дня"""
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)
    current_time = datetime.now().strftime("%H:%M")

    # Получаем текущие данные дня
    work_day = db.get_work_day(user_id, today)

    if not work_day or not work_day["start_time"]:
        update.message.reply_text(
            "❌ Сначала нужно установить начало рабочего дня!\n"
            "Нажмите кнопку '🟢 Начало рабочего дня'"
        )
        return

    if work_day["end_time"]:
        # Предлагаем перезаписать или посмотреть текущее
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Перезаписать время",
                    callback_data=f"overwrite_end_{current_time}",
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_overwrite")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text(
            f"⏰ Конец рабочего дня уже был установлен: {work_day['end_time']}\n"
            f"Хотите перезаписать на текущее время ({current_time})?",
            reply_markup=reply_markup,
        )
        return

    # Сохраняем время окончания (начало берем из существующих данных)
    db.add_work_day(user_id, today, work_day["start_time"], current_time)

    # Расчет рабочих часов
    actual_hours, work_hours_with_lunch = calculate_work_hours(
        work_day["start_time"], current_time
    )

    update.message.reply_text(
        f"🔴 Конец рабочего дня установлен!\n"
        f"📅 Дата: {today_formatted}\n"
        f"🕐 Начало: {work_day['start_time']}\n"
        f"🕔 Конец: {current_time}\n"
        f"⏱ Фактически отработано: {actual_hours:.1f} часов\n"
        f"🍽 С учетом обеда: {work_hours_with_lunch:.1f} часов\n"
        f"Хорошего отдыха! 🌙"
    )


def reset_today(update, context):
    """Сброс сегодняшнего дня для тестирования"""
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)

    # Удаляем данные за сегодня
    conn = sqlite3.connect("work_tracker.db")
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM work_days WHERE user_id = ? AND date = ?", (user_id, today)
    )
    cursor.execute(
        "DELETE FROM work_actions WHERE user_id = ? AND date = ?", (user_id, today)
    )
    conn.commit()
    conn.close()

    update.message.reply_text(
        f"🔄 Данные за сегодня ({today_formatted}) сброшены!\n"
        f"Теперь можно заново установить начало и конец рабочего дня."
    )


def handle_overwrite_callback(update, context):
    """Обработка перезаписи времени"""
    query = update.callback_query
    query.answer()

    user_id = query.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)
    callback_data = query.data

    if callback_data == "cancel_overwrite":
        query.edit_message_text("❌ Операция отменена.")
        return

    elif callback_data.startswith("overwrite_start_"):
        current_time = callback_data.replace("overwrite_start_", "")
        # Перезаписываем время начала (конец оставляем пустым)
        work_day = db.get_work_day(user_id, today)
        db.add_work_day(user_id, today, current_time, "")

        query.edit_message_text(
            f"✅ Время начала перезаписано!\n"
            f"📅 Дата: {today_formatted}\n"
            f"🕐 Новое время: {current_time}"
        )

    elif callback_data.startswith("overwrite_end_"):
        current_time = callback_data.replace("overwrite_end_", "")
        # Перезаписываем время окончания
        work_day = db.get_work_day(user_id, today)
        if work_day and work_day["start_time"]:
            db.add_work_day(user_id, today, work_day["start_time"], current_time)

            # Расчет рабочих часов
            actual_hours, work_hours_with_lunch = calculate_work_hours(
                work_day["start_time"], current_time
            )

            query.edit_message_text(
                f"✅ Время окончания перезаписано!\n"
                f"📅 Дата: {today_formatted}\n"
                f"🕐 Начало: {work_day['start_time']}\n"
                f"🕔 Конец: {current_time}\n"
                f"⏱ Фактически отработано: {actual_hours:.1f} часов\n"
                f"🍽 С учетом обеда: {work_hours_with_lunch:.1f} часов"
            )


# ============================
# ДОБАВЛЕНИЕ ДЕЙСТВИЙ
# ============================


def add_action_start(update, context):
    """Начало добавления выполненного действия"""
    update.message.reply_text(
        "📝 *Опишите выполненное действие:*\n\n"
        "Например:\n"
        "• 'Монтаж электропроводки в квартире'\n"
        "• 'Установка розеток и выключателей'\n"
        "• 'Прокладка кабеля ВВГнг 3x2.5'\n"
        "• 'Подключение щитка освещения'\n"
        "• 'Замена электропроводки на кухне'",
        parse_mode="Markdown",
    )


def add_action_complete(update, context):
    """Добавление выполненного действия (обработка любого текстового сообщения)"""
    # Проверяем, что это не команда и не кнопка
    if update.message.text.startswith("/"):
        return

    # Проверяем, что это не нажатие на другие кнопки
    button_texts = [
        "🟢 Начало рабочего дня",
        "🔴 Конец рабочего дня",
        "📝 Добавить действие",
        "📊 Отчет",
        "📅 Сегодня",
    ]
    if update.message.text in button_texts:
        return

    action_description = update.message.text
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)

    # Сохраняем действие
    db.add_work_task(user_id, today, action_description)

    update.message.reply_text(
        f"✅ *Выполненное действие добавлено!*\n\n"
        f"📅 *Дата:* {today_formatted}\n"
        f"📝 *Действие:* {action_description}",
        parse_mode="Markdown",
    )


# ============================
# ИНФОРМАЦИЯ О СЕГОДНЯШНЕМ ДНЕ
# ============================


def today_info(update, context):
    """Информация о сегодняшнем дне"""
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)

    work_day = db.get_work_day(user_id, today)
    actions = db.get_work_tasks(user_id, today)

    response = [f"📅 *Сегодня:* {today_formatted}"]

    if work_day:
        if work_day["start_time"]:
            response.append(f"🟢 *Начало:* {work_day['start_time']}")
        else:
            response.append("❌ Начало дня не установлено")

        if work_day["end_time"] and work_day["end_time"] != work_day["start_time"]:
            response.append(f"🔴 *Конец:* {work_day['end_time']}")
            actual_hours, work_hours_with_lunch = calculate_work_hours(
                work_day["start_time"], work_day["end_time"]
            )
            response.append(f"⏱ *Фактически:* {actual_hours:.1f} часов")
            response.append(f"🍽 *С учетом обеда:* {work_hours_with_lunch:.1f} часов")
        else:
            response.append("❌ Конец дня не установлен")
    else:
        response.append("❌ Рабочий день не начат")

    if actions:
        response.append("\n✅ *Выполненные действия:*")
        for i, action in enumerate(actions, 1):
            response.append(f"  {i}. {action}")
    else:
        response.append("\n❌ Действия не добавлены")

    update.message.reply_text("\n".join(response), parse_mode="Markdown")


# ============================
# ОТЧЕТЫ
# ============================


def report_start(update, context):
    """Начало формирования отчета"""
    user_id = update.message.from_user.id

    # Инициализируем выбор пользователя
    user_selections[user_id] = {
        "start_date": None,
        "end_date": date.today().isoformat(),  # Конечная дата всегда сегодня
    }

    show_year_selection(update, "start")


def show_year_selection(update, date_type: str):
    """Показ выбора года"""
    current_year = datetime.now().year

    keyboard = []
    row = []
    for year in range(current_year - 1, current_year + 2):  # -1, текущий, +1
        row.append(
            InlineKeyboardButton(str(year), callback_data=f"year_{year}_{date_type}")
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="report_cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if isinstance(update, Update):
        update.message.reply_text(
            "📅 Выберите год для начальной даты отчета:", reply_markup=reply_markup
        )
    else:
        # Это callback query
        update.edit_message_text(
            "📅 Выберите год для начальной даты отчета:", reply_markup=reply_markup
        )


def handle_report_callback(update, context):
    """Обработка callback от inline кнопок"""
    query = update.callback_query
    query.answer()

    user_id = query.from_user.id
    callback_data = query.data

    if callback_data == "report_cancel":
        query.edit_message_text("❌ Формирование отчета отменено.")
        return

    elif callback_data.startswith("year_"):
        # Выбор года
        _, year, date_type = callback_data.split("_")
        show_month_selection(query, int(year), date_type)

    elif callback_data.startswith("month_"):
        # Выбор месяца
        _, year, month, date_type = callback_data.split("_")
        show_day_selection(query, int(year), int(month), date_type)

    elif callback_data.startswith("day_"):
        # Выбор дня - сразу формируем отчет
        _, year, month, day, date_type = callback_data.split("_")
        selected_date = f"{year}-{month:>02s}-{day:>02s}"

        if user_id not in user_selections:
            user_selections[user_id] = {}

        user_selections[user_id]["start_date"] = selected_date
        user_selections[user_id]["end_date"] = date.today().isoformat()

        generate_and_send_report(query, user_id)


def show_month_selection(query, year: int, date_type: str):
    """Показ выбора месяца"""
    months = [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]

    keyboard = []
    row = []
    for i, month in enumerate(months, 1):
        row.append(
            InlineKeyboardButton(
                month, callback_data=f"month_{year}_{i:02d}_{date_type}"
            )
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    "◀️ Назад к выбору года", callback_data="report_start"
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="report_cancel")],
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        f"📅 Выберите месяц для {year} года:", reply_markup=reply_markup
    )


def show_day_selection(query, year: int, month: int, date_type: str):
    """Показ выбора дня"""
    # Определяем количество дней в месяце
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year

    first_day = date(year, month, 1)
    last_day = date(next_year, next_month, 1) - timedelta(days=1)

    keyboard = []
    row = []

    # Добавляем дни
    for day in range(1, last_day.day + 1):
        row.append(
            InlineKeyboardButton(
                str(day), callback_data=f"day_{year}_{month:02d}_{day:02d}_{date_type}"
            )
        )
        if len(row) == 7:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    "◀️ Назад к выбору месяца", callback_data=f"year_{year}_{date_type}"
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="report_cancel")],
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    month_name = [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ][month - 1]

    query.edit_message_text(
        f"📅 Выберите день ({month_name} {year}):", reply_markup=reply_markup
    )


def generate_and_send_report(query, user_id: int):
    """Генерация и отправка отчета"""
    if user_id not in user_selections or not user_selections[user_id].get("start_date"):
        query.edit_message_text("❌ Ошибка: дата не выбрана")
        return

    start_date = user_selections[user_id]["start_date"]
    end_date = user_selections[user_id]["end_date"]

    # Получаем данные за период
    period_data = db.get_work_period(user_id, start_date, end_date)

    # Формируем отчет
    report = generate_report(period_data, start_date, end_date)

    # Очищаем выбор пользователя
    if user_id in user_selections:
        del user_selections[user_id]

    query.edit_message_text(report)


def generate_report(period_data: Dict, start_date: str, end_date: str) -> str:
    """Генерация текстового отчета"""
    if not period_data["work_days"]:
        return f"📊 За период с {format_date(start_date)} по {format_date(end_date)} данные не найдены."

    report_lines = [
        f"📊 *ОТЧЕТ за период:* {format_date(start_date)} - {format_date(end_date)}\n"
    ]
    total_actual_hours = 0
    total_work_hours = 0
    days_with_data = 0

    # Группируем действия по датам
    actions_by_date = {}
    for action_date, action_desc in period_data["tasks"]:
        if action_date not in actions_by_date:
            actions_by_date[action_date] = []
        actions_by_date[action_date].append(action_desc)

    # Формируем отчет по дням
    for work_day in period_data["work_days"]:
        day_date, start_time, end_time = work_day

        # Проверяем, что есть и начало и конец дня
        if start_time and end_time and start_time != end_time:
            actual_hours, work_hours_with_lunch = calculate_work_hours(
                start_time, end_time
            )
            total_actual_hours += actual_hours
            total_work_hours += work_hours_with_lunch
            days_with_data += 1

            report_lines.append(f"\n📅 *{format_date(day_date)}*")
            report_lines.append(f"🕐 Время: {start_time} - {end_time}")
            report_lines.append(f"⏱ Фактически: {actual_hours:.1f} ч")
            report_lines.append(f"🍽 С учетом обеда: {work_hours_with_lunch:.1f} ч")

            # Добавляем выполненные действия за этот день
            if day_date in actions_by_date:
                report_lines.append("✅ *Выполненные действия:*")
                for i, action in enumerate(actions_by_date[day_date], 1):
                    report_lines.append(f"  {i}. {action}")
            else:
                report_lines.append("❌ Действия не добавлены")

    if days_with_data == 0:
        return f"📊 За период с {format_date(start_date)} по {format_date(end_date)} нет полных данных о рабочих днях."

    report_lines.append(f"\n📈 *ИТОГО за {days_with_data} дней:*")
    report_lines.append(f"⏱ Фактически: {total_actual_hours:.1f} часов")
    report_lines.append(f"🍽 С учетом обеда: {total_work_hours:.1f} часов")

    return "\n".join(report_lines)


# ============================
# ЗАПУСК БОТА
# ============================


def main():
    """Запуск бота на Railway"""
    try:
        # Создаем Updater с токеном
        updater = Updater(BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        # Добавляем обработчики кнопок
        dispatcher.add_handler(
            MessageHandler(Filters.regex("🟢 Начало рабочего дня"), start_work_day)
        )
        dispatcher.add_handler(
            MessageHandler(Filters.regex("🔴 Конец рабочего дня"), end_work_day)
        )
        dispatcher.add_handler(MessageHandler(Filters.regex("📊 Отчет"), report_start))
        dispatcher.add_handler(
            MessageHandler(Filters.regex("📝 Добавить действие"), add_action_start)
        )
        dispatcher.add_handler(MessageHandler(Filters.regex("📅 Сегодня"), today_info))

        # Обработчик для добавления действий (любое текстовое сообщение)
        dispatcher.add_handler(
            MessageHandler(Filters.text & ~Filters.command, add_action_complete)
        )

        # Обработчики callback для перезаписи времени
        dispatcher.add_handler(
            CallbackQueryHandler(
                handle_overwrite_callback, pattern="^overwrite_|^cancel_overwrite"
            )
        )

        # Обработчик inline кнопок для отчетов
        dispatcher.add_handler(
            CallbackQueryHandler(
                handle_report_callback, pattern="^report_|^year_|^month_|^day_|^quick_"
            )
        )

        # Добавляем обработчики команд
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("today", today_info))
        dispatcher.add_handler(CommandHandler("report", report_start))
        dispatcher.add_handler(CommandHandler("reset_today", reset_today))
        dispatcher.add_handler(CommandHandler("add_action", add_action_start))

        print("🚀 Бот запускается на Railway...")

        # Запускаем бота
        updater.start_polling()
        print("✅ Бот успешно запущен!")
        updater.idle()

    except Exception as e:
        logging.error(f"❌ Ошибка при запуске бота: {e}")


if __name__ == "__main__":
    main()

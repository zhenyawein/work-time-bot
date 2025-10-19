import os
import logging
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
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from database import Database

# Настройка логирования для Railway
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN не найден! Проверьте переменные окружения на Railway.")
    exit(1)

# Инициализация базы данных
db = Database()

import os
import logging
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
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from dotenv import load_dotenv
from database import Database

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Инициализация базы данных
db = Database()

# Глобальные переменные для хранения выбранных дат
user_selections = {}


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def start_work_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        await update.message.reply_text(
            f"⏰ Начало рабочего дня уже было установлено: {work_day['start_time']}\n"
            f"Хотите перезаписать на текущее время ({current_time})?",
            reply_markup=reply_markup,
        )
    else:
        # Сохраняем только время начала, конец оставляем пустым
        db.add_work_day(user_id, today, current_time, "")

        await update.message.reply_text(
            f"🟢 Начало рабочего дня установлено!\n"
            f"📅 Дата: {today_formatted}\n"
            f"🕐 Время: {current_time}\n"
            f"Хорошего рабочего дня! 💼"
        )


async def end_work_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопки окончания рабочего дня"""
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)
    current_time = datetime.now().strftime("%H:%M")

    # Получаем текущие данные дня
    work_day = db.get_work_day(user_id, today)

    if not work_day or not work_day["start_time"]:
        await update.message.reply_text(
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

        await update.message.reply_text(
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

    await update.message.reply_text(
        f"🔴 Конец рабочего дня установлен!\n"
        f"📅 Дата: {today_formatted}\n"
        f"🕐 Начало: {work_day['start_time']}\n"
        f"🕔 Конец: {current_time}\n"
        f"⏱ Фактически отработано: {actual_hours:.1f} часов\n"
        f"🍽 С учетом обеда: {work_hours_with_lunch:.1f} часов\n"
        f"Хорошего отдыха! 🌙"
    )


async def reset_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс сегодняшнего дня для тестирования"""
    user_id = update.message.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)

    # Удаляем данные за сегодня
    import sqlite3

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

    await update.message.reply_text(
        f"🔄 Данные за сегодня ({today_formatted}) сброшены!\n"
        f"Теперь можно заново установить начало и конец рабочего дня."
    )


async def handle_overwrite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка перезаписи времени"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    today = date.today().isoformat()
    today_formatted = format_date(today)
    callback_data = query.data

    if callback_data == "cancel_overwrite":
        await query.edit_message_text("❌ Операция отменена.")
        return

    elif callback_data.startswith("overwrite_start_"):
        current_time = callback_data.replace("overwrite_start_", "")
        # Перезаписываем время начала (конец оставляем пустым)
        work_day = db.get_work_day(user_id, today)
        db.add_work_day(user_id, today, current_time, "")

        await query.edit_message_text(
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

            await query.edit_message_text(
                f"✅ Время окончания перезаписано!\n"
                f"📅 Дата: {today_formatted}\n"
                f"🕐 Начало: {work_day['start_time']}\n"
                f"🕔 Конец: {current_time}\n"
                f"⏱ Фактически отработано: {actual_hours:.1f} часов\n"
                f"🍽 С учетом обеда: {work_hours_with_lunch:.1f} часов"
            )


# ============================
# ПРОСТОЕ ДОБАВЛЕНИЕ ДЕЙСТВИЙ
# ============================


async def add_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления выполненного действия"""
    await update.message.reply_text(
        "📝 *Опишите выполненное действие:*\n\n"
        "Например:\n"
        "• 'Монтаж электропроводки в квартире'\n"
        "• 'Установка розеток и выключателей'\n"
        "• 'Прокладка кабеля ВВГнг 3x2.5'\n"
        "• 'Подключение щитка освещения'\n"
        "• 'Замена электропроводки на кухне'",
        parse_mode="Markdown",
    )


async def add_action_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await update.message.reply_text(
        f"✅ *Выполненное действие добавлено!*\n\n"
        f"📅 *Дата:* {today_formatted}\n"
        f"📝 *Действие:* {action_description}",
        parse_mode="Markdown",
    )


# ============================
# ИНФОРМАЦИЯ О СЕГОДНЯШНЕМ ДНЕ
# ============================


async def today_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await update.message.reply_text("\n".join(response), parse_mode="Markdown")


# ============================
# УПРОЩЕННЫЙ ВЫБОР ДАТЫ ДЛЯ ОТЧЕТА
# ============================


async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало формирования отчета"""
    user_id = update.message.from_user.id

    # Инициализируем выбор пользователя
    user_selections[user_id] = {
        "start_date": None,
        "end_date": date.today().isoformat(),  # Конечная дата всегда сегодня
    }

    await show_year_selection(update, "start")


async def show_year_selection(update, date_type: str):
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
        await update.message.reply_text(
            "📅 Выберите год для начальной даты отчета:", reply_markup=reply_markup
        )
    else:
        # Это callback query
        await update.edit_message_text(
            "📅 Выберите год для начальной даты отчета:", reply_markup=reply_markup
        )


async def handle_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback от inline кнопок"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback_data = query.data

    if callback_data == "report_cancel":
        await query.edit_message_text("❌ Формирование отчета отменено.")
        return

    elif callback_data.startswith("year_"):
        # Выбор года
        _, year, date_type = callback_data.split("_")
        await show_month_selection(query, int(year), date_type)

    elif callback_data.startswith("month_"):
        # Выбор месяца
        _, year, month, date_type = callback_data.split("_")
        await show_day_selection(query, int(year), int(month), date_type)

    elif callback_data.startswith("day_"):
        # Выбор дня - сразу формируем отчет
        _, year, month, day, date_type = callback_data.split("_")
        selected_date = f"{year}-{month:>02s}-{day:>02s}"

        if user_id not in user_selections:
            user_selections[user_id] = {}

        user_selections[user_id]["start_date"] = selected_date
        user_selections[user_id]["end_date"] = date.today().isoformat()

        await generate_and_send_report(query, user_id)


async def show_month_selection(query, year: int, date_type: str):
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
    await query.edit_message_text(
        f"📅 Выберите месяц для {year} года:", reply_markup=reply_markup
    )


async def show_day_selection(query, year: int, month: int, date_type: str):
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

    await query.edit_message_text(
        f"📅 Выберите день ({month_name} {year}):", reply_markup=reply_markup
    )


async def generate_and_send_report(query, user_id: int):
    """Генерация и отправка отчета"""
    if user_id not in user_selections or not user_selections[user_id].get("start_date"):
        await query.edit_message_text("❌ Ошибка: дата не выбрана")
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

    await query.edit_message_text(report)


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


def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики кнопок
    application.add_handler(
        MessageHandler(filters.Regex("🟢 Начало рабочего дня"), start_work_day)
    )
    application.add_handler(
        MessageHandler(filters.Regex("🔴 Конец рабочего дня"), end_work_day)
    )
    application.add_handler(MessageHandler(filters.Regex("📊 Отчет"), report_start))
    application.add_handler(
        MessageHandler(filters.Regex("📝 Добавить действие"), add_action_start)
    )
    application.add_handler(MessageHandler(filters.Regex("📅 Сегодня"), today_info))

    # Обработчик для добавления действий (любое текстовое сообщение)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, add_action_complete)
    )

    # Обработчики callback для перезаписи времени
    application.add_handler(
        CallbackQueryHandler(
            handle_overwrite_callback, pattern="^overwrite_|^cancel_overwrite"
        )
    )

    # Обработчик inline кнопок для отчетов
    application.add_handler(
        CallbackQueryHandler(
            handle_report_callback, pattern="^report_|^year_|^month_|^day_|^quick_"
        )
    )

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("today", today_info))
    application.add_handler(CommandHandler("report", report_start))
    application.add_handler(CommandHandler("reset_today", reset_today))
    application.add_handler(CommandHandler("add_action", add_action_start))

    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()


def main():
    """Запуск бота на Railway"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Добавьте все ваши обработчики как в оригинальном коде
        application.add_handler(
            MessageHandler(filters.Regex("🟢 Начало рабочего дня"), start_work_day)
        )
        application.add_handler(
            MessageHandler(filters.Regex("🔴 Конец рабочего дня"), end_work_day)
        )
        application.add_handler(MessageHandler(filters.Regex("📊 Отчет"), report_start))
        application.add_handler(
            MessageHandler(filters.Regex("📝 Добавить действие"), add_action_start)
        )
        application.add_handler(MessageHandler(filters.Regex("📅 Сегодня"), today_info))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_action_complete)
        )
        application.add_handler(
            CallbackQueryHandler(
                handle_overwrite_callback, pattern="^overwrite_|^cancel_overwrite"
            )
        )
        application.add_handler(
            CallbackQueryHandler(
                handle_report_callback, pattern="^report_|^year_|^month_|^day_|^quick_"
            )
        )
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("today", today_info))
        application.add_handler(CommandHandler("report", report_start))
        application.add_handler(CommandHandler("reset_today", reset_today))
        application.add_handler(CommandHandler("add_action", add_action_start))

        print("🚀 Бот запускается на Railway...")

        # На Railway используем polling
        application.run_polling()

    except Exception as e:
        logging.error(f"❌ Ошибка при запуске бота: {e}")
        # Railway автоматически перезапустит процесс


if __name__ == "__main__":
    main()

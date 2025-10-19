FROM python:3.11-alpine

# Устанавливаем SQLite и другие системные зависимости
RUN apk add --no-cache sqlite-dev gcc musl-dev

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем базу данных и запускаем бота
CMD python -c "import sqlite3; conn = sqlite3.connect('work_time.db'); conn.close()" && python bot.py

FROM python:3.12-slim

# Не пишем .pyc, не буферизуем stdout (логи сразу видны в docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — лучше кэшируется при изменении кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код (все модули бота)
COPY *.py ./

# Данные (voice_data.json) храним на volume
ENV DATA_FILE=/data/voice_data.json
RUN mkdir -p /data && \
    useradd --create-home --uid 1000 appuser && \
    chown -R appuser:appuser /app /data
USER appuser

CMD ["python", "bot.py"]

FROM node:20-slim

ENV NODE_ENV=production
WORKDIR /app

# Сначала зависимости — лучше кэшируется при изменении кода
COPY package.json ./
RUN npm install --omit=dev

# Код (все модули бота)
COPY *.js ./

# Данные (voice_data.json) храним на volume
ENV DATA_FILE=/data/voice_data.json
RUN mkdir -p /data && \
    useradd --create-home --uid 1000 appuser && \
    chown -R appuser:appuser /app /data
USER appuser

CMD ["node", "bot.js"]

FROM node:20-slim

ENV NODE_ENV=production
WORKDIR /app

# Сначала зависимости — лучше кэшируется при изменении кода
COPY package.json ./
RUN npm install --omit=dev

# Код (все модули бота)
COPY *.js ./

# Данные (voice_data.json) храним на volume.
# В образе node:20 уже есть непривилегированный пользователь `node` (UID 1000).
ENV DATA_FILE=/data/voice_data.json
RUN mkdir -p /data && chown -R node:node /app /data
USER node

CMD ["node", "bot.js"]

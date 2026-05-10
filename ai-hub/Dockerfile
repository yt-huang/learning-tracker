FROM python:3.12-alpine

WORKDIR /app
COPY app /app/app
ENV PORT=8020
ENV DB_PATH=/data/ai_hub.db
EXPOSE 8020
VOLUME ["/data"]
CMD ["python3", "-m", "app.main"]

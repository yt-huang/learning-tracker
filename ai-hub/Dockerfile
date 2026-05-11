FROM python:3.12-alpine

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app /app/app
ENV PORT=8020 \
    DB_ENGINE=mysql \
    DB_HOST=mysql \
    DB_PORT=3306 \
    DB_NAME=ai_hub \
    DB_USER=ai_hub \
    DB_PASSWORD=ai_hub_password
EXPOSE 8020
CMD ["python3", "-m", "app.main"]

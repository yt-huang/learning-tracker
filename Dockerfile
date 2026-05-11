FROM python:3.12-alpine
RUN apk add --no-cache build-base libffi-dev openssl-dev && pip install pymysql cryptography && apk del build-base libffi-dev openssl-dev
WORKDIR /app
COPY . /app
EXPOSE 8010
ENV PORT=8010
CMD ["python3", "server/server.py"]

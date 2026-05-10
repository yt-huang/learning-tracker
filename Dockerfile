FROM python:3.12-alpine
RUN pip install pymysql
WORKDIR /app
COPY . /app
EXPOSE 8010
ENV PORT=8010
CMD ["python3", "server/server.py"]

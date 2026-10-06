# Build context = ROOT del repo:  docker build -f api/Dockerfile .
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY *.py ./
COPY api ./api
EXPOSE 8080
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1

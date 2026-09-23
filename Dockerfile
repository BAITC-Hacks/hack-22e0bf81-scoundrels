FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements.txt
COPY backend/router/requirements.txt backend/router/requirements.txt
COPY backend/platform/requirements.txt backend/platform/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.platform.app:app", "--host", "0.0.0.0", "--port", "8000"]

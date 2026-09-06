FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create volume mounts for persistent data and logs
VOLUME ["/app/data", "/app/logs"]

EXPOSE 5050

CMD ["python", "main.py"]

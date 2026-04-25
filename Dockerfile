FROM mcr.microsoft.com/playwright/python:v1.49.0-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

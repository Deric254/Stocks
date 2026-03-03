FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend source files
COPY app.py .
COPY services/ ./services/
COPY utils/ ./utils/

# Create data directory — CSVs will be written here at runtime
RUN mkdir -p data

# Copy seed data files (empty CSVs + config)
COPY data/ ./data/

# Hugging Face Spaces expects port 7860
EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

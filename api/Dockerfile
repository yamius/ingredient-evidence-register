# Read-only API for the Vallydia Ingredient-Evidence Register.
# Serves the generated dataset from memory — no database, no writes.
FROM python:3.12-slim

WORKDIR /app

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# The dataset the API serves. Copied in so the image is self-contained.
COPY data /app/data
COPY api /app/api

EXPOSE 8000
# CORS is open for read; the service is stateless and safe to scale horizontally.
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]

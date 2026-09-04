FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=7860
EXPOSE 7860
CMD ["python", "server.py"]
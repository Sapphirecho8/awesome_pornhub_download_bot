FROM python:3.11-slim

# System deps: ffmpeg for yt-dlp to merge streams
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY bot_phdl.py /app/

# Create expected shared dir (also provided via volume in compose)
RUN mkdir -p /var/lib/telegram-bot-api/uploads

CMD ["python", "-u", "/app/bot_phdl.py"]


FROM python:alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
COPY VERSION /app/VERSION

RUN mkdir -p /data
ENV DATA_DIR=/data

EXPOSE 8080

# Threads let task streams (SSE) stay open without blocking the other requests.
CMD ["gunicorn", "--worker-class", "gthread", "--threads", "16", "--timeout", "0", "-b", "0.0.0.0:8080", "app:app"]
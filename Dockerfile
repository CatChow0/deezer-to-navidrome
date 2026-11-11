# A fixed Python: the requirements below were tested with it (python:alpine
# moved to each new Python on its own).
FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Decodes audio for the tempo analysis. The link is the name the Python binding looks for.
# su-exec: the switch to PUID / PGID (docker-entrypoint.sh).
RUN apk add --no-cache libsndfile su-exec && ln -s "$(ls /usr/lib/libsndfile.so.* | head -1)" /usr/lib/libsndfile.so

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN chmod +x /app/docker-entrypoint.sh

RUN mkdir -p /data
ENV DATA_DIR=/data

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Threads let task streams (SSE) stay open without blocking the other requests.
CMD ["gunicorn", "--worker-class", "gthread", "--threads", "16", "--timeout", "0", "-b", "0.0.0.0:8080", "app:app"]

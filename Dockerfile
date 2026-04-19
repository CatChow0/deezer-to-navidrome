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

CMD ["gunicorn", "--timeout", "0", "-b", "0.0.0.0:8080", "app:app"]
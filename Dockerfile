FROM python:3.11-slim

WORKDIR /app

COPY requirements-flask.txt .
RUN pip install --no-cache-dir -r requirements-flask.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]

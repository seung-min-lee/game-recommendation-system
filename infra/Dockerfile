FROM python:3.11-slim

WORKDIR /app

COPY infra/requirements-flask.txt .
RUN pip install --no-cache-dir -r requirements-flask.txt

COPY services/ services/
COPY ml/ ml/
COPY data/ data/
COPY config/ config/
COPY infra/app.py infra/app.py

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "infra.app:app"]

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway/Render inject $PORT at runtime; default 8000 for local docker run.
ENV PORT=8000
EXPOSE 8000

CMD uvicorn skuforge.api:app --host 0.0.0.0 --port ${PORT}

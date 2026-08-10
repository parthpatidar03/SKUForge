FROM python:3.12-slim

# python:3.12-slim's Debian base does not always ship an up-to-date CA bundle,
# which fails every outbound HTTPS call silently (httpx raises inside
# cache.fetch()'s except block, so it just looks like every source is
# unreachable). Scout/Extractor hit dozens of external hosts, so this bites
# hard here specifically.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway/Render inject $PORT at runtime; default 8000 for local docker run.
ENV PORT=8000
EXPOSE 8000

CMD uvicorn skuforge.api:app --host 0.0.0.0 --port ${PORT}

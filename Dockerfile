# BFF do dashboard Akeel — imagem pra deploy no Easypanel.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Dependências primeiro: só reinstala quando requirements.txt muda.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Sem root: o processo não precisa escrever em lugar nenhum.
RUN useradd --create-home --uid 10001 akdash && chown -R akdash:akdash /app
USER akdash

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f\"http://127.0.0.1:{os.getenv('PORT','8000')}/saude\").read()"

# Um worker só: o cache de métricas/pessoas é em memória do processo —
# vários workers dariam respostas com idades diferentes pro mesmo endpoint.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

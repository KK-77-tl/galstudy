ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
COPY backend/requirements-alipay.txt backend/requirements-alipay.txt
RUN python -m pip install --no-cache-dir --upgrade pip==26.3
RUN pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-alipay.txt
COPY backend backend
COPY ["frontend/public/assets/shiori.png", "frontend/public/assets/haruka.png", "frontend/public/assets/rin.png", "backend/demo_assets/"]
RUN useradd --create-home app && mkdir -p data && chown app:app data
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# 多阶段构建，减小镜像体积
FROM python:3.11-slim as builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY README.md ./
COPY src ./src
RUN pip install --no-cache-dir wheel && pip wheel --no-deps -w /wheels .

FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    APP_ENV=production \
    CREWAI_TELEMETRY_DISABLED=true \
    OTEL_SDK_DISABLED=true \
    CREWAI_TESTING=true

# 非 root 用户
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/bash app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY src ./src
COPY pyproject.toml ./

RUN chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

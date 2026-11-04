FROM python:3.12-slim
WORKDIR /app

# Runtime deps only (tests excluded).
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi==0.115.6 "uvicorn[standard]==0.34.0" pyjwt==2.10.1 bcrypt==4.2.1 asyncpg==0.30.0

COPY app ./app

# Run as a non-root user.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser /app
USER appuser

ENV API_HOST=0.0.0.0 API_PORT=8080 APP_ENV=production
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

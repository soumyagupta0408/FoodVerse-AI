FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt
# Heavy ML stack (CPU wheels). Build with --build-arg WITH_ML=false for a small API-only image.
ARG WITH_ML=true
RUN if [ "$WITH_ML" = "true" ]; then pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu; fi
COPY . .
RUN useradd -m app && mkdir -p /app/media /app/models /home/app/.cache && chown -R app /app /home/app
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

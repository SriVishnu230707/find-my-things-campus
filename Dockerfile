FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/campus
RUN groupadd --gid 10001 campus && useradd --uid 10001 --gid campus --no-create-home campus
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --requirement /tmp/requirements.lock
COPY backend ./backend
RUN pip install --no-deps -e ./backend && mkdir -p backend/data && chown -R campus:campus /srv/campus
USER campus
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]

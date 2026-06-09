FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/agentlab

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

EXPOSE 8000

# python-based healthcheck: curl is not present in slim images
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

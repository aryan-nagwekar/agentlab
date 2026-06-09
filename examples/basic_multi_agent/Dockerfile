# Demo seeder image. Build context = repository root:
#   docker compose --profile demo run --rm seed
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY packages/sdk-python ./sdk
RUN pip install ./sdk

COPY examples/basic_multi_agent ./demo

CMD ["python", "demo/run_demo.py", "--fast"]

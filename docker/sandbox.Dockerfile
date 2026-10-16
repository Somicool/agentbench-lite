# Image used by AGENTBENCH_EXECUTION_MODE=docker: one throwaway container per test run.
# It only needs Python and pytest; candidate code gets no network and a read-only root fs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install pytest==9.1.1 \
    && useradd --uid 10002 --no-create-home --shell /usr/sbin/nologin sandbox

USER sandbox
WORKDIR /work

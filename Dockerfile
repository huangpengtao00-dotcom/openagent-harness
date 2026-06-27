FROM python:3.12-slim

WORKDIR /harness
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/harness/src
CMD ["python", "-m", "openagent_harness.cli", "--help"]

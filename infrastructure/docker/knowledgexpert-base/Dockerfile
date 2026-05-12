FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

# Install minimal system deps needed by Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from repo root and install them
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create a work dir that other images can use as their runtime CWD
RUN mkdir -p /work

CMD ["/bin/sh", "-c", "echo knowledgexpert-base ready && sleep infinity"]

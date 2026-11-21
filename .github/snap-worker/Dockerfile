FROM python:3.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    HOME=/tmp

COPY .github/environments/e85-snap-python39-requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt

COPY tools/snap_worker.py /opt/ae32c/snap_worker.py
WORKDIR /opt/ae32c
USER 65534:65534
ENTRYPOINT ["python", "-I", "-B", "/opt/ae32c/snap_worker.py"]

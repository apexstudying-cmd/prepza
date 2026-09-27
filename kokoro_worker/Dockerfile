FROM ghcr.io/remsky/kokoro-fastapi-gpu:v0.8.0

USER root

RUN pip install --no-cache-dir \
    boto3==1.43.101 \
    fastapi==0.116.1 \
    pydub==0.25.1 \
    requests==2.34.2 \
    uvicorn==0.35.0

COPY kokoro_worker/worker.py /opt/prepza/worker.py

ENV WEB_CONCURRENCY=1 \
    USE_GPU=true \
    DEVICE_TYPE=cuda \
    PYTHONUNBUFFERED=1

COPY kokoro_worker/start.sh /opt/prepza/start.sh
RUN chmod +x /opt/prepza/start.sh

EXPOSE 8080

CMD ["/opt/prepza/start.sh"]

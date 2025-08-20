FROM python:3.12-slim
LABEL org.opencontainers.image.title="cognis-churnlens"
LABEL org.opencontainers.image.source="https://github.com/cognis-digital/churnlens"
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
ENTRYPOINT ["churnlens"]

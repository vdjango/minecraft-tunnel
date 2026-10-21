FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BUGGCRAFT_FIXED_PORTS=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 node && useradd --uid 10001 --gid node --no-create-home node \
    && mkdir /data && chown node:node /data
COPY --chown=node:node src ./src
COPY PROTOCOL_STANDARD.md ./
USER node
EXPOSE 3333/tcp 3333/udp 18443/tcp
ENTRYPOINT ["python", "src/main.py"]
CMD ["--directory", "/data"]

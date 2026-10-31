FROM python:3.15-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/catalog/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY services/catalog/app.py services/catalog/agenda_api.py services/catalog/inbox_api.py services/catalog/volume_api.py /app/
COPY deploy/scripts/setup-media-tree.sh /app/setup-media-tree.sh
RUN chmod +x /app/setup-media-tree.sh
ENV MEDIA_ROOT=/media
ENV CATALOG_PORT=30127
EXPOSE 30127
CMD ["python", "-u", "/app/app.py"]

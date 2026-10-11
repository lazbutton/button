FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends samba samba-vfs-modules python3 \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/share/apply_share.py /apply_share.py
COPY deploy/share/entrypoint.sh /entrypoint.sh
COPY deploy/scripts/refresh_volume.py /refresh_volume.py
RUN chmod +x /entrypoint.sh

ENV MEDIA_ROOT=/media \
    SHARE_PRIVATE=/share-private \
    PYTHONUNBUFFERED=1

WORKDIR /
ENTRYPOINT ["/entrypoint.sh"]

FROM debian:bookworm-slim
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends icecast2 media-types \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/icecast2 \
    && chown -R icecast2:icecast /var/log/icecast2 /etc/icecast2
COPY icecast.xml /etc/icecast2/icecast.xml.template
COPY docker-entrypoint.sh /docker-entrypoint-icecast.sh
RUN chmod +x /docker-entrypoint-icecast.sh \
    && chown icecast2:icecast /etc/icecast2/icecast.xml.template
EXPOSE 8000
USER icecast2
ENTRYPOINT ["/docker-entrypoint-icecast.sh"]

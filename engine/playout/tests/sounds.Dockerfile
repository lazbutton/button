# The sounds of the antenna bench: Python writes them, lame encodes them. The
# music of a station is mostly MP3, and the stall this bench listens for only
# showed with MP3 titles.
FROM python:3.13-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends lame \
    && rm -rf /var/lib/apt/lists/*

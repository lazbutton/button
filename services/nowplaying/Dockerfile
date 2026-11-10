FROM python:3.13-slim-bookworm
WORKDIR /app
COPY nowplaying.py /app/nowplaying.py
ENV RT_NOWPLAYING_PORT=6820
ENV RT_NOWPLAYING_FILE=/data/now.json
EXPOSE 6820
VOLUME /data
CMD ["python", "/app/nowplaying.py"]

FROM mcr.microsoft.com/playwright:v1.55.0-noble
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg xvfb xdotool pulseaudio pulseaudio-utils espeak-ng fonts-dejavu-core curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY . .
ENV PORT=10000
ENV DISPLAY=:99
ENV PULSE_SERVER=unix:/tmp/pulse/native
ENV STREAM_WIDTH=720
ENV STREAM_HEIGHT=1280
ENV STREAM_FPS=30
RUN chmod +x /app/start-cloud.sh
CMD ["/app/start-cloud.sh"]

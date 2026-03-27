FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/venv/bin:$PATH

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        libexpat1 \
        default-jdk-headless && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv

WORKDIR /app
COPY ./requirements.txt /app/requirements.txt

RUN pip install wheel
RUN pip install -r requirements.txt

# move files to dir
COPY . /app

RUN chmod +x /app/NoiseModelling/wps_scripts/gradlew && \
    cd /app/NoiseModelling/wps_scripts && \
    ./gradlew installDist --no-daemon

CMD ["bash", "entrypoint.sh"]

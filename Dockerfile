FROM ubuntu

# Noise module needs java
RUN apt-get update
RUN apt-get install -y java-common
RUN apt install -y default-jre
RUN apt install -y openjdk-8-jre-headless


# get python3 for ubuntu
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    rm -rf /var/lib/apt/lists/*

RUN add-apt-repository -y ppa:deadsnakes \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.11-venv \
    && apt-get clean 

RUN python3.11 -m venv /venv
ENV PATH=/venv/bin:$PATH

# move files to dir
COPY . /app
WORKDIR /app

RUN pip install wheel
RUN pip install -r requirements.txt

CMD ["bash", "entrypoint.sh"]

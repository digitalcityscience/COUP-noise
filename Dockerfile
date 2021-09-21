FROM python:3.8

LABEL org.opencontainers.image.authors="vinh-ngu@hotmail.com"

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt
RUN pip install -r noise_analysis/requirements.txt

# TODO enable cors for entrypoint sh
CMD ["bash", "entrypoint.sh"]

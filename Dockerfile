FROM python:3.8
LABEL maintainer="Secunity LTD. (support@secunity.io)"

RUN apt update && apt install -y git wget ca-certificates nano

WORKDIR /app
RUN git clone https://github.com/secunity/onpremagent.git .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /etc/secunity
RUN mkdir -p /var/log/secunity

ENTRYPOINT ["python", "/app/bin/start.py", "--program", "stats_fetcher"]

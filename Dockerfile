FROM python:3.10

ENV PYTHON_PIP_VERSION 20.1
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc mono-mcs golang-go \
    default-jre default-jdk nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip==${PYTHON_PIP_VERSION} \
    && pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY . /app

EXPOSE 80
CMD ["python3", "-m", "http.server", "8000"]

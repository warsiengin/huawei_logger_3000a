ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY core.py addon_options.py mqtt_service.py app.py ./
RUN /opt/venv/bin/python -c \
    "import addon_options, mqtt_service, app; import paho.mqtt.client; import pymodbus.client"

CMD ["/opt/venv/bin/python", "/app/app.py"]

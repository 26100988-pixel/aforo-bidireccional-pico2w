
import network
import time
import ujson

try:
    import requests
except ImportError:
    import urequests as requests

# ======================================
# 1. CREDENCIALES
# ======================================

WIFI_NOMBRE = "TU_WIFI"
WIFI_CLAVE = "TU_CLAVE_WIFI"

AIO_USUARIO = "TU_USUARIO_ADAFRUIT"
AIO_KEY = "TU_AIO_KEY"

# Feed que ya creaste en Adafruit IO
FEED = "aforo"

# ======================================
# 2. CONECTAR A WIFI
# ======================================

wifi = network.WLAN(network.STA_IF)
wifi.active(True)

if not wifi.isconnected():
    wifi.connect(WIFI_NOMBRE, WIFI_CLAVE)

    inicio = time.ticks_ms()

    while not wifi.isconnected():
        if time.ticks_diff(
            time.ticks_ms(), inicio
        ) > 20000:
            raise RuntimeError("Error de WiFi")

        time.sleep_ms(500)

print("WIFI_OK")
print("IP:", wifi.ifconfig()[0])

# ======================================
# 3. ENVIAR A ADAFRUIT IO
# ======================================

url = (
    "https://io.adafruit.com/api/v2/"
    + AIO_USUARIO
    + "/feeds/"
    + FEED
    + "/data"
)

headers = {
    "X-AIO-Key": AIO_KEY,
    "Content-Type": "application/json"
}

# Solo para comprobar la comunicacion
datos = {"value": 1}

respuesta = None

try:
    print("Enviando aforo a Adafruit IO...")

    respuesta = requests.post(
        url,
        data=ujson.dumps(datos),
        headers=headers
    )

    print("HTTP:", respuesta.status_code)

    if respuesta.status_code in (200, 201):
        print("ENVIO_CORRECTO")
    else:
        print("ENVIO_FALLIDO")

except Exception as error:
    print("ERROR:", error)

finally:
    if respuesta is not None:
        respuesta.close()

"""Proyecto 13 - Aforo bidireccional, Pico 2 W, 1 o 2 nucleos.

Adaptado al montaje REAL y al UNICO dashboard de Adafruit IO del equipo.

Nucleo 0: Wi-Fi + 2 feeds existentes + consola y mediciones.
Nucleo 1: sensores, conteo, PIR, servo y buzzer PIO.

SOLO PUBLICA LOS FEEDS QUE YA EXISTEN:
    aforo        = 0..5 personas
    aforo-lleno  = 0 libre / 1 lleno

No crea dashboards ni intenta publicar `porcentaje` (ese feed no existe).
El porcentaje se calcula SOLO para los mensajes de consola.

Cableado de tu proyecto (sin cambiar cables):
    I2C1 GP2 SDA, GP3 SCL; XSHUT A GP7, B GP8
    PIR GP6; Buzzer GP14 por PIO; Servo GP15 a PWM 50 Hz

Separacion nominal: 100 mm (10 cm); ajuste medido B: resta 30 mm.
Capacidad maxima: 5 personas; entrada A->B; salida B->A.

USO: maqueta de laboratorio. No es una barrera real de seguridad.
Antes de cambiar main.py, hacer respaldo en Thonny.
Las credenciales se leen de credenciales.py (nunca escribirlas aqui).
"""

from machine import Pin, PWM, I2C
from vl53l0x import VL53L0X
import rp2
import _thread
import time
import gc
import network
import ujson

try:
    import requests
except ImportError:
    import urequests as requests

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

# Archivo personal; NO subir a GitHub ni mostrar en capturas.
from credenciales import WIFI_NOMBRE, WIFI_CLAVE, AIO_USUARIO, AIO_KEY

# ---------------------------------------------------------------------------
# A. CONFIGURACION: CAMBIAR ESTA VARIABLE PARA COMPARAR 1 Y 2 NUCLEOS.
# ---------------------------------------------------------------------------
DOS_NUCLEOS = True  # False: todo corre en nucleo 0 mediante asyncio.

MAXIMO = 5
DISTANCIA_COLUMNAS_MM = 100
AJUSTE_B_EXTRA_MM = 30
MARGEN_DETECCION_MM = 20
MARGEN_LIBERACION_MM = 9
CONFIRMACIONES = 3
MUESTRAS_CALIBRACION = 13
TIMEOUT_CRUCE_MS = 5000
PAUSA_LECTURAS_MS = 40
REPORTE_MS = 2000

# Dos feeds cada 6 s -> 20 puntos/min si cambia continuamente.
# Deja margen frente al limite de 30 datos/min de Adafruit IO gratuito.
PUBLICACION_MIN_MS = 6000
PUBLICACION_REPOSO_MS = 60000
REINTENTO_WIFI_MS = 20000

FEEDS = ('aforo', 'aforo-lleno')  # Los dos feeds que YA EXISTEN en tu cuenta
PULSO_ABIERTO_US = 1000
PULSO_CERRADO_US = 2000

# ---------------------------------------------------------------------------
# B. ACTUADORES: EL SERVO NO COMPARTE FRECUENCIA PWM CON EL BUZZER.
# ---------------------------------------------------------------------------
pir = Pin(6, Pin.IN)
servo = PWM(Pin(15))
servo.freq(50)

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def onda_buzzer():
    wrap_target()
    set(pins, 1) [31]
    set(pins, 0) [31]
    wrap()

# 64000 / (32 + 32) = 1000 Hz.
sm_buzzer = rp2.StateMachine(0, onda_buzzer, freq=64000,
                             set_base=Pin(14))
sm_buzzer.active(0)
sm_buzzer.exec('set(pins, 0)')


def mover_servo(cerrar):
    """Emite pulsos de 1000/2000 us a 50 Hz, segun la orientacion montada."""
    pulso = PULSO_CERRADO_US if cerrar else PULSO_ABIERTO_US
    servo.duty_u16(pulso * 65535 // 20000)
    print('[SERVO]', 'CERRADO' if cerrar else 'ABIERTO', pulso, 'us')


# ---------------------------------------------------------------------------
# C. I2C: LOS DOS SENSORES NACEN EN 0x29. XSHUT EVITA UNA COLISION.
# ---------------------------------------------------------------------------
xshut_a = Pin(7, Pin.OUT, value=0)
xshut_b = Pin(8, Pin.OUT, value=0)
time.sleep_ms(150)
i2c = I2C(1, sda=Pin(2), scl=Pin(3), freq=100000)


def iniciar_tof(pin_xshut, direccion, nombre):
    """Libera un sensor por vez y le asigna direccion I2C independiente."""
    pin_xshut.init(Pin.IN)  # Entrada: no forzar 3.3 V sobre XSHUT.
    time.sleep_ms(150)
    if 0x29 not in i2c.scan():
        raise OSError(nombre + ': no aparece en direccion inicial 0x29')
    sensor = VL53L0X(i2c, address=0x29, io_timeout_ms=500)
    sensor.set_address(direccion)
    time.sleep_ms(30)
    if direccion not in i2c.scan():
        raise OSError(nombre + ': no se establecio la direccion nueva')
    print('[TOF]', nombre, hex(direccion))
    return sensor


def leer_mm(sensor, nombre):
    """Lee distancia valida. Sensor B descuenta 30 mm por calibracion previa."""
    try:
        valor = int(sensor.range)
        if not 30 <= valor <= 1800:
            return None
        return max(0, valor - AJUSTE_B_EXTRA_MM) if nombre == 'B' else valor
    except (OSError, RuntimeError, ValueError) as exc:
        print('[TOF ERROR]', nombre, repr(exc))
        return None


def calibrar(sensor, nombre):
    """Usa mediana de 13 medidas libres para obtener fondo de cada sensor."""
    print('[CALIBRACION]', nombre, 'deja los dos sensores despejados')
    time.sleep_ms(700)
    medidas = []
    for _ in range(MUESTRAS_CALIBRACION):
        valor = leer_mm(sensor, nombre)
        if valor is not None:
            medidas.append(valor)
        time.sleep_ms(70)
    if len(medidas) < 8:
        raise RuntimeError('Calibracion ' + nombre + ': pocas lecturas')
    medidas.sort()
    fondo = medidas[len(medidas) // 2]
    fondo_sin_ajuste = fondo + (AJUSTE_B_EXTRA_MM if nombre == 'B' else 0)
    print('[FONDO]', nombre, fondo, 'mm, sin ajuste:', fondo_sin_ajuste)
    if abs(fondo_sin_ajuste - DISTANCIA_COLUMNAS_MM) > 25:
        print('[AVISO] Desviacion >25 mm; revisa orientacion del', nombre)
    if fondo_sin_ajuste < 55 or fondo - MARGEN_LIBERACION_MM <= 30:
        raise RuntimeError('Fondo demasiado cercano en sensor ' + nombre)
    return fondo


# Iniciar hardware una sola vez en nucleo 0, antes del segundo hilo.
mover_servo(False)
sensor_a = iniciar_tof(xshut_a, 0x30, 'A')
sensor_b = iniciar_tof(xshut_b, 0x31, 'B')
fondo_a = calibrar(sensor_a, 'A')
fondo_b = calibrar(sensor_b, 'B')


# ---------------------------------------------------------------------------
# D. CONTEO: HISTERESIS, 3 CONFIRMACIONES Y MAQUINA DE ESTADOS.
# ---------------------------------------------------------------------------
class Detector:
    """Evita rebotes de deteccion con umbrales distintos para entrar/salir."""
    def __init__(self, fondo, nombre):
        self.detectado = False
        self.consecutivas = 0
        self.detectar = max(30, fondo - MARGEN_DETECCION_MM)
        self.liberar = fondo - MARGEN_LIBERACION_MM
        if self.liberar <= self.detectar:
            raise ValueError('Umbrales invalidos en ' + nombre)
        print('[UMBRALES]', nombre, 'detecta <=', self.detectar,
              'libera >=', self.liberar)

    def actualizar(self, mm):
        """Devuelve True cuando la presencia cambia de manera confirmada."""
        if mm is None:
            self.consecutivas = 0
            return False
        cambio = ((not self.detectado and mm <= self.detectar) or
                  (self.detectado and mm >= self.liberar))
        if cambio:
            self.consecutivas += 1
            if self.consecutivas >= CONFIRMACIONES:
                self.detectado = not self.detectado
                self.consecutivas = 0
                return True
        else:
            self.consecutivas = 0
        return False


class Alarma:
    """Secuenciador no bloqueante: PIO suena y la lectura I2C continua."""
    # Una entrada produce un pitido breve. El otro patron representa
    # MAXIMUM CAPACITY REACHED con 3 + 4 + 1 pitidos, no reproduce voz.
    ENTRADA = ((1, 160), (0, 80))
    LLENO = (
        (1, 120), (0, 75), (1, 120), (0, 75), (1, 120), (0, 200),
        (1, 120), (0, 75), (1, 120), (0, 75),
        (1, 120), (0, 75), (1, 120), (0, 200),
        (1, 430), (0, 100),
    )

    def __init__(self):
        self.cola = []
        self.secuencia = None
        self.indice = 0
        self.siguiente = time.ticks_ms()
        self.encendido = False

    def pedir(self, tipo):
        """Acumula hasta 4 eventos para evitar sonidos superpuestos."""
        if tipo == 'lleno':
            if tipo in self.cola:
                return
            if len(self.cola) >= 4:
                # Prioridad: no perder alarma de capacidad aun con cola llena.
                self.cola[-1] = 'lleno'
            else:
                self.cola.append('lleno')
            return
        if len(self.cola) < 4:
            self.cola.append(tipo)

    def apagar(self):
        if self.encendido:
            sm_buzzer.active(0)
            sm_buzzer.exec('set(pins, 0)')
            self.encendido = False

    def avanzar(self, ahora):
        """Ejecuta una transicion de tono cuando vence su intervalo."""
        if time.ticks_diff(ahora, self.siguiente) < 0:
            return
        if self.secuencia is None:
            if not self.cola:
                self.apagar()
                return
            tipo = self.cola.pop(0)
            self.secuencia = self.LLENO if tipo == 'lleno' else self.ENTRADA
            self.indice = 0
            if tipo == 'lleno':
                print('[ALARMA] MAXIMUM CAPACITY REACHED (pitidos)')
        if self.indice >= len(self.secuencia):
            self.apagar()
            self.secuencia = None
            return
        activar, duracion = self.secuencia[self.indice]
        if activar and not self.encendido:
            sm_buzzer.restart()
            sm_buzzer.active(1)
            self.encendido = True
        elif not activar:
            self.apagar()
        self.indice += 1
        self.siguiente = time.ticks_add(ahora, duracion)


class ControlAforo:
    """A->B suma y B->A resta; bloquea pasos incompletos y rebotes."""
    def __init__(self):
        self.a = Detector(fondo_a, 'A')
        self.b = Detector(fondo_b, 'B')
        self.mm_a = None
        self.mm_b = None
        self.aforo = 0
        self.entradas = 0
        self.salidas = 0
        self.sensor_ok = False
        self.estado = 'LIBRE'
        self.inicio_cruce = time.ticks_ms()
        self.permitir_salida = False
        self.barrera_cerrada = False
        self.alarma = Alarma()
        self.pir = pir.value()
        # Medicion real del intervalo entre comienzos de lectura.
        self.ciclos = 0
        self.anterior_inicio = None
        self.max_intervalo_ms = 0
        self.max_ciclo_ms = 0
        self.fallos_sensor = 0

    def procesar(self, ahora):
        a = self.a.detectado
        b = self.b.detectado
        if self.estado == 'LIBRE':
            if a and b:
                self.estado = 'ESPERAR_LIBRE'
            elif a:
                self.estado = 'ESPERANDO_B'
                self.inicio_cruce = ahora
                if self.aforo == MAXIMO:
                    self.alarma.pedir('lleno')
                    print('[DENEGADO] Aforo completo')
            elif b:
                self.estado = 'ESPERANDO_A'
                self.inicio_cruce = ahora
                if self.aforo == MAXIMO:
                    self.permitir_salida = True
        elif self.estado == 'ESPERANDO_B':
            if b:
                if self.aforo < MAXIMO:
                    self.aforo += 1
                    self.entradas += 1
                    self.alarma.pedir('entrada')
                    print('[ENTRADA]', self.aforo, '/', MAXIMO)
                    if self.aforo == MAXIMO:
                        self.alarma.pedir('lleno')
                self.estado = 'ESPERAR_LIBRE'
            elif time.ticks_diff(ahora, self.inicio_cruce) >= TIMEOUT_CRUCE_MS:
                self.estado = 'ESPERAR_LIBRE'
        elif self.estado == 'ESPERANDO_A':
            if a:
                if self.aforo > 0:
                    self.aforo -= 1
                    self.salidas += 1
                    print('[SALIDA]', self.aforo, '/', MAXIMO)
                self.estado = 'ESPERAR_LIBRE'
                self.permitir_salida = False
            elif time.ticks_diff(ahora, self.inicio_cruce) >= TIMEOUT_CRUCE_MS:
                self.estado = 'ESPERAR_LIBRE'
                self.permitir_salida = False
        elif self.estado == 'ESPERAR_LIBRE':
            if not a and not b:
                self.estado = 'LIBRE'
                self.permitir_salida = False

    def actualizar_barrera(self):
        """En maqueta, sensor fallido -> abrir. Una salida B->A puede salir."""
        if not self.sensor_ok or self.aforo < MAXIMO or self.permitir_salida:
            cerrar = False
        elif self.estado == 'LIBRE' and not self.a.detectado and not self.b.detectado:
            cerrar = True
        else:
            return  # No mover barrera mientras hay objetos en zona.
        if cerrar != self.barrera_cerrada:
            mover_servo(cerrar)
            self.barrera_cerrada = cerrar

    def ciclo(self):
        """Un paso completo: I2C -> presencia -> conteo -> actuadores."""
        t0 = time.ticks_ms()
        if self.anterior_inicio is not None:
            intervalo = time.ticks_diff(t0, self.anterior_inicio)
            if intervalo > self.max_intervalo_ms:
                self.max_intervalo_ms = intervalo
        self.anterior_inicio = t0

        self.mm_a = leer_mm(sensor_a, 'A')
        self.mm_b = leer_mm(sensor_b, 'B')
        self.sensor_ok = self.mm_a is not None and self.mm_b is not None
        if self.sensor_ok:
            self.a.actualizar(self.mm_a)
            self.b.actualizar(self.mm_b)
            self.procesar(time.ticks_ms())
        else:
            self.fallos_sensor += 1
        self.pir = pir.value()
        self.actualizar_barrera()
        self.alarma.avanzar(time.ticks_ms())
        duracion = time.ticks_diff(time.ticks_ms(), t0)
        if duracion > self.max_ciclo_ms:
            self.max_ciclo_ms = duracion
        self.ciclos += 1

    def instantanea(self):
        """Tupla sin referencias mutables para comunicacion entre nucleos."""
        return (self.aforo, self.entradas, self.salidas,
                self.pir, self.mm_a, self.mm_b, self.estado,
                self.sensor_ok, self.ciclos, self.max_intervalo_ms,
                self.max_ciclo_ms, self.fallos_sensor)


control = ControlAforo()

# ---------------------------------------------------------------------------
# E. INTERCAMBIO SEGURO ENTRE NUCLEOS.
# En modo dual el nucleo 1 es propietario exclusivo de control/I2C/servo/PIO.
# El nucleo 0 solo lee instantaneas y realiza Wi-Fi/HTTP.
# ---------------------------------------------------------------------------
candado = _thread.allocate_lock()
instantanea_publica = control.instantanea()
terminar = False
hilo_vivo = False
error_hilo = None


def publicar_instantanea():
    global instantanea_publica
    # Crear tupla fuera de la seccion critica para reducir la espera.
    actual = control.instantanea()
    candado.acquire()
    try:
        instantanea_publica = actual
    finally:
        candado.release()


def leer_instantanea():
    candado.acquire()
    try:
        return instantanea_publica
    finally:
        candado.release()


def nucleo_1():
    """Hilo secundario, nunca usa Wi-Fi ni requests."""
    global hilo_vivo, error_hilo
    print('[NUCLEO 1] Lecturas I2C y conteo iniciados')
    try:
        while not terminar:
            control.ciclo()
            publicar_instantanea()
            time.sleep_ms(PAUSA_LECTURAS_MS)
    except Exception as exc:
        error_hilo = repr(exc)
        print('[NUCLEO 1 ERROR]', error_hilo)
    finally:
        # El actuador debe desactivarse antes de terminar el hilo.
        control.alarma.apagar()
        mover_servo(False)
        publicar_instantanea()
        hilo_vivo = False
        print('[NUCLEO 1] Detenido')


async def tarea_un_nucleo():
    """Linea base: mismos sensores y actuadores, pero sin _thread."""
    while True:
        control.ciclo()
        publicar_instantanea()
        await asyncio.sleep_ms(PAUSA_LECTURAS_MS)


# ---------------------------------------------------------------------------
# F. NUCLEO 0: COMUNICACION HTTP CON ADAFRUIT IO.
# ---------------------------------------------------------------------------
def publicar_feed(feed, valor):
    """Devuelve HTTP status, o None si hubo un error de comunicacion."""
    respuesta = None
    try:
        gc.collect()
        url = ('https://io.adafruit.com/api/v2/' + AIO_USUARIO +
               '/feeds/' + feed + '/data')
        respuesta = requests.post(
            url,
            headers={'X-AIO-Key': AIO_KEY,
                     'Content-Type': 'application/json'},
            data=ujson.dumps({'value': int(valor)}),
        )
        estado = respuesta.status_code
        print('[NUBE]', feed, valor, 'HTTP', estado)
        return estado
    except Exception as exc:
        print('[NUBE ERROR]', feed, repr(exc))
        return None
    finally:
        if respuesta is not None:
            respuesta.close()


async def tarea_nube():
    """Publica aforo y aforo-lleno; nunca publica el feed ausente porcentaje."""
    credenciales = (WIFI_NOMBRE, WIFI_CLAVE, AIO_USUARIO, AIO_KEY)
    if any(not c or c.startswith('REEMPLAZA_CON_') for c in credenciales):
        print('[NUBE] Completa credenciales.py; conteo sigue local')
        return

    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    anterior = None
    ultimo_exito = None
    ultimo_envio = None
    ultima_conexion = None
    conectado_antes = False

    while True:
        ahora = time.ticks_ms()
        if not wifi.isconnected():
            if conectado_antes:
                print('[WIFI] Conexion perdida; conteo local sigue')
            conectado_antes = False
            if (ultima_conexion is None or
                time.ticks_diff(ahora, ultima_conexion) >= REINTENTO_WIFI_MS):
                ultima_conexion = ahora
                try:
                    print('[WIFI] Reconectando...')
                    wifi.connect(WIFI_NOMBRE, WIFI_CLAVE)
                except Exception as exc:
                    print('[WIFI ERROR]', repr(exc))
            await asyncio.sleep_ms(1000)
            continue

        if not conectado_antes:
            print('[WIFI] WIFI_OK | IP:', wifi.ifconfig()[0])
            conectado_antes = True
            anterior = None  # Resincronizar despues de reconectar.
            ultimo_envio = None

        # Publicar solamente feeds existentes; el dashboard es el mismo.
        # NO enviamos `porcentaje` porque el usuario todavia no tiene
        # ese feed y causaba HTTP 404.

        s = leer_instantanea()
        aforo = s[0]
        estado = (aforo, 1 if aforo >= MAXIMO else 0)
        debe_enviar = (estado != anterior or ultimo_exito is None or
                       time.ticks_diff(ahora, ultimo_exito) >= PUBLICACION_REPOSO_MS)
        intervalo_ok = (ultimo_envio is None or
                        time.ticks_diff(ahora, ultimo_envio) >= PUBLICACION_MIN_MS)

        if debe_enviar and intervalo_ok:
            ultimo_envio = ahora
            ok = True
            # Snapshot consistente: si cambia el aforo durante HTTPS,
            # publicaremos la nueva version en el siguiente ciclo habilitado.
            pares = [('aforo', estado[0]), ('aforo-lleno', estado[1])]

            for feed, valor in pares:
                codigo_http = publicar_feed(feed, valor)
                if codigo_http not in (200, 201):
                    ok = False
                    if codigo_http == 404:
                        print('[NUBE] Revisa la KEY en Adafruit IO > Feeds:', feed)
                    elif codigo_http in (401, 403):
                        print('[NUBE] Revisa AIO_USUARIO y AIO_KEY en credenciales.py')
                await asyncio.sleep_ms(0)

            if ok:
                anterior = estado
                ultimo_exito = time.ticks_ms()
                print('[NUBE]', len(pares), 'feeds actualizados correctamente')
            else:
                print('[NUBE] Envio parcial; se reintentara sin detener sensores')
        await asyncio.sleep_ms(300)


async def tarea_monitor():
    """Informe para la exposicion: intervalos medidos de adquisicion."""
    ultimo = -1
    while True:
        if DOS_NUCLEOS and error_hilo is not None:
            raise RuntimeError('Fallo segundo nucleo: ' + error_hilo)
        s = leer_instantanea()
        aforo, entradas, salidas, pir_estado, mm_a, mm_b, estado, sensores_ok, \
            ciclos, intervalo_max, duracion_max, fallos = s
        if ciclos != ultimo:
            print('[MONITOR] nucleo=', 2 if DOS_NUCLEOS else 1,
                  '| aforo=', aforo, '/', MAXIMO,
                  '| ocupacion=', (100 * aforo // MAXIMO), '%',
                  '| A=', mm_a, '| B=', mm_b,
                  '| estado=', estado, '| PIR=', pir_estado)
            print('[MEDICION] ciclos=', ciclos,
                  '| intervalo_max_ms=', intervalo_max,
                  '| ciclo_max_ms=', duracion_max,
                  '| fallos_sensor=', fallos)
            ultimo = ciclos
        await asyncio.sleep_ms(REPORTE_MS)


async def principal():
    """Comparacion valida: mismo hardware, modo elegido antes del arranque."""
    global hilo_vivo
    print('=== PROYECTO 13: AFORO + ADAFRUIT IO ===')
    print('[CONFIG] MODO:', 'DOS NUCLEOS' if DOS_NUCLEOS else 'UN NUCLEO')
    print('[CONFIG] I2C GP2/GP3; XSHUT GP7/GP8; PIR GP6; '
          'BUZZER GP14 PIO; SERVO GP15')
    print('[CONFIG] 100 mm; ajuste B -30 mm; MAXIMO 5')
    print('[CONFIG] Feeds:', FEEDS)
    print('[CONFIG] Dashboard existente; solo feeds aforo y aforo-lleno')
    print('[CONFIG] Porcentaje solo local; NO se envia a la nube')
    if DOS_NUCLEOS:
        hilo_vivo = True
        try:
            _thread.start_new_thread(nucleo_1, ())
        except Exception:
            hilo_vivo = False
            raise
        await asyncio.gather(tarea_nube(), tarea_monitor())
    else:
        await asyncio.gather(tarea_un_nucleo(), tarea_nube(), tarea_monitor())


try:
    asyncio.run(principal())
except KeyboardInterrupt:
    print('[STOP] Solicitada detencion')
except Exception as exc:
    print('[ERROR PRINCIPAL]', repr(exc))
finally:
    # En MicroPython es preferible detener el hilo antes de reiniciar la Pico.
    terminar = True
    if DOS_NUCLEOS and hilo_vivo:
        inicio_espera = time.ticks_ms()
        while hilo_vivo and time.ticks_diff(time.ticks_ms(), inicio_espera) < 4000:
            time.sleep_ms(50)
        if hilo_vivo:
            print('[ADVERTENCIA] Hilo activo: evita reiniciar sin detenerlo.')
    else:
        control.alarma.apagar()
        mover_servo(False)
    if not hilo_vivo:
        servo.deinit()
        sm_buzzer.active(0)
        sm_buzzer.exec('set(pins, 0)')
    print('[STOP] Programa finalizado; no usar como barrera real')

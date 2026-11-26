"""Proyecto 13: Aforo bidireccional con Raspberry Pi Pico 2 W.

Versión integrada: 100 mm libres, un núcleo, asyncio y Adafruit IO por Wi-Fi.
Sensores: VL53L0X en I2C1 (SDA GP2 / SCL GP3), XSHUT A GP7, B GP8.
Otros: PIR GP6, servo GP15 (PWM 50 Hz) y buzzer GP14 con PIO.
Dependencias: MicroPython con rp2 y vl53l0x.py compatible.

Objetivo: contar entradas y salidas, controlar la barrera y avisar mediante
pitido de entrada o patrón de aforo lleno. No sintetiza voz hablada.
Esta versión aplica un ajuste de -30 mm a las lecturas del sensor B.
Publica los feeds aforo y aforo-lleno por HTTPS (Adafruit IO).
La publicación HTTP con requests es bloqueante: durante cada envío,
asyncio detiene brevemente las lecturas; comprobar el conteo en pruebas reales.
No incluye todavía el reto medido de dos núcleos.
Es una maqueta de demostración, no un sistema de seguridad de evacuación.
"""

# TODO: Evaluar publicaciones HTTP asíncronas o segundo núcleo para reducir
#       posibles demoras al leer ToF durante los envíos HTTPS.
# TODO: Medir el reto de dos núcleos y guardar los resultados reales.
# FIXME: Verificar el ancho físico y la calibración de ambos sensores.

# ============================================================================
# 1. IMPORTACIONES Y COMPATIBILIDAD CON EL FIRMWARE
# ============================================================================
from machine import Pin, PWM, I2C
import rp2
from vl53l0x import VL53L0X
import time
import network
import gc
import ujson

# Dependencia probada previamente al enviar el feed aforo desde esta Pico.
try:
    import requests
except ImportError:
    import urequests as requests

# Credenciales separadas para evitar subir contraseñas al repositorio Git.
from credenciales import WIFI_NOMBRE, WIFI_CLAVE, AIO_USUARIO, AIO_KEY

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

# ====== AJUSTES DEL PROYECTO ======
MAXIMO = 5
# Separacion nominal entre columnas: 10 cm = 100 mm.
DISTANCIA_COLUMNAS_MM = 100
# Los limites se calculan automaticamente a partir de la distancia
# LIBRE que mide cada sensor al encender.
# AJUSTE ADICIONAL solicitado para sensor B: se restan 30 mm
# a cada lectura de B, sin cambiar las lecturas del sensor A.
# OJO: este codigo original NO tenia el offset fijo de 36 mm que
# aparecia en versiones antiguas. Si utilizabas esa version, no mezclar offsets.
AJUSTE_B_EXTRA_MM = 30
MARGEN_DETECCION_MM = 20  # ejemplo: 100 - 20 = 80 mm para DETECTAR
MARGEN_LIBERACION_MM = 9  # ejemplo: 100 - 9 = 91 mm para LIBERAR
MUESTRAS_CALIBRACION = 13
CONFIRMACIONES = 3
TIMEOUT_CRUCE_MS = 5000
REPORTE_MS = 1500

# Dos peticiones HTTPS como máximo por ciclo de publicación.
# 12 s entre intentos = máximo teórico de 10 puntos/minuto si ambos feeds
# cambian continuamente. El ciclo de 60 s mantiene datos recientes al estar
# en reposo, sin gastar la cuota de datos con lecturas de 40 ms.
PUBLICACION_MIN_MS = 12000
PUBLICACION_REPOSO_MS = 60000
REINTENTO_WIFI_MS = 20000

# Claves EXACTAS de los feeds existentes de Adafruit IO.
FEED_AFORO = 'aforo'
FEED_AFORO_LLENO = 'aforo-lleno'
# True: el buzzer sonara UNA VEZ por 2 segundos al arrancar.
# Despues de validar que suena, puedes cambiarlo a False.
PRUEBA_BUZZER_AL_INICIAR = False

# Servo SG90 en sentido invertido (segun el montaje real).
# Aforo disponible -> barrera ABIERTA (1000 us).
# Aforo completo -> barrera CERRADA (2000 us).
# Si el brazo llega a un tope mecanico, reajustar los pulsos antes de usar.
PULSO_ABIERTO_US = 1000
PULSO_CERRADO_US = 2000

# ====== ACTUADORES Y PIR ======
pir = Pin(6, Pin.IN)
servo = PWM(Pin(15))
servo.freq(50)
# El buzzer de dos patas se controla a traves de su circuito adecuado.
# PIO ofrece un tono de 1000 Hz sin modificar la frecuencia PWM del servo.
@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def onda_buzzer_1000hz():
    wrap_target()
    set(pins, 1) [31]  # 32 ciclos: nivel alto
    set(pins, 0) [31]  # 32 ciclos: nivel bajo
    wrap()

# 64000 ciclos/s / 64 ciclos por onda = 1000 Hz.
# PIO mantiene el tono separado del PWM de 50 Hz del servo.
sm_buzzer = rp2.StateMachine(0, onda_buzzer_1000hz,
                             freq=64000, set_base=Pin(14))
# La máquina PIO solo debe quedar activa mientras hay sonido.
sm_buzzer.active(0)
sm_buzzer.exec('set(pins, 0)')
print('[ACTUADORES] Servo PWM GP15:', servo.freq(),
      'Hz; buzzer PIO GP14: 1000 Hz')


def mover_servo(cerrar):
    """Coloca la barrera en una de las dos posiciones calibradas.
    
    Args:
        cerrar (bool): True selecciona el pulso de cierre; False, apertura.
    
    No detecta obstáculos: los límites mecánicos deben probarse antes.
    """
    pulso = PULSO_CERRADO_US if cerrar else PULSO_ABIERTO_US
    # 50 Hz implica un período de 20 000 us; duty_u16 usa escala 0..65535.
    servo.duty_u16(int(pulso * 65535 // 20000))
    print('[BARRERA]', 'CERRADA' if cerrar else 'ABIERTA', '- GP15 -', pulso, 'us', '| frecuencia', servo.freq(), 'Hz')


# Iniciar abierto antes de activar sensores.
mover_servo(False)

# Prueba de audio ANTES de inicializar los sensores.
# Si el sensor B falla al iniciar, igualmente habremos comprobado el buzzer.
if PRUEBA_BUZZER_AL_INICIAR:
    print('[TEST BUZZER] Tono de 1000 Hz durante 2 segundos...')
    try:
        sm_buzzer.restart()
        sm_buzzer.active(1)
        time.sleep_ms(2000)
    finally:
        # La máquina PIO solo debe quedar activa mientras hay sonido.
        sm_buzzer.active(0)
        sm_buzzer.exec('set(pins, 0)')
    print('[TEST BUZZER] Apagado, GP14=0')

# ====== DOS SENSORES EN EL MISMO BUS I2C ======
# XSHUT activo en 0. Se libera como entrada: requiere pull-up en el modulo.
# Ambos inician apagados para evitar que respondan a 0x29 simultáneamente.
xshut_a = Pin(7, Pin.OUT, value=0)
xshut_b = Pin(8, Pin.OUT, value=0)
time.sleep_ms(150)
i2c = I2C(1, sda=Pin(2), scl=Pin(3), freq=100000)


def iniciar_tof(xshut, nueva_direccion, nombre):
    """Activa un VL53L0X aislado y cambia su dirección I2C.
    
    Args:
        xshut: GPIO que mantiene apagado o libera este módulo.
        nueva_direccion (int): 0x30 para A o 0x31 para B.
        nombre (str): Identificador utilizado en los mensajes.
    Returns:
        VL53L0X: Sensor configurado para leer distancias.
    Raises:
        OSError: Si no aparece en la dirección inicial o final.
    """
    xshut.init(Pin.IN)  # No poner HIGH directamente en XSHUT.
    time.sleep_ms(150)
    if 0x29 not in i2c.scan():
        raise OSError(nombre + ': no encontrado en 0x29')
    sensor = VL53L0X(i2c, address=0x29, io_timeout_ms=500)
    sensor.set_address(nueva_direccion)
    time.sleep_ms(30)
    if nueva_direccion not in i2c.scan():
        raise OSError(nombre + ': no se cambio la direccion')
    print(nombre, 'listo en', hex(nueva_direccion))
    return sensor


# Secuencia obligatoria: cambiar A antes de encender B (ambos nacen en 0x29).
sensor_a = iniciar_tof(xshut_a, 0x30, 'Sensor A')
sensor_b = iniciar_tof(xshut_b, 0x31, 'Sensor B')
print('I2C:', [hex(x) for x in i2c.scan()])


def leer_mm(sensor, nombre):
    """Obtiene una distancia válida en milímetros, o None ante fallo.
    
    Args:
        sensor: Instancia del controlador VL53L0X.
        nombre (str): Identificador para diagnóstico y ajustes.
    Returns:
        int | None: Distancia aceptada o ausencia de lectura fiable.
    """
    try:
        mm = int(sensor.range)
        if not 30 <= mm <= 1800:
            return None
        # El ajuste se aplica SOLO al sensor B.
        # El ajuste se aplica antes de calcular el fondo y los umbrales de B.
        if nombre == 'B':
            mm = max(0, mm - AJUSTE_B_EXTRA_MM)
        return mm
    except (OSError, RuntimeError, ValueError) as exc:
        print('[ERROR SENSOR ' + nombre + ']', exc)
        return None


def calibrar_fondo(sensor, nombre):
    """Estima el fondo libre mediante la mediana de varias lecturas.
    
    Args:
        sensor: VL53L0X que apunta a la columna opuesta.
        nombre (str): Etiqueta A/B para avisos de diagnóstico.
    Returns:
        int: Distancia de referencia obtenida al iniciar.
    Raises:
        RuntimeError: Si hay pocas muestras o un fondo inadecuado.
    
    Es imprescindible mantener la abertura despejada durante esta fase.
    """
    print('[CALIBRACION ' + nombre + '] Deja la abertura libre...')
    time.sleep_ms(700)
    muestras = []
    for _ in range(MUESTRAS_CALIBRACION):
        mm = leer_mm(sensor, nombre)
        if mm is not None:
            muestras.append(mm)
        time.sleep_ms(70)
    if len(muestras) < 8:
        raise RuntimeError('Calibracion ' + nombre + ': lecturas insuficientes')
    # La mediana resiste mejor lecturas atípicas que un promedio simple.
    muestras.sort()
    fondo = muestras[len(muestras) // 2]
    # Reconstrucción aproximada para comparar con la separación física.
    fondo_original = fondo + (AJUSTE_B_EXTRA_MM if nombre == 'B' else 0)
    print('[CALIBRACION ' + nombre + '] Fondo usado:', fondo,
          'mm; lectura original:', fondo_original, 'mm;',
          'separacion nominal:', DISTANCIA_COLUMNAS_MM, 'mm')
    if abs(fondo_original - DISTANCIA_COLUMNAS_MM) > 25:
        print('[AVISO ' + nombre + '] La lectura ORIGINAL del fondo difiere de 100 mm.')
        print('Revisa orientacion, obstaculos y montaje; un offset no corrige eso.')
    if fondo_original < 55:
        raise RuntimeError('Calibracion ' + nombre + ': fondo original demasiado cerca ('
                           + str(fondo_original) + ' mm). Revisar montaje.')
    if nombre == 'B' and (fondo - MARGEN_LIBERACION_MM <= max(30, fondo - MARGEN_DETECCION_MM)):
        raise RuntimeError('Calibracion B: el descuento deja muy poco rango util ('
                           + str(fondo) + ' mm). Reduce AJUSTE_B_EXTRA_MM.')
    return fondo


# Al arrancar, NO debe haber objetos atravesando el vano.
fondo_a = calibrar_fondo(sensor_a, 'A')
fondo_b = calibrar_fondo(sensor_b, 'B')



# ============================================================================
# CLASE DE ESTADO: Detector
# ============================================================================
class Detector:
    """Convierte distancias ruidosas en presencia estable o ausencia.
    
    Utiliza umbrales diferentes al detectar y liberar (histéresis),
    junto con confirmaciones consecutivas para reducir rebotes.
    """
    def __init__(self, fondo_mm, nombre):
        """Calcula umbrales relativos al fondo propio de este sensor.
        
        Args:
            fondo_mm (int): Mediana medida con el paso libre.
            nombre (str): Nombre del sensor para reportar errores.
        """
        self.detectado = False
        self.consecutivas = 0
        # La activación exige un objeto más próximo que el fondo libre.
        self.umbral_detectar = max(30, fondo_mm - MARGEN_DETECCION_MM)
        # Histéresis: se libera a una distancia mayor para evitar oscilaciones.
        self.umbral_liberar = fondo_mm - MARGEN_LIBERACION_MM
        if self.umbral_liberar <= self.umbral_detectar:
            raise ValueError('Umbrales invalidos para sensor ' + nombre)
        print('[UMBRALES ' + nombre + '] Detectar <=', self.umbral_detectar,
              'mm; liberar >=', self.umbral_liberar, 'mm')

    def actualizar(self, mm):
        """Actualiza la presencia con una nueva lectura.
        
        Args:
            mm (int | None): Distancia medida; None indica fallo.
        Returns:
            bool: True únicamente si cambió la presencia confirmada.
        """
        if mm is None:
            self.consecutivas = 0
            return False

        cambiar = ((not self.detectado and mm <= self.umbral_detectar)
                   or (self.detectado and mm >= self.umbral_liberar))
        if cambiar:
            self.consecutivas += 1
            # Tres lecturas compatibles reducen cambios por una muestra ruidosa.
            if self.consecutivas >= CONFIRMACIONES:
                self.detectado = not self.detectado
                self.consecutivas = 0
                return True
        else:
            self.consecutivas = 0
        return False



# ============================================================================
# CLASE DE ESTADO: ControlAforo
# ============================================================================
class ControlAforo:
    """Coordina las secuencias A/B y mantiene el contador local.
    
    Estados: LIBRE, ESPERANDO_B, ESPERANDO_A y ESPERAR_LIBRE.
    La entrada es A -> B; la salida es B -> A.
    """
    def __init__(self):
        """Establece estado inicial de sensores, contador y actuadores.
        
        No recupera automáticamente el aforo tras reiniciar la placa.
        """
        self.a = Detector(fondo_a, 'A')
        self.b = Detector(fondo_b, 'B')
        self.mm_a = None
        self.mm_b = None
        self.sensor_ok = False
        self.aforo = 0
        self.entradas = 0
        self.salidas = 0
        self.estado = 'LIBRE'
        self.inicio_cruce = time.ticks_ms()
        self.permitir_salida = False
        self.barrera_cerrada = False
        # Sonidos por evento: entrada confirmada / aforo completo.
        # No se reproduce un sonido continuo por tener aforo >= 5.
        self.avisos_pendientes = []

    def solicitar_aviso(self, tipo):
        """Pone un sonido en espera sin interrumpir la lectura ToF.
        
        Args:
            tipo (str): 'entrada' o 'lleno'.
        
        Limita la cola y evita duplicar alertas de aforo lleno.
        """
        # Evitar cola infinita y multiples mensajes de aforo completo.
        # Evita repetir el mismo aviso mientras aún está en la cola.
        if tipo == 'lleno' and 'lleno' in self.avisos_pendientes:
            return
        if len(self.avisos_pendientes) < 10:
            self.avisos_pendientes.append(tipo)

    def procesar(self, ahora):
        """Procesa un ciclo de la máquina de estados de paso.
        
        Args:
            ahora (int): Marca de tiempo de time.ticks_ms().
        
        Actualiza el aforo cuando se confirma el segundo sensor dentro
        del tiempo permitido, y espera liberación antes de rearmarse.
        """
        a = self.a.detectado
        b = self.b.detectado

        # Solo decide la dirección a partir del primer sensor activado.
        if self.estado == 'LIBRE':
            if a and b:
                # No se contabiliza otro cruce hasta que ambos ToF queden libres.
                self.estado = 'ESPERAR_LIBRE'
                print('[IGNORADO] Ambos sensores comenzaron detectados')
            elif a:
                self.estado = 'ESPERANDO_B'
                self.inicio_cruce = ahora
                if self.aforo >= MAXIMO:
                    # Solo suena al detectar un NUEVO intento A primero.
                    self.solicitar_aviso('lleno')
                    print('[INTENTO DENEGADO] Aforo 5/5: alarma una vez')
                else:
                    print('Posible ENTRADA: A primero')
            elif b:
                self.estado = 'ESPERANDO_A'
                self.inicio_cruce = ahora
                if self.aforo >= MAXIMO:
                    self.permitir_salida = True
                print('Posible SALIDA: B primero')

        elif self.estado == 'ESPERANDO_B':
            if b:
                if self.aforo < MAXIMO:
                    self.aforo += 1
                    self.entradas += 1
                    print('[ENTRADA] Aforo:', self.aforo, '/', MAXIMO)
                    self.solicitar_aviso('entrada')
                    if self.aforo == MAXIMO:
                        self.solicitar_aviso('lleno')
                        print('[AFORO COMPLETO] Alarma una sola vez')
                else:
                    print('[BLOQUEADO] Aforo completo; no se suma')
                # No se contabiliza otro cruce hasta que ambos ToF queden libres.
                self.estado = 'ESPERAR_LIBRE'
            # Expira una detección incompleta para evitar conteos tardíos.
            elif time.ticks_diff(ahora, self.inicio_cruce) >= TIMEOUT_CRUCE_MS:
                print('[CANCELADA] Entrada sin segundo sensor')
                # No se contabiliza otro cruce hasta que ambos ToF queden libres.
                self.estado = 'ESPERAR_LIBRE'

        elif self.estado == 'ESPERANDO_A':
            if a:
                if self.aforo > 0:
                    self.aforo -= 1
                    self.salidas += 1
                    print('[SALIDA] Aforo:', self.aforo, '/', MAXIMO)
                else:
                    print('[IGNORADO] Aforo ya estaba en cero')
                # No se contabiliza otro cruce hasta que ambos ToF queden libres.
                self.estado = 'ESPERAR_LIBRE'
                self.permitir_salida = False
            # Expira una detección incompleta para evitar conteos tardíos.
            elif time.ticks_diff(ahora, self.inicio_cruce) >= TIMEOUT_CRUCE_MS:
                print('[CANCELADA] Salida sin segundo sensor')
                # No se contabiliza otro cruce hasta que ambos ToF queden libres.
                self.estado = 'ESPERAR_LIBRE'
                self.permitir_salida = False

        elif self.estado == 'ESPERAR_LIBRE':
            if not a and not b:
                self.estado = 'LIBRE'
                self.permitir_salida = False
                print('Pasillo libre; listo para otro cruce')


control = ControlAforo()


# ADQUISICIÓN: esta tarea es dueña de las lecturas del bus I2C.
async def tarea_sensores_y_conteo():
    """Lee ambos ToF y alimenta el contador continuamente.
    
    Las mediciones I2C son síncronas: otras tareas avanzan entre lecturas,
    pero no mientras el controlador está bloqueado en una medición.
    """
    while True:
        control.mm_a = leer_mm(sensor_a, 'A')
        control.mm_b = leer_mm(sensor_b, 'B')
        control.sensor_ok = (control.mm_a is not None
                             and control.mm_b is not None)
        if control.sensor_ok:
            if control.a.actualizar(control.mm_a):
                print('A:', 'DETECTADO' if control.a.detectado else 'LIBRE')
            if control.b.actualizar(control.mm_b):
                print('B:', 'DETECTADO' if control.b.detectado else 'LIBRE')
            control.procesar(time.ticks_ms())
        # La biblioteca hace lecturas I2C sincronas. El await permite a otras
        # tareas avanzar entre ciclos, no durante cada medicion individual.
        # Cede tiempo al resto de tareas entre ciclos de lectura.
        await asyncio.sleep_ms(40)


# SUPERVISIÓN: el PIR no reemplaza el orden de activación A/B.
async def tarea_pir():
    """Informa cambios de movimiento sin decidir la dirección del paso.
    
    El PIR es auxiliar: no debe impedir que se registre una salida.
    """
    anterior = pir.value()
    print('[PIR]', 'MOVIMIENTO' if anterior else 'SIN MOVIMIENTO')
    while True:
        actual = pir.value()
        if actual != anterior:
            print('[PIR]', 'MOVIMIENTO' if actual else 'SIN MOVIMIENTO')
            anterior = actual
        # El PIR es informativo, nunca requisito para permitir una salida.
        await asyncio.sleep_ms(150)


# ACTUACIÓN: el servo conserva su PWM a 50 Hz independientemente del aforo.
async def tarea_barrera():
    """Ajusta la barrera según aforo, sensores y posibles salidas.
    
    No cierra durante un cruce; ante fallo de sensores adopta apertura
    como estrategia del prototipo para no bloquear el paso.
    """
    ultimo_diagnostico = time.ticks_ms()
    while True:
        # Si hay error de sensor, o aforo inferior a MAXIMO, abrir.
        # La barrera siempre se abre cuando hay una posible salida (B primero).
        # Política de maqueta: ante falla de sensor, evita bloquear la salida.
        if not control.sensor_ok or control.aforo < MAXIMO or control.permitir_salida:
            cerrar = False
        else:
            # Cerrar SOLO al terminar el cruce y quedar ambos sensores libres.
            cerrar = (control.estado == 'LIBRE'
                      and not control.a.detectado
                      and not control.b.detectado)
            if not cerrar:
                if time.ticks_diff(time.ticks_ms(), ultimo_diagnostico) >= 2000:
                    print('[BARRERA ESPERANDO] estado:', control.estado,
                          '| A:', control.a.detectado, '| B:', control.b.detectado)
                    ultimo_diagnostico = time.ticks_ms()
                # Esperar sin mover durante el cruce, sin abrir una entrada
                # cuando el aforo ya esta completo.
                await asyncio.sleep_ms(60)
                continue

        if cerrar != control.barrera_cerrada:
            print('[CAMBIO BARRERA] aforo:', control.aforo,
                  '| estado:', control.estado, '| sensores OK:', control.sensor_ok)
            mover_servo(cerrar)
            control.barrera_cerrada = cerrar
        await asyncio.sleep_ms(60)


# === BUZZER GP14: sonido por eventos usando PIO ===
# El buzzer no puede hablar: codifica el mensaje en una secuencia de pitidos.
# Usamos PIO para no cambiar el PWM de 50 Hz del servo (GP15).
async def pitido(duracion_ms):
    """Activa el tono PIO por un intervalo y asegura el apagado.
    
    Args:
        duracion_ms (int): Duración del sonido en milisegundos.
    
    El await permite que el servo y los sensores sigan ejecutándose.
    """
    try:
        sm_buzzer.restart()
        sm_buzzer.active(1)
        await asyncio.sleep_ms(duracion_ms)
    finally:
        # La máquina PIO solo debe quedar activa mientras hay sonido.
        sm_buzzer.active(0)
        sm_buzzer.exec('set(pins, 0)')


async def sonido_entrada():
    """Emite un aviso breve después de confirmar A -> B."""
    print('[SONIDO] Entrada confirmada: un pitido')
    await pitido(160)


async def sonido_aforo_lleno():
    """Representa MAXIMUM CAPACITY REACHED con grupos de pitidos.
    
    El buzzer no pronuncia palabras: reproduce un patrón 3 + 4 + 1.
    """
    print('[ALERTA] MAXIMUM CAPACITY REACHED (aforo lleno)')
    grupos = (
        (110, 110, 110),       # MAX-I-MUM
        (110, 110, 110, 110),  # CA-PA-CI-TY
        (420,),                # REACHED
    )
    for numero, grupo in enumerate(grupos):
        for indice, duracion in enumerate(grupo):
            await pitido(duracion)
            if indice < len(grupo) - 1:
                await asyncio.sleep_ms(75)
        if numero < len(grupos) - 1:
            await asyncio.sleep_ms(170)
    print('[SONIDO] Fin de aviso, GP14=0')


# ALERTAS: se activan por eventos, no continuamente en cada ciclo.
async def tarea_alarma():
    """Consume avisos solicitados sin detener el resto del sistema.
    
    La versión digital usa una bandera; la versión PIO usa una cola.
    """
    while True:
        if control.avisos_pendientes:
            aviso = control.avisos_pendientes.pop(0)
            if aviso == 'entrada':
                await sonido_entrada()
            elif aviso == 'lleno' and control.aforo >= MAXIMO:
                await sonido_aforo_lleno()
        else:
            await asyncio.sleep_ms(25)


# DIAGNÓSTICO: imprimir continuamente consume tiempo de CPU/USB.
async def tarea_monitor():
    """Muestra diagnóstico periódico de sensores, aforo y PIR.
    
    La consola es una ayuda de prueba; no sustituye un dashboard IoT.
    """
    while True:
        print('A:', control.mm_a, 'mm | B:', control.mm_b,
              'mm | AFORO:', control.aforo, '/', MAXIMO,
              '| ESTADO:', control.estado,
              '| PIR:', pir.value())
        await asyncio.sleep_ms(REPORTE_MS)


# ============================================================================
# NUBE: PUBLICACIÓN DE AFORO A DOS FEEDS YA EXISTENTES DE ADAFRUIT IO
# ============================================================================
# Es importante no publicar cada lectura del VL53L0X: ambas se realizan muchas
# veces por segundo, mientras que Adafruit IO cobra cuota por punto recibido.
# Aquí enviamos solo cambios o una actualización periódica de estado.


def publicar_feed(feed, valor):
    """Envía un entero al feed mediante HTTPS usando la API v2 de Adafruit IO.

    Args:
        feed (str): Clave exacta 'aforo' o 'aforo-lleno'.
        valor (int): Valor actual a publicar en la nube.
    Returns:
        bool: True solo si el servidor responde HTTP 200 o 201.

    NOTA: requests.post es bloqueante; durante ese instante, la ejecución
    cooperativa asyncio no puede leer sensores. Se publican pocos datos para
    reducir el impacto; este límite debe medirse en la demostración.
    """
    url = ('https://io.adafruit.com/api/v2/' + AIO_USUARIO
           + '/feeds/' + feed + '/data')
    cabeceras = {
        'X-AIO-Key': AIO_KEY,
        'Content-Type': 'application/json',
    }
    cuerpo = ujson.dumps({'value': int(valor)})
    respuesta = None
    try:
        gc.collect()
        respuesta = requests.post(url, data=cuerpo, headers=cabeceras)
        codigo_http = respuesta.status_code
        ok = codigo_http in (200, 201)
        print('[NUBE]', feed, '=', valor, '| HTTP:', codigo_http,
              '|', 'OK' if ok else 'FALLO')
        return ok
    except Exception as error:
        # Una falla de internet NO debe borrar el conteo local.
        print('[NUBE ERROR]', feed, repr(error))
        return False
    finally:
        if respuesta is not None:
            respuesta.close()


async def tarea_adafruit_io():
    """Conecta Wi-Fi, mantiene reconexión y sincroniza aforo con Adafruit IO.

    Publica 'aforo' (0..5) y 'aforo-lleno' (0/1). Conserva el último estado
    exitoso y reintenta cuando regresa internet. No inventa personas ni
    restablece el contador a partir del historial de Adafruit IO.
    """
    # Evita enviar solicitudes con los valores de ejemplo sin configurar.
    if (WIFI_NOMBRE.startswith('REEMPLAZA_CON_') or
        WIFI_CLAVE.startswith('REEMPLAZA_CON_') or
        AIO_USUARIO.startswith('REEMPLAZA_CON_') or
        AIO_KEY.startswith('REEMPLAZA_CON_')):
        print('[NUBE] Revisa credenciales.py y completa los cuatro datos.')
        print('[NUBE] El aforo local seguira funcionando sin enviar datos.')
        return

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    ultimo_estado = None     # Tupla (aforo, lleno) confirmada en la nube.
    ultimo_exito = None
    ultimo_intento = None
    ultimo_wifi = None
    wifi_estaba_conectado = False

    while True:
        ahora = time.ticks_ms()
        conectado = wlan.isconnected()

        if not conectado:
            if wifi_estaba_conectado:
                print('[WIFI] Conexion perdida; el conteo local continua.')
                wifi_estaba_conectado = False
            if (ultimo_wifi is None or
                time.ticks_diff(ahora, ultimo_wifi) >= REINTENTO_WIFI_MS):
                ultimo_wifi = ahora
                try:
                    print('[WIFI] Intentando conectar...')
                    wlan.connect(WIFI_NOMBRE, WIFI_CLAVE)
                except Exception as error:
                    print('[WIFI ERROR]', repr(error))
            await asyncio.sleep_ms(1000)
            continue

        if not wifi_estaba_conectado:
            print('[WIFI] WIFI_OK | IP:', wlan.ifconfig()[0])
            wifi_estaba_conectado = True
            # Recuperar el estado local al reconectar, aunque no haya cambios.
            ultimo_estado = None
            ultimo_intento = None

        # Captura coherente del contador justo antes de intentar publicar.
        actual = control.aforo
        completo = 1 if actual >= MAXIMO else 0
        estado_actual = (actual, completo)
        cambio = estado_actual != ultimo_estado
        vencio_reporte = (ultimo_exito is None or
                          time.ticks_diff(ahora, ultimo_exito) >= PUBLICACION_REPOSO_MS)
        intervalo_ok = (ultimo_intento is None or
                        time.ticks_diff(ahora, ultimo_intento) >= PUBLICACION_MIN_MS)

        if intervalo_ok and (cambio or vencio_reporte):
            ultimo_intento = ahora
            print('[NUBE] Sincronizando aforo real:', actual, '/', MAXIMO,
                  '| aforo-lleno:', completo)

            ok_aforo = publicar_feed(FEED_AFORO, actual)
            # Cede el control antes del segundo POST para que otras tareas
            # puedan continuar, incluso si el primer envío tardó.
            await asyncio.sleep_ms(0)
            ok_lleno = publicar_feed(FEED_AFORO_LLENO, completo)

            if ok_aforo and ok_lleno:
                ultimo_estado = estado_actual
                ultimo_exito = time.ticks_ms()
                print('[NUBE] Ambos feeds actualizados correctamente.')
            else:
                print('[NUBE] Envio incompleto; se reintentara sin alterar aforo.')

        await asyncio.sleep_ms(500)


# ORQUESTACIÓN: gather mantiene vivas las tareas cooperativas.
async def principal():
    """Inicia tareas del sistema local y una tarea adicional de Adafruit IO.

    El conteo sigue funcionando sin internet, pero los requests HTTPS son
    síncronos y pueden introducir pausas temporales en las demás tareas.
    """
    print('=== AFORO 100 mm / ADAFRUIT IO / 1 NUCLEO + ASYNCIO ===')
    print('[AJUSTE B] Se restan', AJUSTE_B_EXTRA_MM, 'mm adicionales a B')
    print('[NUBE] Feeds:', FEED_AFORO, 'y', FEED_AFORO_LLENO)
    await asyncio.gather(
        tarea_sensores_y_conteo(),
        tarea_pir(),
        tarea_barrera(),
        tarea_alarma(),
        tarea_monitor(),
        tarea_adafruit_io()
    )


try:
    asyncio.run(principal())
except KeyboardInterrupt:
    print('Detenido desde Thonny')
finally:
    # La máquina PIO solo debe quedar activa mientras hay sonido.
    sm_buzzer.active(0)
    sm_buzzer.exec('set(pins, 0)')
    # Dejar barrera en posicion abierta al detener el programa.
    mover_servo(False)
    servo.deinit()

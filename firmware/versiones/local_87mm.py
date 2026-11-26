"""Proyecto 13: Aforo bidireccional con Raspberry Pi Pico 2 W.

Versión fuente adjunta: 87 mm de ancho libre; prueba LOCAL de un núcleo.
Sensores: 2 VL53L0X en I2C1 (SDA GP2 / SCL GP3), XSHUT A GP7, B GP8.
Otros: PIR GP6, servo GP15 (PWM 50 Hz), buzzer GP14 (salida digital).
Dependencia: vl53l0x.py compatible con set_address y range.

Objetivo: contar cruces A -> B y B -> A y controlar una barrera de maqueta.
Limitaciones: no incluye Wi-Fi, Ubidots, dos núcleos ni voz real.
El buzzer se activa con un nivel fijo; no genera tono para uno pasivo.
No se debe usar como barrera de evacuación de una puerta real.
"""

# TODO: Integrar publicación Wi-Fi/Ubidots y recuperación tras reconexión.
# TODO: Medir el reto de dos núcleos y guardar los resultados reales.
# FIXME: Verificar el ancho físico y la calibración de ambos sensores.

# ============================================================================
# 1. IMPORTACIONES Y COMPATIBILIDAD CON EL FIRMWARE
# ============================================================================
from machine import Pin, PWM, I2C
from vl53l0x import VL53L0X
import time
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

# ====== AJUSTES DEL PROYECTO ======
MAXIMO = 5
# Separacion nominal entre columnas: 8.7 cm = 87 mm.
DISTANCIA_COLUMNAS_MM = 87
# Los limites se calculan automaticamente a partir de la distancia
# LIBRE que mide cada sensor al encender (sin usar offsets fijos).
MARGEN_DETECCION_MM = 20  # ejemplo: 87 - 20 = 67 mm para DETECTAR
MARGEN_LIBERACION_MM = 9  # ejemplo: 87 - 9 = 78 mm para LIBERAR
MUESTRAS_CALIBRACION = 13
CONFIRMACIONES = 3
TIMEOUT_CRUCE_MS = 5000
REPORTE_MS = 1500

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
buzzer = Pin(14, Pin.OUT, value=0)
print('[ACTUADORES] Servo PWM GP15:', servo.freq(), 'Hz; buzzer digital GP14')


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
    print('[CALIBRACION ' + nombre + '] Fondo medido:', fondo,
          'mm; separacion nominal:', DISTANCIA_COLUMNAS_MM, 'mm')
    if abs(fondo - DISTANCIA_COLUMNAS_MM) > 25:
        print('[AVISO ' + nombre + '] El fondo se aleja de los 87 mm nominales.')
        print('Revisa que el sensor apunte a la columna opuesta y no este tapado.')
    if fondo < 55:
        raise RuntimeError('Calibracion ' + nombre + ': fondo demasiado cerca ('
                           + str(fondo) + ' mm). Revisar montaje.')
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
        # La alarma se solicita por EVENTO, no por aforo >= 5 continuamente.
        self.alarma_pendiente = False

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
                    self.alarma_pendiente = True
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
                    if self.aforo == MAXIMO:
                        self.alarma_pendiente = True
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


# Buzzer en nivel digital: no hay señal alterna de tono.
# AVISO: si es pasivo, este patrón puede no sonar; usar variante PIO.
async def silaba(f_inicio, f_final, duracion_ms):
    """Enciende y apaga el buzzer digital durante un intervalo.
    
    Args:
        f_inicio, f_final: Parámetros heredados, no utilizados aquí.
        duracion_ms (int): Duración de la activación digital.
    Returns:
        bool: Si continúa siendo pertinente la alarma por aforo lleno.
    
    No genera una frecuencia acústica: un buzzer pasivo puede callar.
    """
    # Conservamos las duraciones del efecto original. Las frecuencias
    # no se usan porque GP14 es una salida digital independiente del PWM.
    if control.aforo < MAXIMO:
        buzzer.value(0)
        return False
    buzzer.value(1)
    try:
        await asyncio.sleep_ms(duracion_ms)
    finally:
        buzzer.value(0)
    await asyncio.sleep_ms(50)
    return control.aforo >= MAXIMO


async def decir_mensaje_robotico():
    """Emite el patrón rítmico asociado al aforo completo.
    
    No sintetiza voz ni reproduce palabras en inglés; solo pulsos.
    """
    print('[ALARMA] MAXIMUM CAPACITY REACHED (pitidos ritmicos)')
    # MAX-I-MUM
    for f1, f2, ms in ((900, 1400, 250), (1300, 900, 150), (900, 650, 250)):
        if not await silaba(f1, f2, ms):
            return
    await asyncio.sleep_ms(200)
    # CA-PA-CI-TY
    for f1, f2, ms in ((750, 1200, 200), (1200, 950, 200),
                       (1300, 1600, 150), (1100, 750, 250)):
        if not await silaba(f1, f2, ms):
            return
    await asyncio.sleep_ms(200)
# Patrón final: cinco activaciones largas de 850 ms cada una.
    for _ in range(5):
        if not await silaba(1500, 600, 850):
            return
        await asyncio.sleep_ms(150)


# ALERTAS: se activan por eventos, no continuamente en cada ciclo.
async def tarea_alarma():
    """Consume avisos solicitados sin detener el resto del sistema.
    
    La versión digital usa una bandera; la versión PIO usa una cola.
    """
    while True:
        if control.alarma_pendiente:
            control.alarma_pendiente = False
            if control.aforo >= MAXIMO:
                await decir_mensaje_robotico()
            buzzer.value(0)
        else:
            buzzer.value(0)
            await asyncio.sleep_ms(50)

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


# ORQUESTACIÓN: gather mantiene vivas las tareas cooperativas.
async def principal():
    """Inicia las tareas cooperativas del prototipo local.
    
    asyncio alterna tareas en los puntos await; esto no implementa
    todavía un ensayo real de los dos núcleos del RP2350.
    """
    print('=== AFORO LOCAL - 1 NUCLEO CON ASYNCIO / 87 mm ===')
    # Estas tareas cooperan en un núcleo; no equivalen a dos núcleos.
    await asyncio.gather(
        tarea_sensores_y_conteo(),
        tarea_pir(),
        tarea_barrera(),
        tarea_alarma(),
        tarea_monitor()
    )


try:
    asyncio.run(principal())
except KeyboardInterrupt:
    print('Detenido desde Thonny')
finally:
    buzzer.value(0)
    # Dejar barrera en posicion abierta al detener el programa.
    mover_servo(False)
    servo.deinit()
# Firmware

## Versiones disponibles en los archivos del equipo

| Archivo original | Destino propuesto | Descripción |
|---|---|---|
| MAIN_UN_NUCLEO.py | MAIN_UN_NUCLEO.py | Integrada: 100 mm, PIO, HTTPS, un núcleo y seis tareas |
| MAIN_DOS_NUCLEOS.py | MAIN_DOS_NUCLEOS.py | Variante seleccionable de uno/dos núcleos con _thread y PIO |
| Programa_MicroPy_Rasberry_Pi_PICO2W_UN_NUCLEO.py | versiones/local_87mm.py | Anterior: 87 mm, buzzer digital, sin nube |
| WIFI-LLENAR CREDENCIALES.py | pruebas/prueba_wifi.py | Prueba independiente que publica el valor de prueba 1 |

## Dependencias
MicroPython para Pico 2 W con machine, rp2, network, time, gc, ujson y asyncio (o uasyncio); requests (o urequests); controlador vl53l0x.py compatible con range, set_address e io_timeout_ms. Falta el controlador exacto y la versión del firmware probada por el equipo.

## Configuración
El programa principal importa WIFI_NOMBRE, WIFI_CLAVE, AIO_USUARIO y AIO_KEY desde credenciales.py. Usar credenciales.example.py como plantilla y conservar el archivo real fuera del control de versiones. Los feeds existentes se llaman aforo y aforo-lleno. No ejecutar la prueba Wi-Fi contra el dashboard de producción durante una demo: publica un dato ficticio.

La versión integrada y local deben ejecutarse por separado. Los tres archivos fuente han pasado una revisión sintáctica en CPython; esto no acredita ejecución en MicroPython ni funcionamiento físico.

## Observaciones de revisión
- La implementación actual está en un archivo con clases y funciones; falta evaluar separación en módulos sin alterar la versión probada.
- Las solicitudes HTTPS y lecturas I²C son síncronas, aunque se usen tareas asyncio.
- En caso de fallo de sensor, se omite la actualización de los detectores; revisar el reinicio de las confirmaciones y el estado del cruce antes de reanudar.
- El código evalúa la segunda detección antes de comprobar el timeout; comprobar cruces tardíos.
- El informe describe PIO y un núcleo. MAIN_DOS_NUCLEOS.py incorpora la variante dual; para comparar usar el mismo archivo con DOS_NUCLEOS=False y True, PIO constante y condiciones equivalentes. La versión dual publica cada 6 s y la anterior cada 12 s. No hay comparación experimental verificada.
- El firmware original queda sin cambios funcionales hasta que el equipo pruebe las correcciones en la maqueta.

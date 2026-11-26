# Aforo bidireccional de ambientes con Raspberry Pi Pico 2 W

Proyecto 13 · Arquitectura del Computador I (16953) · Universidad ESAN · 2026-2.

## Objetivo
Registrar entradas y salidas en una maqueta de acceso único, calcular la ocupación, controlar una barrera y permitir la consulta remota mediante Adafruit IO. Usuario objetivo: responsable de un aula o laboratorio.

## Funcionamiento
Dos VL53L0X comparten I²C1 (0x30 y 0x31). A → B suma y B → A resta. Se requieren tres confirmaciones, liberación de ambos sensores y un plazo configurado de 5 s. El PIR informa movimiento sin determinar dirección. Capacidad predeterminada: 5. Servo SG90 por PWM de 50 Hz; buzzer por PIO a 1000 Hz. La nube recibe los feeds `aforo` y `aforo-lleno` por HTTPS.

## Versiones de firmware
| Versión | Arquitectura | Estado de evidencia |
|---|---|---|
| MAIN_UN_NUCLEO.py | Un núcleo, seis tareas asyncio, PIO | Versión descrita en el paper y PPT, con capturas HTTP 200 |
| MAIN_DOS_NUCLEOS.py | Modo seleccionable: un núcleo o dos mediante _thread; PIO en ambos | Código recibido y sintaxis revisada; falta confirmar ejecución y comparación controlada |
| Local de 87 mm | Un núcleo, buzzer digital, sin nube | Histórica, no corresponde a la configuración integrada |

En modo dual, el núcleo 0 gestiona la nube y el monitor, y el núcleo 1 realiza adquisición y actuación. Una instantánea protegida por candado comunica los estados. La mejora de rendimiento no está demostrada todavía.

## Repositorio
- [Firmware](firmware/): versiones, dependencias y configuración.
- [Hardware](hardware/): tabla de pines y diagrama lógico.
- [Modelado 3D](modelado_3d/): inventario de piezas y archivos.
- [Documentación](documentacion/): arquitectura, pruebas y limitaciones.
- [Evidencias](evidencias/): inventario del prototipo, dashboard y video.

## Resultados y estado
47 de 50 cruces correctos (94 %) según el informe; no hay desglose individual. El dashboard y consola documentan aforo 5 y HTTP 200. Los 80–120 ms son una estimación teórica, no una medición. El README recibido cita máximos de 124 ms entre ciclos y 83 ms por ciclo en dos núcleos, pero no se adjuntó la captura correspondiente ni una línea base de un núcleo: datos preliminares no verificados.

El ZIP del equipo contiene 14 STL, 2 proyectos 3MF, diagramas, fotografías, paper, PPT y video. Los archivos fuente y binarios deben incorporarse mediante la carga del paquete organizado.

## Pendientes antes de entregar
- Incorporar archivos originales y controlador exacto vl53l0x.py.
- Confirmar si el reto evaluado será PIO o dos núcleos; armonizar paper, PPT y código.
- Medir la comparación antes/después bajo condiciones equivalentes.
- Validar calibración de 100 mm, reconexión Wi-Fi, alerta remota y casos límite.
- Reducir el PDF de 7 a 6 páginas como máximo, declarar uso de IA y confirmar códigos de integrantes.
- Video original: 133,77 s; entregar versión de 120 s o menos revisada por el equipo.
- Solicitar CAD editable: STL y 3MF no prueban que se disponga del archivo paramétrico original.

Maqueta académica, no sistema de evacuación. No subir contraseñas ni tokens. Los diagramas de conexiones deben verificarse con el montaje real y el docente.

## Equipo
Richard Ernesto Arroyo Torres · Pool Alejandro Villena Romero · Sebastián Sánchez Malca · Alvaro Gonzalo Matias Montero Chacon.

Fuentes: ZIP del equipo (26/11/2026), informe, presentación, firmware y guía del curso. Documentación organizada con asistencia de IA; declarar su utilización en el paper.

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
| MAIN_DOS_NUCLEOS.py | Modo seleccionable: un núcleo o dos mediante _thread; PIO en ambos | Ejecución física en ambos modos documentada por capturas de Thonny |
| Local de 87 mm | Un núcleo, buzzer digital, sin nube | Histórica, no corresponde a la configuración integrada |

En modo dual, el núcleo 0 gestiona la nube y el monitor, y el núcleo 1 realiza adquisición y actuación. Una instantánea protegida por candado comunica los estados. La comparación preliminar muestra una reducción del intervalo máximo entre inicios de ciclo del 92,69 % en reposo.

## Repositorio
- [Firmware](firmware/): versiones, dependencias y configuración.
- [Hardware](hardware/): tabla de pines y diagrama lógico.
- [Modelado 3D](modelado_3d/): inventario de piezas y archivos.
- [Documentación](documentacion/): arquitectura, pruebas y limitaciones.
- [Evidencias](evidencias/): inventario del prototipo, dashboard y video.

## Resultados y estado
47 de 50 cruces correctos (94 %) según el informe; no hay desglose individual. El dashboard y consola documentan aforo 5 y HTTP 200. Los 80–120 ms son una estimación teórica, no una medición. El 26/11/2026 se recibieron capturas de Thonny del mismo firmware seleccionable con `DOS_NUCLEOS=False` y `True`. En reposo (aforo 0, PIR 0), con Wi-Fi conectado y HTTP 200, se observaron máximos acumulados de 1655 ms (un núcleo) y 121 ms (dos núcleos), una reducción del 92,69 %; la duración máxima del ciclo fue 76 y 81 ms respectivamente, con 0 fallos de lectura en ambos registros. No se conoce la duración exacta de los ensayos ni hay repeticiones o cruces comparables documentados; los conteos de ciclos no se usan para estimar rendimiento. El resultado es preliminar y no equivale a una medición de latencia extremo a extremo.

El repositorio contiene los programas fuente, 14 STL, 2 proyectos 3MF, diagramas, fotografías, paper, PPT y video. Se comprobó su presencia en la rama main.

## Pendientes antes de entregar
- Confirmar la versión exacta de MicroPython. El controlador exacto ya está incluido.
- Confirmar con el docente el reto evaluado y validar que los entregables revisados coincidan con la versión demostrada.
- Comparación preliminar registrada; repetir con duración y cruces iguales si se requiere una validación más rigurosa.
- Calibración de 100 mm documentada; revisar orientación del sensor B (advertencia de desviación). Verificar reconexión Wi-Fi, alerta remota y casos límite.
- Confirmar códigos de integrantes si son requeridos y revisar el paper corregido con el equipo.
- Verificar claridad del video editado de aproximadamente 117 s (aceleración 14 %); no utilizarlo como medición experimental.
- Los 14 STL y 2 proyectos 3MF cubren los formatos de impresión entregados; el CAD paramétrico sería adicional si el docente lo solicita.

Maqueta académica, no sistema de evacuación. No subir contraseñas ni tokens. Los diagramas de conexiones deben verificarse con el montaje real y el docente.

## Equipo
Richard Ernesto Arroyo Torres · Pool Alejandro Villena Romero · Sebastián Sánchez Malca · Alvaro Gonzalo Matias Montero Chacon.

Fuentes: ZIP del equipo (26/11/2026), informe, presentación, firmware y guía del curso. Documentación organizada con asistencia de IA; declarar su utilización en el paper.

## Entregables revisados
- [Paper PDF](documentacion/paper/INFORME_MODULO_13_AFORO_BIDIRECCIONAL.pdf) y [Word editable](documentacion/paper/INFORME_MODULO_13_AFORO_BIDIRECCIONAL.docx).
- [Presentación](documentacion/presentacion/Control_de_aforo.pptx).
- [Video de demostración](evidencias/video/demo_117s.mp4).
- [Diagrama de conexiones](hardware/diagrama_conexiones.png).
- [Firmware de un núcleo](firmware/MAIN_UN_NUCLEO.py) y [variante de dos núcleos](firmware/MAIN_DOS_NUCLEOS.py).
- [Modelos STL](modelado_3d/STL/) y [proyectos 3MF](modelado_3d/3MF/).
- [Mediciones experimentales](documentacion/resultados_1_vs_2_nucleos.csv) · [Análisis y gráfico](documentacion/RESULTADOS_EXPERIMENTALES.md). Las versiones anteriores del paper y PPT deben sustituirse por las actualizadas.

Carga comprobada en main el 26/11/2026; la presencia de archivos no acredita la ejecución física del prototipo.

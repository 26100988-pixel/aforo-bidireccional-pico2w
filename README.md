# Aforo bidireccional de ambientes con Raspberry Pi Pico 2 W

Proyecto 13 · Arquitectura del Computador I (16953) · Universidad ESAN · 2026-2.

## Objetivo
Registrar entradas y salidas en una maqueta de acceso único, calcular la ocupación, controlar una barrera y permitir la consulta remota mediante Adafruit IO. Usuario objetivo: responsable de un aula o laboratorio.

## Funcionamiento
Dos VL53L0X comparten I²C1; sus direcciones son 0x30 y 0x31. A → B suma una entrada y B → A resta una salida. Se confirman tres lecturas, se espera liberar ambos sensores y se cancela un intento incompleto tras 5 s. El PIR informa movimiento sin decidir la dirección. El límite predeterminado es cinco ocupantes. El servo SG90 controla la barrera y el buzzer genera avisos mediante PIO de 1000 Hz.

La versión integrada usa un núcleo, MicroPython, seis tareas cooperativas con asyncio y HTTPS hacia los feeds `aforo` y `aforo-lleno` de Adafruit IO.

## Organización
- [Firmware](firmware/): versiones, dependencias y configuración.
- [Hardware](hardware/): componentes y diagrama lógico de conexiones.
- [Modelado 3D](modelado_3d/): descripción de las 14 piezas y archivos pendientes.
- [Documentación técnica](documentacion/): arquitectura, PIO y resultados.
- [Evidencias](evidencias/): inventario de fotografías y capturas.

## Resultados reportados
47 de 50 cruces correctos (94 %). Tres fallos sin desglose. Se reporta respuesta correcta con límites de 3, 5 y 7. El informe y la presentación incluyen evidencia del marco ensamblado, dashboard con aforo 5 y respuestas HTTP 200 de ambos feeds. La confirmación de presencia de 80–120 ms es teórica, no una latencia medida.

## Estado y límites
- [x] Documentar arquitectura, componentes, conexiones y resultados reportados.
- [x] Identificar PIO como reto implementado en la versión integrada.
- [ ] Incorporar y comprobar en la placa el firmware original y la librería compatible vl53l0x.py.
- [ ] Incorporar CAD/STL/3MF originales, informe y presentación.
- [ ] Registrar calibración del montaje de 100 mm y comprobar reconexión Wi-Fi.
- [ ] Medir antes/después de PIO y registrar datos reales.
- [ ] Verificar modularidad, casos de falsos positivos y demo final.

El sistema es una maqueta académica, no un dispositivo de seguridad o evacuación. La ocupación no persiste tras reinicio y HTTPS puede bloquear temporalmente las tareas. No subir contraseñas o tokens. Ver [firmware](firmware/) para la configuración.

## Equipo
Richard Ernesto Arroyo Torres · Pool Alejandro Villena Romero · Sebastián Sánchez Malca · Alvaro Gonzalo Matias Montero Chacon.

## Fuentes
Informe_modulo_13.docx, Control_de_aforo.pptx, MAIN_UN_NUCLEO.py, versión local de 87 mm y Guía del Proyecto Final Pico 2 W 2026-2. Documentación organizada con asistencia de IA; validar con el equipo y declarar el uso en el paper.

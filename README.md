# Sistema IoT de aforo bidireccional de ambientes

Proyecto final de Arquitectura del Computador I (16953) — Universidad ESAN, semestre 2026-2.

## Objetivo

Desarrollar un sistema embebido con Raspberry Pi Pico 2 W que registre entradas y salidas de personas, calcule la ocupación de un ambiente y publique información en la nube para facilitar el control de aforo.

## Funcionamiento previsto

1. Los sensores detectan el paso de una persona.
2. El orden de detección permite distinguir entrada y salida.
3. El microcontrolador actualiza el contador de ocupación.
4. El sistema publica la telemetría y genera una alerta o acción cuando corresponde.

Este flujo describe el diseño previsto; su implementación y validación integral están pendientes de documentar.

## Hardware

| Componente | Función | Estado de documentación |
| --- | --- | --- |
| Raspberry Pi Pico 2 W (RP2350) | Procesamiento y conectividad Wi-Fi | Plataforma del proyecto |
| Sensor A | Detección del paso | Modelo y conexiones por confirmar |
| Sensor B (VL53L0X) | Detección de distancia mediante ToF | Modelo informado por el equipo; conexiones por confirmar |
| Actuador | Alerta o acción de control | Modelo por confirmar |
| Pieza 3D | Integración física de componentes | CAD/STL pendientes de incorporar |

## Organización del repositorio

| Carpeta | Contenido |
| --- | --- |
| [firmware](firmware/) | Código MicroPython, controladores y configuración de ejemplo |
| [hardware](hardware/) | Lista de materiales, pines y diagrama de conexiones |
| [modelado_3d](modelado_3d/) | Diseño CAD y archivos STL |
| [documentacion](documentacion/) | Arquitectura, reto del RP2350 y resultados de pruebas |
| [evidencias](evidencias/) | Fotografías del prototipo y capturas del dashboard |

## Instalación y ejecución

Pendiente de incorporar los archivos finales del equipo, dependencias, versión de MicroPython, mapa de pines y procedimiento de configuración. No publicar contraseñas Wi-Fi, tokens ni claves privadas.

## Estado de los requisitos técnicos

- [ ] Incorporar código final comentado y modular.
- [ ] Documentar y validar al menos dos sensores y un actuador.
- [ ] Documentar el protocolo de comunicación y las conexiones.
- [ ] Verificar tareas concurrentes con asyncio.
- [ ] Documentar publicación en la nube, dashboard y alertas.
- [ ] Documentar el reto de arquitectura elegido y medición antes/después.
- [ ] Incorporar CAD/STL y evidencia de la pieza impresa.
- [ ] Registrar pruebas de integración, falsos positivos y reconexión Wi-Fi.

Las casillas indican documentación o verificación pendiente en este repositorio, no necesariamente trabajo pendiente del equipo.

## Integrantes

Pendiente de completar con los nombres y responsabilidades confirmados por el equipo.

## Referencia

Guía del proyecto final — Arquitectura del Computador I, Universidad ESAN, 2026-2.

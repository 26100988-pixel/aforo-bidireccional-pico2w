# Revisión de entrega

- Paper corregido: seis páginas, con referencias y declaración de uso de IA. Presentación corregida: 12 diapositivas. Se describe el firmware de uno y dos núcleos, distinguiendo los resultados históricos de la comparación pendiente. Los códigos universitarios se omitieron por discrepancias y privacidad; verificar los datos antes de entregar si el docente los exige.
- Video abreviado a aproximadamente 117 s mediante aceleración del 14 %. Revisar la claridad; no usar para medir latencia.
- Se conservaron los programas originales para evitar cambiar el comportamiento de la maqueta sin pruebas físicas. Los nombres de las versiones y la configuración de ejemplo no contienen credenciales reales.
- El diagrama debe cotejarse con el montaje físico. La simulación virtual es referencial y no representa los sensores ToF reales.
- Se incluyen 14 STL y 2 proyectos 3MF; falta el CAD editable original.

## Pendientes imprescindibles

1. Conseguir `vl53l0x.py` exacto y confirmar la versión de MicroPython.
2. Acordar con el docente el reto final. Para comparar núcleos, ejecutar el mismo `MAIN_DOS_NUCLEOS.py` con `DOS_NUCLEOS=False` y `True`; mantener PIO, duración, carga y condiciones iguales. Registrar mediciones en el CSV incluido. No usar los máximos preliminares sin registros ni fabricar una línea base.
3. Validar calibración de 100 mm, falsos positivos, reconexión Wi-Fi y alerta remota. Revisar detecciones tardías y recuperación ante fallos de lectura antes de cambiar el firmware.
4. Adjuntar CAD original y confirmar códigos de integrantes si son requeridos.
5. Revisar el paper y el PPT con el equipo; completar la declaración de IA si existieron otros usos.

## Carga en GitHub

Descomprimir el paquete y cargar sus cinco carpetas en la raíz del repositorio existente. No subir el ZIP como sustituto de los archivos. No reemplazar los README ni el .gitignore existentes. Las credenciales reales deben permanecer fuera del repositorio. Confirmar que GitHub conserva los archivos originales y las versiones revisadas del paper y PPT.

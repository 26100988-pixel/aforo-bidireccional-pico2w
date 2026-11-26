# Revisión de entrega

- Paper corregido: seis páginas, con referencias y declaración de uso de IA. Presentación corregida: 12 diapositivas. Se describe el firmware de uno y dos núcleos, distinguiendo resultados históricos y arquitectura dual; las nuevas mediciones constan en RESULTADOS_EXPERIMENTALES.md y el CSV, y se cargaron los archivos binarios actualizados. Los códigos universitarios se omitieron por discrepancias y privacidad; verificar los datos antes de entregar si el docente los exige.
- Video abreviado a aproximadamente 117 s mediante aceleración del 14 %. Revisar la claridad; no usar para medir latencia.
- Se conservaron los programas originales para evitar cambiar el comportamiento de la maqueta sin pruebas físicas. Los nombres de las versiones y la configuración de ejemplo no contienen credenciales reales.
- El diagrama debe cotejarse con el montaje físico. La simulación virtual es referencial y no representa los sensores ToF reales.
- Se incluyen 14 STL y 2 proyectos 3MF; el CAD paramétrico original no se ha localizado y solo se solicitaría si el docente lo requiere.

## Pendientes imprescindibles

1. Controlador exacto recibido e incluido con aviso MIT; confirmar versión de MicroPython.
2. Comparación preliminar realizada: 1655/121 ms, 76/81 ms, 0/0 fallos. Registrar duración y repeticiones con carga equivalente si se requiere mayor rigor. Confirmar con el docente el reto final.
3. Calibración de 100 mm registrada; revisar orientación B, falsos positivos, reconexión Wi-Fi y alerta remota. Revisar detecciones tardías y recuperación ante fallos de lectura antes de cambiar el firmware.
4. Confirmar códigos de integrantes y acceso del docente; CAD paramétrico solo si lo requiere.
5. Revisar el paper y el PPT con el equipo; completar la declaración de IA si existieron otros usos.

## Carga en GitHub

Carga comprobada el 26/11/2026: cinco capturas nuevas, paper DOCX y PDF, y PPTX actualizados en sus rutas. Los originales de firmware se conservan. Mantener las credenciales reales fuera del repositorio.

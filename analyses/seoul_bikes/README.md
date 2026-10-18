# Bicicletas en Seúl, 2018

Pregunta de mantenimiento: en los días hábiles de 2018, ¿a qué hora entre las 8 a.m. y las 5 p.m. hay menos bicicletas alquiladas?

El archivo de origen no se redistribuye. En esta máquina está en `D:\Coursera\Course 2\Seoul bicycle rental dataset - Seoul bicycle rental dataset.csv`. Otra ruta se indica con `SEOUL_CSV`.

## Corte

- Año 2018.
- Lunes a viernes.
- La ventana de mantenimiento es de las 8 a.m. a las 5 p.m. inclusive.
- El promedio de cada hora es la media de `Rented Bike Count` en ese corte. Pandas calcula la media. Superset dibuja la columna.

## Resultado

Entre las 8 a.m. y las 5 p.m., la media más baja es las **10 a.m.**, con 548.5 bicicletas. A las 8 a.m. la media es 1314.0 y a las 5 p.m. es 1204.0.

Las 10 a.m. son la hora más baja de esa ventana en **171 de 240** jornadas y en **41 de 48** semanas ISO. En 23 jornadas el mínimo es las 8 a.m.

El promedio de las 10 a.m. no dice que todas las mañanas estén vacías. Por eso el script también deja la serie hora por hora, semana por semana y jornada por jornada.

## Cómo correrlo

Hace falta el Superset local descrito en `deploy/superset.md`. El script reescribe el tablero de Seúl.

```powershell
python analyses/seoul_bikes/seoul_detail.py
```

Las tablas pequeñas que el script carga quedan en `outputs/`.

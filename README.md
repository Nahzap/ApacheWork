# ApacheWork

Estudios reproducibles en Python. Apache Superset solo dibuja tablas que pandas y numpy ya dejaron agregadas.

Dos casos, los dos salidos de un flujo de Tableau y rehechos para poder auditar la cuenta:

- [Bicicletas en Seúl, 2018](analyses/seoul_bikes/README.md). Dentro del horario laboral, las 10 a.m. son la hora con menos alquileres: 548.5 de media, y la hora más baja en 171 de 240 jornadas.
- [Rayos en Estados Unidos, 2009-2018](analyses/lightning/README.md). El archivo pasa de 30.1 a 44.6 millones de rayos (+48%). No muestra una mudanza de la costa este al centro, ni una concentración en los condados con más hogares por km².

## Cómo está armado

```
analyses/seoul_bikes/     corte, promedios y publicación del tablero
analyses/lightning/       totales, territorio, censo y mapas
deploy/superset.md        cómo levantar el Superset local
```

Python hace el filtro, la agregación y las figuras de revisión. Postgres recibe el resultado por `\copy`. El gráfico de Superset lee una columna. No hay lógica de negocio en el SQL del dashboard.

Los mapas de rayos comparten un solo fondo, OpenStreetMap con MapLibre. El color va encima de los nombres de ciudades y estados. El tooltip muestra latitud y después longitud.

## Entorno

Python 3.11. Dependencias fijadas en `requirements.txt`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Los CSV de origen no están en el repositorio. Las rutas de esta máquina y las variables `SEOUL_CSV` y `LIGHTNING_CSV` están en el README de cada estudio. El censo y los shapefiles se descargan al correr el estudio de rayos.

## Superset

El clon de Apache Superset y el disco de Docker quedan fuera de git. La guía de arranque y los tableros locales están en [deploy/superset.md](deploy/superset.md).

## Qué no entra en este repositorio

- El árbol upstream de Superset y `docker-data/`.
- Los microdatos de rayos y de bicicletas.
- Los extractos del Census Bureau y los polígonos generados.
- El gimnasio de práctica que está en `practice/` y `Docs/` en la máquina local.

# Rayos en Estados Unidos, 2009-2018

El archivo tiene 12,875,911 filas: `date`, `number_of_strikes`, `x_coord` (longitud) y `y_coord` (latitud). La grilla nativa es de 0.1°. Solo hay cuatro años completos, de enero a diciembre: 2009, 2012, 2015 y 2018. Los otros años del título no están y no se dibujan como cero.

El CSV de origen no se redistribuye. En esta máquina está en `D:\Coursera\Course 2\tableau_main_2009_to_2018.csv`. Otra ruta se indica con `LIGHTNING_CSV`.

## Tres frases del video, medidas

**“Lightning strikes in the U.S. have increased 50% over the last decade.”**

En todo el archivo, 2009 suma 30.1 millones y 2018 suma 44.6 millones: +48%. El video anota 30.1M y 45M, y redondea el aumento a 50%. En el recorte continental (latitud 24.5 a 49.5, longitud −125 a −66.5) el paso es de 29.2M a 39.4M, +35%. 2012 queda en 28.8M, por debajo de 2009. No es una subida año a año.

**“Lightning strikes have moved from the East Coast to the Central Mainlands over the last decade.”**

Dentro del continente, la costa este (longitud ≥ −83) pasa de 23.3% a 21.3% y el centro (−103 a −90) se queda en 42.3%. En millones, la costa este sube de 6.8 a 8.4 y el centro de 12.3 a 16.7. El centro de masa se mueve unos 62 km al oeste, de (−91.76, 34.78) a (−92.43, 34.68). Las dos regiones ganan rayos. El cambio de lugar que sí aparece en el archivo está fuera del recorte: al sur de 24.5° se pasa de 0.6M a 4.4M.

**“Most number of lightning strikes in 2018 happened in densely populated household areas.”**

El archivo de rayos no trae hogares. Se unieron el American Community Survey 2018 de 5 años (tablas B11001, hogares, y B01003, población) y los límites cartográficos TIGER 2018. En los condados, el cuartil con más hogares por km² concentra el 79% de los hogares, el 13% de la tierra y el 19% de los rayos que caen dentro de un condado. La correlación de rangos entre hogares por km² y rayos por km² es −0.01.

En los tractos de Texas, Oklahoma y Kansas el mismo cuartil concentra el 27% de los hogares, el 0.4% de la tierra y el 0.5% de los rayos. Por estado, la parte de rayos en ese cuartil es Texas 0.6%, Oklahoma 0.6% y Kansas 0.2%. La asignación de cada celda de 0.1° a los tractos reparte 16 puntos interiores, porque un tracto urbano es más chico que la celda.

Los rayos siguen el territorio. No se concentran en los barrios con más hogares por km².

## Mapas

La longitud va primero en la geometría de deck.gl, porque ese es el orden del mapa. El texto que se copia a Google Maps va al revés: latitud, longitud. Una celda de Dallas es `32.78, -96.80`. Si se pega primero la longitud, Google lee una latitud imposible y lleva el punto hacia la Antártida.

El fondo es OpenStreetMap vía MapLibre. Condados y tractos se dibujan encima, con opacidad 46, para que el nombre del lugar quede debajo del color.

## Orden de ejecución

Cada script publica en Superset. Hay que correrlos en este orden, porque el último deja el tablero en el estado publicado:

```powershell
python analyses/lightning/lightning_story.py
python analyses/lightning/lightning_territory.py
python analyses/lightning/lightning_basemap.py
python analyses/lightning/lightning_labels.py
```

`lightning_story.py` reescribe los gráficos anuales. `lightning_territory.py` baja el ACS y los shapefiles a `outputs/census/` (eso no se versiona) y arma condados y tractos. `lightning_basemap.py` asigna cada celda de 0.1° a un condado. `lightning_labels.py` suma 2009 por condado, pasa todos los mapas al mismo fondo y quita del tablero las cuadrículas que tapaban los nombres.

## Location Metrics

El segundo tablero, `Location Metrics`, sale de `location_metrics.py`. El mapa usa los condados del territorio, el mismo fondo con los nombres debajo del color. Cada condado lleva la cantidad de rayos de sus celdas. Es una sola consulta, y mover el mapa no la repite. **Interactive Filter** elige el año y mueve las tres cifras de **Metrics for the Year**: total, promedio y máximo. Un clic en un lugar mueve solo **Location Metrics**. Otro clic vuelve a mostrar todos los lugares. El fondo y el orden latitud, longitud son los mismos que en el tablero anterior.

```powershell
python analyses/lightning/location_metrics.py
```

## Qué queda en el repositorio

| Ruta | Contenido |
| --- | --- |
| `figures/` | Seis figuras de revisión, hechas con seaborn |
| `outputs/annual.csv` | Totales, regiones y centro de masa de los cuatro años |
| `outputs/summary.json` | El mismo resumen en JSON |
| `outputs/household_summary.json` | Cuartiles de hogares y correlación |
| `outputs/lightning_household_quartile.csv` | Tabla larga de esos cuartiles |
| `data/us-states.json` | Contorno estatal usado en el primer mapa de revisión |

Las tablas de celdas y los polígonos se regeneran. Pesan decenas de megabytes y no hacen falta para leer el resultado.

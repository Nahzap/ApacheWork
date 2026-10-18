# Superset local

Los estudios publican tableros en un Apache Superset local. El clon upstream vive en `superset/` de esta máquina y no entra en este repositorio: es el árbol de https://github.com/apache/superset. El disco de Docker Desktop tampoco entra.

## Arranque

Desde el clon local:

```powershell
cd D:\ApacheWork\superset
docker compose -f docker-compose-non-dev.yml up -d
```

La interfaz queda en http://127.0.0.1:8088. El compose de desarrollo usa `admin` / `admin`. Esa contraseña es solo para la máquina local. Si el puerto queda expuesto, cámbiala.

Postgres está en el contenedor `superset_db`, base `examples`, usuario de lectura `examples`. Los scripts crean las tablas con `docker cp` y `\copy`, y conceden `SELECT` a `examples`. Superset no agrega: lee columnas que Python ya dejó calculadas.

## Tableros

| Estudio | Título | Ruta local |
| --- | --- | --- |
| Bicicletas en Seúl, 2018 | Seoul: horarios de mantenimiento de bicicletas (2018) | http://127.0.0.1:8088/superset/dashboard/12/ |
| Rayos en Estados Unidos, 2009-2018 | Historia: rayos en Estados Unidos, 2009-2018 | http://127.0.0.1:8088/superset/dashboard/13/ |

Los identificadores 12 y 13 son los de esta instalación. Otra base de metadatos les asigna otros números. Los scripts buscan el tablero por título.

## Mapas

Todos los mapas del estudio de rayos usan MapLibre sobre teselas de OpenStreetMap. El color del rayo o de los hogares va encima, con opacidad 46, para que el nombre del lugar siga leyéndose. El tooltip imprime latitud y después longitud, que es el orden de Google Maps.

OpenStreetMap pide un uso moderado de sus teselas. Este tablero local pide unas pocas teselas por mapa.

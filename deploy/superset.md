# Local Superset

The studies publish dashboards to a local Apache Superset. The upstream clone lives in `superset/` on this machine and is not part of this repository: it is the tree from https://github.com/apache/superset. The Docker Desktop disk is not included either.

## Startup

From the local clone:

```powershell
cd D:\ApacheWork\superset
docker compose -f docker-compose-non-dev.yml up -d
```

The interface is at http://127.0.0.1:8088. The development compose uses `admin` / `admin`. That password is only for the local machine. Change it if the port is exposed.

Postgres is in the `superset_db` container, database `examples`, read-only user `examples`. The scripts create the tables with `docker cp` and `\copy`, and grant `SELECT` to `examples`. Superset does not aggregate: it reads columns Python has already computed.

## Dashboards

| Study | Title | Local path |
| --- | --- | --- |
| Seoul bike rentals, 2018 | Seoul: weekday bike-maintenance hours (2018) | http://127.0.0.1:8088/superset/dashboard/12/ |
| Lightning in the United States, 2009-2018 | Lightning history: United States, 2009-2018 | http://127.0.0.1:8088/superset/dashboard/13/ |

Identifiers 12 and 13 belong to this installation. Another metadata database assigns different numbers. The scripts find a dashboard by title. A board already published under an older title stays as it is until that script is run again.

## Maps

Every map in the lightning study uses MapLibre on OpenStreetMap tiles. Strike or household color sits on top, at opacity 46, so the place name stays readable. The tooltip prints latitude, then longitude, which is the Google Maps order.

OpenStreetMap asks for moderate use of its tiles. This local dashboard requests a few tiles per map.

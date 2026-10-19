"""Interactive location dashboard for the lightning file.

The map is one mark per half-degree cell. That query runs once; panning
does not ask for the data again. The year filter updates Metrics for
the Year. A click updates Location Metrics only. Python prepares the
cells; Superset only draws them.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "territory", Path(__file__).with_name("lightning_territory.py")
)
territory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(territory)

DASHBOARD_TITLE = "Location Metrics"
TABLE = "lightning_location_points"
STYLE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
US_VIEW = {"longitude": -97.2, "latitude": 38.4, "zoom": 3.7, "bearing": 0, "pitch": 0}
YEARS = ("2009", "2012", "2015", "2018")


def accumulate():
    parts = []
    rows = 0
    for chunk in pd.read_csv(
        territory.CSV_SRC,
        usecols=["date", "number_of_strikes", "x_coord", "y_coord"],
        chunksize=1_000_000,
    ):
        rows += len(chunk)
        year = chunk["date"].str.slice(0, 4)
        mask = year.isin(YEARS)
        if not mask.any():
            continue
        part = chunk.loc[mask]
        frame = pd.DataFrame(
            {
                "year": year.loc[mask].to_numpy(),
                "lon": np.round(part["x_coord"].to_numpy(np.float64), 1),
                "lat": np.round(part["y_coord"].to_numpy(np.float64), 1),
                "strikes": part["number_of_strikes"].to_numpy(np.float64),
            }
        )
        grouped = frame.groupby(["year", "lon", "lat"], as_index=False).agg(
            strikes_sum=("strikes", "sum"),
            n_obs=("strikes", "size"),
            strikes_max=("strikes", "max"),
        )
        parts.append(grouped)
        print("rows", rows, "chunks", len(parts), flush=True)
    cells = pd.concat(parts, ignore_index=True)
    cells = cells.groupby(["year", "lon", "lat"], as_index=False).agg(
        strikes_sum=("strikes_sum", "sum"),
        n_obs=("n_obs", "sum"),
        strikes_max=("strikes_max", "max"),
    )
    print("cells", len(cells), "strikes", round(cells["strikes_sum"].sum()), flush=True)
    return cells


def square(lat, lon, half=0.16):
    ring = [
        [round(lon - half, 4), round(lat - half, 4)],
        [round(lon + half, 4), round(lat - half, 4)],
        [round(lon + half, 4), round(lat + half, 4)],
        [round(lon - half, 4), round(lat + half, 4)],
        [round(lon - half, 4), round(lat - half, 4)],
    ]
    return json.dumps({"type": "Polygon", "coordinates": [ring]}, separators=(",", ":"))


def coarsen(frame):
    frame = frame.copy()
    frame["latitude"] = np.round(frame["latitude"].to_numpy(np.float64) * 2) / 2
    frame["longitude"] = np.round(frame["longitude"].to_numpy(np.float64) * 2) / 2
    frame = frame.groupby(["year_label", "latitude", "longitude"], as_index=False).agg(
        strikes_sum=("strikes_sum", "sum"),
        n_obs=("n_obs", "sum"),
        strikes_max=("strikes_max", "max"),
    )
    frame["google"] = [
        f"{lat:.1f}, {lon:.1f}"
        for lat, lon in zip(frame["latitude"], frame["longitude"])
    ]
    frame["polygon"] = [
        square(lat, lon) for lat, lon in zip(frame["latitude"], frame["longitude"])
    ]
    print(frame.groupby("year_label")["strikes_sum"].sum().round(0).to_string(), flush=True)
    print("locations", frame.groupby(["latitude", "longitude"]).ngroups, flush=True)
    return frame[
        [
            "year_label",
            "latitude",
            "longitude",
            "google",
            "polygon",
            "strikes_sum",
            "n_obs",
            "strikes_max",
        ]
    ]


def points_frame(cells):
    return coarsen(
        pd.DataFrame(
            {
                "year_label": cells["year"].astype(str),
                "latitude": cells["lat"],
                "longitude": cells["lon"],
                "strikes_sum": cells["strikes_sum"],
                "n_obs": cells["n_obs"],
                "strikes_max": cells["strikes_max"],
            }
        )
    )


def sql_metric(expression, label):
    return {
        "expressionType": "SQL",
        "sqlExpression": expression,
        "hasCustomLabel": True,
        "label": label,
    }


def big_number(dataset_id, label, expression, number_format, subtitle):
    return {
        "slice_name": label,
        "viz_type": "big_number_total",
        "datasource_id": dataset_id,
        "params": {
            "viz_type": "big_number_total",
            "datasource": f"{dataset_id}__table",
            "metric": sql_metric(expression, label),
            "adhoc_filters": [],
            "subheader": subtitle,
            "header_font_size": 0.4,
            "subheader_font_size": 0.15,
            "y_axis_format": number_format,
        },
    }


def strikes_metric():
    return {
        "aggregate": "SUM",
        "column": {"column_name": "strikes_sum"},
        "expressionType": "SIMPLE",
        "hasCustomLabel": True,
        "label": "Strikes",
        "optionName": "metric_strikes_sum",
        "sqlExpression": None,
    }


def map_chart(dataset_id):
    return {
        "slice_name": "Map",
        "viz_type": "deck_polygon",
        "datasource_id": dataset_id,
        "params": {
            "viz_type": "deck_polygon",
            "datasource": f"{dataset_id}__table",
            "line_column": "polygon",
            "line_type": "json",
            "metric": strikes_metric(),
            "adhoc_filters": [],
            "row_limit": 20000,
            "filter_nulls": True,
            "map_renderer": "maplibre",
            "maplibre_style": STYLE,
            "viewport": US_VIEW,
            "autozoom": False,
            "color_scheme_type": "linear_palette",
            "linear_color_scheme": "schemeYlOrRd",
            "filled": True,
            "stroked": False,
            "opacity": 46,
            "legend_position": "bl",
            "legend_format": ",.0f",
            "cross_filter_column": "place",
            "tooltip_contents": ["place", "google"],
            "tooltip_template": "<div><b>{{place}}</b></div><div>{{google}}</div>",
        },
    }


def publish(frame):
    territory.load_frame(
        frame,
        TABLE,
        "year_label text, latitude double precision, longitude double precision, "
        "google text, polygon text, strikes_sum double precision, "
        "n_obs double precision, strikes_max double precision",
    )
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "superset_db",
            "psql",
            "-U",
            "superset",
            "-d",
            "examples",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE INDEX IF NOT EXISTS lightning_location_points_year "
            "ON public.lightning_location_points (year_label); "
            "CREATE INDEX IF NOT EXISTS lightning_location_points_xy "
            "ON public.lightning_location_points (longitude, latitude); "
            "CREATE INDEX IF NOT EXISTS lightning_location_points_google "
            "ON public.lightning_location_points (google);",
        ],
        check=True,
    )
    login = territory.api(
        "POST",
        "/api/v1/security/login",
        {"username": "admin", "password": "admin", "provider": "db", "refresh": True},
    )
    token = login["access_token"]
    csrf = territory.api("GET", "/api/v1/security/csrf_token/", token=token)["result"]
    databases = territory.api("GET", "/api/v1/database/?q=(page:0,page_size:20)", token=token)["result"]
    database_id = next(item["id"] for item in databases if item["database_name"] == "examples")
    datasets = territory.api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    existing = {item["table_name"]: item["id"] for item in datasets}
    dataset_id = existing.get(TABLE)
    if dataset_id is None:
        created = territory.api(
            "POST",
            "/api/v1/dataset/",
            {"database": database_id, "schema": "public", "table_name": TABLE},
            token=token,
            csrf=csrf,
        )
        dataset_id = created.get("id") or created["result"]["id"]
    else:
        territory.api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)

    dashboards = territory.api("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)", token=token)["result"]
    dashboard = next((item for item in dashboards if item["dashboard_title"] == DASHBOARD_TITLE), None)
    if dashboard is None:
        created = territory.api(
            "POST",
            "/api/v1/dashboard/",
            {"dashboard_title": DASHBOARD_TITLE, "published": True},
            token=token,
            csrf=csrf,
        )
        dashboard_id = created.get("id") or created["result"]["id"]
    else:
        dashboard_id = dashboard["id"]
    print("dashboard", dashboard_id, "dataset", dataset_id, flush=True)

    linked = territory.api("GET", f"/api/v1/dashboard/{dashboard_id}/charts", token=token)["result"]
    by_name = {item["slice_name"]: item for item in linked}
    specs = [
        map_chart(dataset_id),
        big_number(dataset_id, "Total", "SUM(strikes_sum)", ",.0f", "SUM(Strikes)"),
        big_number(
            dataset_id,
            "Average",
            "SUM(strikes_sum) / NULLIF(SUM(n_obs), 0)",
            ",.1f",
            "AVG(Strikes)",
        ),
        big_number(dataset_id, "Maximum", "MAX(strikes_max)", ",.0f", "MAX(Strikes)"),
        big_number(
            dataset_id,
            "Location Metrics",
            "SUM(strikes_sum) / NULLIF(SUM(n_obs), 0)",
            ",.1f",
            "AVG(Strikes)",
        ),
    ]
    aliases = {"Location Metrics": ("Location Metrics", "Average strikes")}
    created_charts = []
    for spec in specs:
        payload = {
            "slice_name": spec["slice_name"],
            "viz_type": spec["viz_type"],
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(spec["params"]),
            "dashboards": [dashboard_id],
        }
        names = aliases.get(spec["slice_name"], (spec["slice_name"],))
        current = next((by_name[name] for name in names if name in by_name), None)
        if current is None:
            result = territory.api("POST", "/api/v1/chart/", payload, token=token, csrf=csrf)
            chart_id = result.get("id") or result["result"]["id"]
        else:
            chart_id = current["id"]
            territory.api("PUT", f"/api/v1/chart/{chart_id}", payload, token=token, csrf=csrf)
        chart = territory.api("GET", f"/api/v1/chart/{chart_id}", token=token)["result"]
        created_charts.append((chart_id, chart["uuid"], spec["slice_name"]))
        print("chart", chart_id, spec["slice_name"], flush=True)

    chart_ids = [chart_id for chart_id, _uuid, _name in created_charts]
    year_chart_ids = chart_ids[1:4]
    location_chart_ids = chart_ids[4:]
    metadata = {
        "native_filter_configuration": [
            {
                "id": "NATIVE_FILTER-year",
                "controlValues": {
                    "enableEmptyFilter": False,
                    "defaultToFirstItem": False,
                    "creatable": False,
                    "multiSelect": True,
                    "searchAllOptions": False,
                    "inverseSelection": False,
                },
                "name": "Interactive Filter",
                "filterType": "filter_select",
                "targets": [{"datasetId": dataset_id, "column": {"name": "year_label"}}],
                "defaultDataMask": {
                    "extraFormData": {
                        "filters": [
                            {"col": "year_label", "op": "IN", "val": list(YEARS)}
                        ]
                    },
                    "filterState": {"value": list(YEARS)},
                    "ownState": {},
                },
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": chart_ids,
                "tabsInScope": [],
                "type": "NATIVE_FILTER",
                "description": "Select a year. All four years start selected.",
            }
        ],
        "cross_filters_enabled": True,
        "global_chart_configuration": {
            "scope": {"rootPath": ["ROOT_ID"], "excluded": year_chart_ids},
            "chartsInScope": location_chart_ids,
        },
        "chart_configuration": {
            str(created_charts[0][0]): {
                "id": created_charts[0][0],
                "crossFilters": {
                    "scope": {"rootPath": ["ROOT_ID"], "excluded": year_chart_ids},
                    "chartsInScope": location_chart_ids,
                },
            }
        },
        "color_scheme": "",
        "label_colors": {},
        "shared_label_colors": {},
        "map_label_colors": {},
        "color_scheme_domain": [],
    }
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": ["ROW-intro", "ROW-main"],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": DASHBOARD_TITLE}},
        "ROW-intro": {
            "type": "ROW",
            "id": "ROW-intro",
            "children": ["MARKDOWN-intro"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "MARKDOWN-intro": {
            "type": "MARKDOWN",
            "id": "MARKDOWN-intro",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-intro"],
            "meta": {
                "width": 12,
                "height": 16,
                "code": "\n".join(
                    [
                        "**Interactive Filter** está a la izquierda. Elegí un año, o dejá los cuatro marcados. Eso actualiza el mapa y **Metrics for the Year**.",
                        "",
                        "Choose a point on the map to view location specific metrics. Otro clic en el mismo punto vuelve a mostrar todos los lugares. El tooltip es latitud, longitud.",
                    ]
                ),
            },
        },
        "ROW-main": {
            "type": "ROW",
            "id": "ROW-main",
            "children": ["CHART-map", "COLUMN-side"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "COLUMN-side": {
            "type": "COLUMN",
            "id": "COLUMN-side",
            "children": [
                "MARKDOWN-year",
                "CHART-total",
                "CHART-average",
                "CHART-maximum",
                "MARKDOWN-location",
                "CHART-location",
            ],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-main"],
            "meta": {"width": 4, "background": "BACKGROUND_TRANSPARENT"},
        },
    }

    def add_markdown(node_id, parent_id, parents, code, width, height):
        layout[node_id] = {
            "type": "MARKDOWN",
            "id": node_id,
            "children": [],
            "parents": parents,
            "meta": {"width": width, "height": height, "code": code},
        }

    def add_chart(node_id, chart, parents, width, height):
        chart_id, chart_uuid, name = chart
        layout[node_id] = {
            "type": "CHART",
            "id": node_id,
            "children": [],
            "parents": parents,
            "meta": {
                "chartId": chart_id,
                "uuid": chart_uuid,
                "sliceName": name,
                "width": width,
                "height": height,
            },
        }

    side_parents = ["ROOT_ID", "GRID_ID", "ROW-main", "COLUMN-side"]
    add_chart(
        "CHART-map",
        created_charts[0],
        ["ROOT_ID", "GRID_ID", "ROW-main"],
        8,
        88,
    )
    add_markdown("MARKDOWN-year", "COLUMN-side", side_parents, "**Metrics for the Year**", 4, 6)
    add_chart("CHART-total", created_charts[1], side_parents, 4, 14)
    add_chart("CHART-average", created_charts[2], side_parents, 4, 14)
    add_chart("CHART-maximum", created_charts[3], side_parents, 4, 14)
    add_markdown(
        "MARKDOWN-location",
        "COLUMN-side",
        side_parents,
        "**Location Metrics**",
        4,
        6,
    )
    add_chart("CHART-location", created_charts[4], side_parents, 4, 16)
    territory.api(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        {
            "dashboard_title": DASHBOARD_TITLE,
            "published": True,
            "position_json": json.dumps(layout),
            "json_metadata": json.dumps(metadata),
        },
        token=token,
        csrf=csrf,
    )
    print("READY", dashboard_id, flush=True)


def from_database():
    import io

    proc = subprocess.run(
        [
            "docker",
            "exec",
            "superset_db",
            "psql",
            "-U",
            "superset",
            "-d",
            "examples",
            "-c",
            "COPY (SELECT year_label, latitude, longitude, strikes_sum, n_obs, strikes_max "
            "FROM public.lightning_location_points) TO STDOUT WITH CSV HEADER",
        ],
        check=True,
        capture_output=True,
    )
    return coarsen(pd.read_csv(io.BytesIO(proc.stdout)))


def main():
    frame = points_frame(accumulate())
    publish(frame)


def bind_territory():
    login = territory.api(
        "POST",
        "/api/v1/security/login",
        {"username": "admin", "password": "admin", "provider": "db", "refresh": True},
    )
    token = login["access_token"]
    csrf = territory.api("GET", "/api/v1/security/csrf_token/", token=token)["result"]
    datasets = territory.api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    dataset_id = next(item["id"] for item in datasets if item["table_name"] == "lightning_location_metrics")
    territory.api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)
    charts = territory.api("GET", "/api/v1/dashboard/14/charts", token=token)["result"]
    specs = {
        spec["slice_name"]: spec
        for spec in (
            map_chart(dataset_id),
            big_number(dataset_id, "Total", "SUM(strikes_sum)", ",.0f", "SUM(Strikes)"),
            big_number(
                dataset_id,
                "Average",
                "SUM(strikes_sum) / NULLIF(SUM(n_obs), 0)",
                ",.1f",
                "AVG(Strikes)",
            ),
            big_number(dataset_id, "Maximum", "MAX(strikes_max)", ",.0f", "MAX(Strikes)"),
            big_number(
                dataset_id,
                "Location Metrics",
                "SUM(strikes_sum) / NULLIF(SUM(n_obs), 0)",
                ",.1f",
                "AVG(Strikes)",
            ),
        )
    }
    for chart in charts:
        spec = specs.get(chart["slice_name"])
        if spec is None:
            continue
        territory.api(
            "PUT",
            f"/api/v1/chart/{chart['id']}",
            {
                "slice_name": spec["slice_name"],
                "viz_type": spec["viz_type"],
                "datasource_id": dataset_id,
                "datasource_type": "table",
                "params": json.dumps(spec["params"]),
                "dashboards": [14],
            },
            token=token,
            csrf=csrf,
        )
        print("chart", chart["id"], spec["slice_name"], flush=True)
    dashboard = territory.api("GET", "/api/v1/dashboard/14", token=token)["result"]
    metadata = json.loads(dashboard["json_metadata"])
    for native_filter in metadata.get("native_filter_configuration", []):
        for target in native_filter.get("targets", []):
            target["datasetId"] = dataset_id
    territory.api(
        "PUT",
        "/api/v1/dashboard/14",
        {
            "dashboard_title": DASHBOARD_TITLE,
            "published": True,
            "position_json": dashboard["position_json"],
            "json_metadata": json.dumps(metadata),
        },
        token=token,
        csrf=csrf,
    )
    print("territory", dataset_id, flush=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "coarse":
        publish(from_database())
    elif len(sys.argv) > 1 and sys.argv[1] == "territory":
        bind_territory()
    else:
        main()

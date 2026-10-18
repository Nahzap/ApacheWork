"""One map framework: OpenStreetMap names under the lightning polygons.

Google Maps reads the first number as latitude. Tooltips now print
latitude, longitude. The deck heatmaps covered those names and used up
the browser's WebGL contexts, so the geographic story stays on the
county and tract polygons only.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "territory", Path(__file__).with_name("lightning_territory.py")
)
territory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(territory)

OUT = territory.OUT
STYLE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
US_VIEW = {"longitude": -97.2, "latitude": 38.4, "zoom": 3.7, "bearing": 0, "pitch": 0}
STATE_VIEWS = {
    "Texas": {"longitude": -99.2, "latitude": 31.4, "zoom": 5.15, "bearing": 0, "pitch": 0},
    "Oklahoma": {"longitude": -97.4, "latitude": 35.55, "zoom": 6.05, "bearing": 0, "pitch": 0},
    "Kansas": {"longitude": -98.3, "latitude": 38.5, "zoom": 6.25, "bearing": 0, "pitch": 0},
}
HEATMAP_CHARTS = {121, 122, 123, 124, 125}


def psql(sql):
    subprocess.run(
        ["docker", "exec", "-i", "superset_db", "psql", "-U", "superset", "-d", "examples", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode(),
        check=True,
    )


def copy_out(query, name):
    sql = f"\\copy ({query}) TO '/tmp/{name}.csv' WITH (FORMAT csv, HEADER true)\n"
    psql(sql)
    subprocess.run(["docker", "cp", f"superset_db:/tmp/{name}.csv", str(OUT / f"{name}.csv")], check=True)
    return pd.read_csv(OUT / f"{name}.csv")


def tooltip(strike_field):
    return (
        "<div><b>{{name}}, {{state}}</b></div>"
        "<div>{{google}}</div>"
        f"<div>Rayos: {{{{{strike_field}}}}}</div>"
        "<div>Hogares por km²: {{household_density}}</div>"
    )


def add_2009():
    points = copy_out(
        "SELECT place, state, strikes FROM public.lightning_map_points WHERE year = 2009",
        "points_2009",
    )
    counties = copy_out(
        "SELECT geoid, name, state FROM public.lightning_county_2018",
        "county_names",
    )
    counties["geoid"] = counties["geoid"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    grouped = points.groupby(["place", "state"], as_index=False)["strikes"].sum()
    counties["place"] = counties["name"] + ", " + counties["state"]
    merged = counties.merge(grouped, on=["place", "state"], how="left")
    merged["strikes"] = merged["strikes"].fillna(0)
    matched = int((merged["strikes"] > 0).sum())
    print("counties with 2009 strikes", matched, "of", len(merged), "sum", round(merged["strikes"].sum()), flush=True)
    csv_path = OUT / "county_strikes_2009.csv"
    merged[["geoid", "strikes"]].rename(columns={"strikes": "strikes_2009"}).to_csv(csv_path, index=False)
    subprocess.run(["docker", "cp", str(csv_path), "superset_db:/tmp/county_strikes_2009.csv"], check=True)
    subprocess.run(["docker", "exec", "superset_db", "chmod", "644", "/tmp/county_strikes_2009.csv"], check=True)
    psql(
        """
ALTER TABLE public.lightning_county_2018 ADD COLUMN IF NOT EXISTS strikes_2009 double precision;
CREATE TEMP TABLE county_strikes_2009 (geoid text, strikes_2009 double precision);
\\copy county_strikes_2009 FROM '/tmp/county_strikes_2009.csv' WITH (FORMAT csv, HEADER true)
UPDATE public.lightning_county_2018 AS county
SET strikes_2009 = incoming.strikes_2009
FROM county_strikes_2009 AS incoming
WHERE county.geoid = incoming.geoid;
UPDATE public.lightning_county_2018 SET strikes_2009 = 0 WHERE strikes_2009 IS NULL;
"""
    )


def apply_style(params, view, strike_field):
    params["map_renderer"] = "maplibre"
    params["maplibre_style"] = STYLE
    params["opacity"] = 46
    params["autozoom"] = False
    params["viewport"] = view
    params["filled"] = True
    params["stroked"] = False
    params["legend_position"] = "bl"
    params["tooltip_contents"] = ["name", "state", "google", "household_density", strike_field]
    params["tooltip_template"] = tooltip(strike_field)
    params["adhoc_filters"] = [
        item for item in params.get("adhoc_filters", []) if item.get("operator") != "NOT IN"
    ]
    return params


def polygon_2009(dataset_id):
    return {
        "viz_type": "deck_polygon",
        "datasource": f"{dataset_id}__table",
        "line_column": "polygon",
        "line_type": "json",
        "metric": territory.metric("strikes_2009", "Rayos"),
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
        "tooltip_contents": ["name", "state", "google", "household_density", "strikes_2009"],
        "tooltip_template": tooltip("strikes_2009"),
    }


def retile_dashboard(layout, chart_id, chart_uuid):
    removed = []
    for key, node in list(layout.items()):
        if not isinstance(node, dict) or node.get("type") != "CHART":
            continue
        if node.get("meta", {}).get("chartId") not in HEATMAP_CHARTS:
            continue
        parent = node["parents"][-1]
        if key in layout.get(parent, {}).get("children", []):
            layout[parent]["children"].remove(key)
        removed.append(key)
        layout.pop(key, None)
    for key, node in list(layout.items()):
        if isinstance(node, dict) and node.get("type") == "ROW" and not node.get("children"):
            layout["GRID_ID"]["children"].remove(key)
            layout.pop(key, None)
    print("removed heatmaps", removed, flush=True)

    county_key = None
    household_key = None
    for key, node in layout.items():
        if not isinstance(node, dict) or node.get("type") != "CHART":
            continue
        chart = node.get("meta", {}).get("chartId")
        if chart == 133:
            county_key = key
        if chart == 134:
            household_key = key
    county_row = layout[county_key]["parents"][-1]
    household_row = layout[household_key]["parents"][-1]
    year_key = f"CHART-{chart_id}"
    layout[year_key] = {
        "type": "CHART",
        "id": year_key,
        "children": [],
        "parents": ["ROOT_ID", "GRID_ID", county_row],
        "meta": {
            "chartId": chart_id,
            "uuid": chart_uuid,
            "sliceName": "Rayos en 2009 sobre el territorio",
            "width": 6,
            "height": 70,
        },
    }
    if household_row == county_row:
        layout[county_row]["children"].remove(household_key)
        new_row = "ROW-territory-households"
        layout[new_row] = {
            "type": "ROW",
            "id": new_row,
            "children": [household_key],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        grid = layout["GRID_ID"]["children"]
        grid.insert(grid.index(county_row) + 1, new_row)
        layout[household_key]["parents"] = ["ROOT_ID", "GRID_ID", new_row]
        layout[household_key]["meta"]["width"] = 12
        layout[household_key]["meta"]["height"] = 70
    if year_key not in layout[county_row]["children"]:
        layout[county_row]["children"].insert(0, year_key)
    for child in layout[county_row]["children"]:
        layout[child]["meta"]["width"] = 12 // len(layout[county_row]["children"])
        layout[child]["meta"]["height"] = 70
    for key, node in layout.items():
        if isinstance(node, dict) and node.get("type") == "MARKDOWN":
            code = node.get("meta", {}).get("code", "")
            old = "El archivo no trae hogares ni población, así que esa frase no se puede comprobar aquí."
            if old in code:
                node["meta"]["code"] = code.replace(
                    old,
                    "Esa frase se comprueba más abajo con los hogares del censo, dibujados sobre el mismo mapa.",
                )
            note = "En el mapa, el nombre del lugar queda debajo de los rayos. El tooltip muestra latitud, longitud, el orden que usa Google Maps."
            if note not in node["meta"]["code"] and "cuartil con más hogares" in node["meta"]["code"]:
                node["meta"]["code"] = node["meta"]["code"].rstrip() + "\n\n" + note


def main():
    add_2009()
    login = territory.api(
        "POST",
        "/api/v1/security/login",
        {"username": "admin", "password": "admin", "provider": "db", "refresh": True},
    )
    token = login["access_token"]
    csrf = territory.api("GET", "/api/v1/security/csrf_token/", token=token)["result"]
    datasets = territory.api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    county_id = next(item["id"] for item in datasets if item["table_name"] == "lightning_county_2018")
    territory.api("PUT", f"/api/v1/dataset/{county_id}/refresh", token=token, csrf=csrf)

    charts = territory.api("GET", "/api/v1/chart/?q=(page:0,page_size:300)", token=token)["result"]
    by_name = {}
    for item in charts:
        by_name.setdefault(item["slice_name"], item)

    title = "Rayos en 2009 sobre el territorio"
    params = polygon_2009(county_id)
    payload = {
        "slice_name": title,
        "viz_type": "deck_polygon",
        "datasource_id": county_id,
        "datasource_type": "table",
        "params": json.dumps(params),
        "dashboards": [13],
    }
    existing = by_name.get(title)
    if existing:
        territory.api("PUT", f"/api/v1/chart/{existing['id']}", payload, token=token, csrf=csrf)
        chart_id = existing["id"]
    else:
        created = territory.api("POST", "/api/v1/chart/", payload, token=token, csrf=csrf)
        chart_id = created.get("id") or created["result"]["id"]
    chart_uuid = territory.api("GET", f"/api/v1/chart/{chart_id}", token=token)["result"]["uuid"]
    print("year chart", chart_id, flush=True)

    updates = {
        133: (US_VIEW, "strikes"),
        134: (US_VIEW, "strikes"),
        135: (STATE_VIEWS["Texas"], "strikes"),
        136: (STATE_VIEWS["Oklahoma"], "strikes"),
        137: (STATE_VIEWS["Kansas"], "strikes"),
    }
    for chart_id_now, (view, field) in updates.items():
        chart = territory.api("GET", f"/api/v1/chart/{chart_id_now}", token=token)["result"]
        current = json.loads(chart["params"])
        apply_style(current, view, field)
        territory.api(
            "PUT",
            f"/api/v1/chart/{chart_id_now}",
            {"params": json.dumps(current)},
            token=token,
            csrf=csrf,
        )
        print("styled", chart_id_now, chart["slice_name"], flush=True)

    dashboard = territory.api("GET", "/api/v1/dashboard/13", token=token)["result"]
    layout = json.loads(dashboard["position_json"])
    metadata = json.loads(dashboard["json_metadata"] or "{}")
    retile_dashboard(layout, chart_id, chart_uuid)
    scope = metadata.setdefault("global_chart_configuration", {}).setdefault("chartsInScope", [])
    for dropped in HEATMAP_CHARTS:
        if dropped in scope:
            scope.remove(dropped)
    if chart_id not in scope:
        scope.append(chart_id)
    territory.api(
        "PUT",
        "/api/v1/dashboard/13",
        {"position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)},
        token=token,
        csrf=csrf,
    )
    print("dashboard updated", flush=True)


if __name__ == "__main__":
    main()

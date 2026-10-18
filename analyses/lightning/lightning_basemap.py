"""Put every lightning map on one labeled basemap.

Google Maps reads the first number as latitude. The old charts showed
longitude first, so -109.25, 29.25 was sent to Antarctica. This script
stores coordinates as latitude, longitude and draws them on MapLibre.
"""

import importlib.util
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "territory", Path(__file__).with_name("lightning_territory.py")
)
territory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(territory)

CSV_SRC = territory.CSV_SRC
OUT = territory.OUT
STYLE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TOOLTIP = (
    "<div><b>{{place}}</b></div>"
    "<div>{{google}}</div>"
    "<div>Rayos: {{weight}}</div>"
)
POLYGON_TOOLTIP = (
    "<div><b>{{name}}, {{state}}</b></div>"
    "<div>Google Maps: <b>{{google}}</b></div>"
    "<div>Rayos: {{strikes}}</div>"
    "<div>Hogares por km²: {{household_density}}</div>"
)


def cells_for_years():
    totals = {}
    rows = 0
    for chunk in pd.read_csv(
        CSV_SRC,
        usecols=["date", "number_of_strikes", "x_coord", "y_coord"],
        chunksize=1_000_000,
    ):
        rows += len(chunk)
        year = chunk["date"].str.slice(0, 4)
        mask = year.isin(["2009", "2018"])
        if not mask.any():
            continue
        part = chunk.loc[mask]
        lon = np.round(part["x_coord"].to_numpy(np.float64), 1)
        lat = np.round(part["y_coord"].to_numpy(np.float64), 1)
        count = part["number_of_strikes"].to_numpy(np.float64)
        years = year.loc[mask].to_numpy()
        frame = pd.DataFrame({"year": years, "lon": lon, "lat": lat, "strikes": count})
        frame = frame[(frame["lat"].between(18, 55)) & (frame["lon"].between(-140, -60))]
        grouped = frame.groupby(["year", "lon", "lat"], sort=False)["strikes"].sum()
        for (year_value, lon_value, lat_value), strikes in grouped.items():
            key = (int(year_value), float(lon_value), float(lat_value))
            totals[key] = totals.get(key, 0.0) + float(strikes)
        print("rows", rows, "cells", len(totals), flush=True)
    return totals


def locate(cells, features):
    index = territory.spatial_index(features, 1.0)
    by_geoid = {feature["geoid"]: feature for feature in features}
    rows = []
    for (year, lon, lat), strikes in cells.items():
        bucket = index.get((int(np.floor(lon)), int(np.floor(lat))), [])
        place = "Fuera de los condados de EE.UU."
        state = "Fuera de EE.UU."
        for feature in bucket:
            minx, miny, maxx, maxy = feature["bbox"]
            if lon < minx or lon > maxx or lat < miny or lat > maxy:
                continue
            if territory.point_in_rings(lon, lat, feature["rings"]):
                state = territory.place_name(feature["state_fips"])
                place = f"{feature['name']}, {state}"
                break
        rows.append(
            {
                "year": year,
                "latitude": lat,
                "longitude": lon,
                "google": f"{lat:.1f}, {lon:.1f}",
                "place": place,
                "state": state,
                "strikes": strikes,
            }
        )
    return pd.DataFrame(rows)


def centroid(polygon_text):
    payload = json.loads(polygon_text)
    coordinates = payload["coordinates"]
    ring = coordinates[0] if payload["type"] == "Polygon" else coordinates[0][0]
    points = np.asarray(ring, dtype=float)
    return float(points[:, 1].mean()), float(points[:, 0].mean())


def add_google(frame):
    centers = frame["polygon"].map(centroid)
    frame = frame.copy()
    frame["latitude"] = [round(item[0], 2) for item in centers]
    frame["longitude"] = [round(item[1], 2) for item in centers]
    frame["google"] = [f"{lat:.2f}, {lon:.2f}" for lat, lon in zip(frame["latitude"], frame["longitude"])]
    return frame


def metric(column, label):
    return territory.metric(column, label)


def deck_heat(dataset_id, title, filters, viewport, radius):
    return {
        "slice_name": title,
        "viz_type": "deck_heatmap",
        "datasource_id": dataset_id,
        "params": {
            "viz_type": "deck_heatmap",
            "datasource": f"{dataset_id}__table",
            "spatial": {"type": "latlong", "lonCol": "longitude", "latCol": "latitude"},
            "size": metric("strikes", "Rayos"),
            "row_limit": 200000,
            "filter_nulls": True,
            "adhoc_filters": filters,
            "intensity": 0.4,
            "radius_pixels": radius,
            "tooltip_contents": ["place", "google"],
            "aggregation": "sum",
            "map_renderer": "maplibre",
            "maplibre_style": STYLE,
            "autozoom": False,
            "viewport": viewport,
            "color_scheme_type": "linear_palette",
            "linear_color_scheme": "schemeYlOrRd",
            "tooltip_template": TOOLTIP,
        },
    }


def main():
    features = territory.download_county_shapes()
    frame = locate(cells_for_years(), features)
    print(frame["google"].head(3).tolist(), "places", frame["place"].nunique(), flush=True)
    sample = frame[(frame["latitude"].between(32.5, 33.1)) & (frame["longitude"].between(-97.1, -96.5))]
    print("dallas sample", sample[["google", "place", "strikes"]].head(3).to_dict(orient="records"), flush=True)
    territory.load_frame(
        frame,
        "lightning_map_points",
        "year integer, latitude double precision, longitude double precision, google text, "
        "place text, state text, strikes double precision",
    )
    county_columns = (
        "geoid text, name text, state text, polygon text, strikes double precision, "
        "households double precision, population double precision, area_km2 double precision, "
        "household_density double precision, population_density double precision, "
        "latitude double precision, longitude double precision, google text"
    )
    for table in ("lightning_county_2018", "lightning_tract_2018"):
        current = pd.read_csv(OUT / f"{table}.csv", dtype={"geoid": str})
        current = add_google(current)
        keep = [
            "geoid",
            "name",
            "state",
            "polygon",
            "strikes",
            "households",
            "population",
            "area_km2",
            "household_density",
            "population_density",
            "latitude",
            "longitude",
            "google",
        ]
        territory.load_frame(current[keep], table, county_columns)

    login = territory.api(
        "POST",
        "/api/v1/security/login",
        {"username": "admin", "password": "admin", "provider": "db", "refresh": True},
    )
    token = login["access_token"]
    csrf = territory.api("GET", "/api/v1/security/csrf_token/", token=token)["result"]
    databases = territory.api("GET", "/api/v1/database/?q=(page:0,page_size:20)", token=token)["result"]
    database_id = next(item["id"] for item in databases if item["database_name"] == "examples")
    existing = {
        item["table_name"]: item["id"]
        for item in territory.api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    }

    def ensure(table_name):
        dataset_id = existing.get(table_name)
        if dataset_id is None:
            created = territory.api(
                "POST",
                "/api/v1/dataset/",
                {"database": database_id, "schema": "public", "table_name": table_name},
                token=token,
                csrf=csrf,
            )
            return created.get("id") or created["result"]["id"]
        territory.api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)
        return dataset_id

    points_id = ensure("lightning_map_points")
    ensure("lightning_county_2018")
    ensure("lightning_tract_2018")
    us_view = {"longitude": -97.2, "latitude": 38.4, "zoom": 3.65, "bearing": 0, "pitch": 0}
    views = {
        "Rayos en 2009": ([{"clause": "WHERE", "expressionType": "SIMPLE", "subject": "year", "operator": "==", "comparator": 2009}], us_view, 8),
        "Rayos en 2018": ([{"clause": "WHERE", "expressionType": "SIMPLE", "subject": "year", "operator": "==", "comparator": 2018}], us_view, 8),
        "Texas 2018": (
            [
                {"clause": "WHERE", "expressionType": "SIMPLE", "subject": "year", "operator": "==", "comparator": 2018},
                {"clause": "WHERE", "expressionType": "SIMPLE", "subject": "state", "operator": "==", "comparator": "Texas"},
            ],
            {"longitude": -99.2, "latitude": 31.4, "zoom": 5.2, "bearing": 0, "pitch": 0},
            12,
        ),
        "Oklahoma 2018": (
            [
                {"clause": "WHERE", "expressionType": "SIMPLE", "subject": "year", "operator": "==", "comparator": 2018},
                {"clause": "WHERE", "expressionType": "SIMPLE", "subject": "state", "operator": "==", "comparator": "Oklahoma"},
            ],
            {"longitude": -97.4, "latitude": 35.55, "zoom": 6.05, "bearing": 0, "pitch": 0},
            12,
        ),
        "Kansas 2018": (
            [
                {"clause": "WHERE", "expressionType": "SIMPLE", "subject": "year", "operator": "==", "comparator": 2018},
                {"clause": "WHERE", "expressionType": "SIMPLE", "subject": "state", "operator": "==", "comparator": "Kansas"},
            ],
            {"longitude": -98.3, "latitude": 38.5, "zoom": 6.25, "bearing": 0, "pitch": 0},
            12,
        ),
    }
    charts = territory.api("GET", "/api/v1/chart/?q=(page:0,page_size:300)", token=token)["result"]
    by_name = {}
    for item in charts:
        by_name.setdefault(item["slice_name"], []).append(item)
    for title, (filters, viewport, radius) in views.items():
        spec = deck_heat(points_id, title, filters, viewport, radius)
        matches = by_name.get(title, [])
        target = matches[0] if matches else None
        payload = {
            "slice_name": title,
            "viz_type": "deck_heatmap",
            "datasource_id": points_id,
            "datasource_type": "table",
            "params": json.dumps(spec["params"]),
        }
        if target is None:
            created = territory.api("POST", "/api/v1/chart/", {**payload, "dashboards": [13]}, token=token, csrf=csrf)
            print("created", title, created.get("id"), flush=True)
            continue
        territory.api("PUT", f"/api/v1/chart/{target['id']}", payload, token=token, csrf=csrf)
        print("updated", target["id"], title, flush=True)
        for extra in matches[1:]:
            territory.api("DELETE", f"/api/v1/chart/{extra['id']}", token=token, csrf=csrf)

    polygon_names = {
        "Territorio: rayos por condado en 2018",
        "Territorio: hogares por km² en 2018",
        "Texas 2018 sobre el territorio",
        "Oklahoma 2018 sobre el territorio",
        "Kansas 2018 sobre el territorio",
    }
    for item in charts:
        if item["slice_name"] not in polygon_names:
            continue
        chart = territory.api("GET", f"/api/v1/chart/{item['id']}", token=token)["result"]
        params = json.loads(chart["params"])
        params["maplibre_style"] = STYLE
        params["opacity"] = 46
        params["autozoom"] = False
        params["adhoc_filters"] = [
            item_filter
            for item_filter in params.get("adhoc_filters", [])
            if item_filter.get("operator") != "NOT IN"
        ]
        params["tooltip_template"] = POLYGON_TOOLTIP
        territory.api(
            "PUT",
            f"/api/v1/chart/{item['id']}",
            {"params": json.dumps(params)},
            token=token,
            csrf=csrf,
        )
        print("polygon", item["id"], item["slice_name"], flush=True)


if __name__ == "__main__":
    main()

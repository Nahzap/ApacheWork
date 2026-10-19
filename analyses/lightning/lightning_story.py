"""Lightning story for 2009-2018, prepared in Python and drawn in Superset.

pandas reads the source file. numpy accumulates the yearly totals, the
regional shares and the map grids. seaborn draws the review figures.
Superset only reads the tables this script writes.
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

BASE = os.environ.get("SUPERSET_URL", "http://127.0.0.1:8088")
ROOT = Path(__file__).resolve().parent
CSV_SRC = Path(os.environ.get(
    "LIGHTNING_CSV",
    r"D:\Coursera\Course 2\tableau_main_2009_to_2018.csv",
))
GEOJSON = ROOT / "data" / "us-states.json"
OUT = ROOT / "outputs"
FIG = ROOT / "figures"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
DASHBOARD_TITLE = "Lightning history: United States, 2009-2018"

YEARS = np.arange(2009, 2019)
LON0, DLON, NLON = -130.0, 0.5, 140
LAT0, DLAT, NLAT = 24.0, 0.5, 56
SLON0, SDLON, NSLON = -106.8, 0.2, 70
SLAT0, SDLAT, NSLAT = 25.6, 0.2, 74

CITIES = {
    "Texas": {
        "Houston": (-95.37, 29.76),
        "Dallas": (-96.80, 32.78),
        "Austin": (-97.74, 30.27),
        "San Antonio": (-98.49, 29.42),
        "El Paso": (-106.49, 31.76),
    },
    "Oklahoma": {
        "Oklahoma City": (-97.52, 35.47),
        "Tulsa": (-95.99, 36.15),
    },
    "Kansas": {
        "Wichita": (-97.34, 37.69),
        "Kansas City": (-94.63, 39.11),
        "Topeka": (-95.68, 39.05),
    },
}


def api(method, path, payload=None, token=None, csrf=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if csrf:
        headers["X-CSRFToken"] = csrf
        headers["Referer"] = BASE + "/"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with OPENER.open(request, timeout=120) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        raise RuntimeError(f"{method} {path} -> {error.code} {detail[:2000]}") from error


def metric(column, label):
    return {
        "aggregate": "SUM",
        "column": {"column_name": column},
        "expressionType": "SIMPLE",
        "hasCustomLabel": True,
        "label": label,
        "optionName": "metric_" + column,
        "sqlExpression": None,
    }


def rings_for(name):
    payload = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feature = next(item for item in payload["features"] if item["properties"]["name"] == name)
    geometry = feature["geometry"]
    if geometry["type"] == "Polygon":
        return [np.asarray(geometry["coordinates"][0], dtype=float)]
    return [np.asarray(polygon[0], dtype=float) for polygon in geometry["coordinates"]]


def points_in_ring(lon, lat, ring):
    x_ring = ring[:, 0]
    y_ring = ring[:, 1]
    inside = np.zeros(lon.shape, dtype=bool)
    previous = len(ring) - 1
    for current in range(len(ring)):
        x1, y1 = x_ring[current], y_ring[current]
        x2, y2 = x_ring[previous], y_ring[previous]
        crosses = ((y1 > lat) != (y2 > lat)) & (
            lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1
        )
        inside ^= crosses
        previous = current
    return inside


def haversine_km(lon1, lat1, lon2, lat2):
    radius = 6371.0
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    arc = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(arc))


def accumulate():
    strikes = np.zeros(2019, dtype=np.float64)
    conus = np.zeros(2019, dtype=np.float64)
    east = np.zeros(2019, dtype=np.float64)
    gap = np.zeros(2019, dtype=np.float64)
    central = np.zeros(2019, dtype=np.float64)
    west = np.zeros(2019, dtype=np.float64)
    south = np.zeros(2019, dtype=np.float64)
    north = np.zeros(2019, dtype=np.float64)
    atlantic = np.zeros(2019, dtype=np.float64)
    pacific = np.zeros(2019, dtype=np.float64)
    weight_lon = np.zeros(2019, dtype=np.float64)
    weight_lat = np.zeros(2019, dtype=np.float64)
    grid = np.zeros((10, NLON, NLAT), dtype=np.float64)
    state_grid = np.zeros((NSLON, NSLAT), dtype=np.float64)
    rows = 0
    for chunk in pd.read_csv(
        CSV_SRC,
        usecols=["date", "number_of_strikes", "x_coord", "y_coord"],
        chunksize=1_000_000,
    ):
        rows += len(chunk)
        year = chunk["date"].str.slice(0, 4).to_numpy(np.int16)
        count = chunk["number_of_strikes"].to_numpy(np.float64)
        lon = chunk["x_coord"].to_numpy(np.float64)
        lat = chunk["y_coord"].to_numpy(np.float64)
        valid_year = (year >= 2009) & (year <= 2018)
        year = year[valid_year]
        count = count[valid_year]
        lon = lon[valid_year]
        lat = lat[valid_year]
        np.add.at(strikes, year, count)
        in_conus = (lon >= -125.0) & (lon <= -66.5) & (lat >= 24.5) & (lat <= 49.5)
        np.add.at(conus, year[in_conus], count[in_conus])
        np.add.at(weight_lon, year[in_conus], lon[in_conus] * count[in_conus])
        np.add.at(weight_lat, year[in_conus], lat[in_conus] * count[in_conus])
        east_mask = in_conus & (lon >= -83.0)
        gap_mask = in_conus & (lon >= -90.0) & (lon < -83.0)
        central_mask = in_conus & (lon >= -103.0) & (lon < -90.0)
        west_mask = in_conus & (lon < -103.0)
        np.add.at(east, year[east_mask], count[east_mask])
        np.add.at(gap, year[gap_mask], count[gap_mask])
        np.add.at(central, year[central_mask], count[central_mask])
        np.add.at(west, year[west_mask], count[west_mask])
        south_mask = lat < 24.5
        north_mask = lat > 49.5
        atlantic_mask = (lon > -66.5) & (lat >= 24.5) & (lat <= 49.5)
        pacific_mask = (lon < -125.0) & (lat >= 24.5) & (lat <= 49.5)
        np.add.at(south, year[south_mask], count[south_mask])
        np.add.at(north, year[north_mask], count[north_mask])
        np.add.at(atlantic, year[atlantic_mask], count[atlantic_mask])
        np.add.at(pacific, year[pacific_mask], count[pacific_mask])
        lon_bin = np.floor((lon - LON0) / DLON).astype(np.int32)
        lat_bin = np.floor((lat - LAT0) / DLAT).astype(np.int32)
        year_bin = year.astype(np.int32) - 2009
        on_grid = (
            in_conus
            & (lon_bin >= 0)
            & (lon_bin < NLON)
            & (lat_bin >= 0)
            & (lat_bin < NLAT)
            & (year_bin >= 0)
            & (year_bin < 10)
        )
        flat = (
            year_bin[on_grid] * NLON * NLAT
            + lon_bin[on_grid] * NLAT
            + lat_bin[on_grid]
        )
        np.add.at(grid.ravel(), flat, count[on_grid])
        in_2018 = year == 2018
        slon = np.floor((lon - SLON0) / SDLON).astype(np.int32)
        slat = np.floor((lat - SLAT0) / SDLAT).astype(np.int32)
        in_box = (
            in_2018
            & (slon >= 0)
            & (slon < NSLON)
            & (slat >= 0)
            & (slat < NSLAT)
        )
        flat_state = slon[in_box] * NSLAT + slat[in_box]
        np.add.at(state_grid.ravel(), flat_state, count[in_box])
        print("rows", rows, flush=True)
    return {
        "strikes": strikes,
        "conus": conus,
        "east": east,
        "gap": gap,
        "central": central,
        "west": west,
        "south": south,
        "north": north,
        "atlantic": atlantic,
        "pacific": pacific,
        "weight_lon": weight_lon,
        "weight_lat": weight_lat,
        "grid": grid,
        "state_grid": state_grid,
        "rows": rows,
    }


def annual_frame(totals):
    observed = YEARS[totals["strikes"][YEARS] > 0]
    conus = totals["conus"][observed]
    millions = 1_000_000
    frame = pd.DataFrame(
        {
            "year": observed.astype(int),
            "year_label": [str(int(year)) for year in observed],
            "all_millions": totals["strikes"][observed] / millions,
            "conus_millions": conus / millions,
            "outside_millions": (totals["strikes"][observed] - conus) / millions,
            "east_millions": totals["east"][observed] / millions,
            "gap_millions": totals["gap"][observed] / millions,
            "central_millions": totals["central"][observed] / millions,
            "west_millions": totals["west"][observed] / millions,
            "south_millions": totals["south"][observed] / millions,
            "north_millions": totals["north"][observed] / millions,
            "atlantic_millions": totals["atlantic"][observed] / millions,
            "pacific_millions": totals["pacific"][observed] / millions,
            "east_share": totals["east"][observed] / conus,
            "gap_share": totals["gap"][observed] / conus,
            "central_share": totals["central"][observed] / conus,
            "west_share": totals["west"][observed] / conus,
            "centroid_lon": totals["weight_lon"][observed] / conus,
            "centroid_lat": totals["weight_lat"][observed] / conus,
        }
    )
    return frame


def grid_frame(grid, years):
    frames = []
    lon_centers = LON0 + (np.arange(NLON) + 0.5) * DLON
    lat_centers = LAT0 + (np.arange(NLAT) + 0.5) * DLAT
    for year in years:
        values = grid[year - 2009]
        lon_idx, lat_idx = np.nonzero(values > 0)
        frames.append(
            pd.DataFrame(
                {
                    "year": year,
                    "longitude": np.round(lon_centers[lon_idx], 2),
                    "latitude": np.round(lat_centers[lat_idx], 2),
                    "strikes": values[lon_idx, lat_idx],
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def state_frames(state_grid):
    lon_centers = SLON0 + (np.arange(NSLON) + 0.5) * SDLON
    lat_centers = SLAT0 + (np.arange(NSLAT) + 0.5) * SDLAT
    lon_idx, lat_idx = np.nonzero(state_grid > 0)
    lon = lon_centers[lon_idx]
    lat = lat_centers[lat_idx]
    strikes = state_grid[lon_idx, lat_idx]
    assigned = np.full(lon.shape, "", dtype=object)
    for name in ("Texas", "Oklahoma", "Kansas"):
        mask = np.zeros(lon.shape, dtype=bool)
        for ring in rings_for(name):
            mask |= points_in_ring(lon, lat, ring)
        assigned[mask & (assigned == "")] = name
    frame = pd.DataFrame(
        {
            "state": assigned,
            "longitude": np.round(lon, 2),
            "latitude": np.round(lat, 2),
            "strikes": strikes,
        }
    )
    frame = frame[frame["state"] != ""].copy()
    return frame


def city_share(frame):
    lines = []
    for state, cities in CITIES.items():
        part = frame[frame["state"] == state]
        if part.empty:
            continue
        distance = np.full(len(part), np.inf)
        for city_lon, city_lat in cities.values():
            distance = np.minimum(
                distance,
                haversine_km(part["longitude"].to_numpy(), part["latitude"].to_numpy(), city_lon, city_lat),
            )
        weight = part["strikes"].to_numpy()
        lines.append(
            {
                "state": state,
                "strikes": float(weight.sum()),
                "within_80km": float(weight[distance <= 80].sum() / weight.sum()),
                "within_150km": float(weight[distance <= 150].sum() / weight.sum()),
            }
        )
    return pd.DataFrame(lines)


def draw(annual, grid, states, city, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="talk")
    first = annual.iloc[0]
    last = annual.iloc[-1]
    change_all = last["all_millions"] / first["all_millions"] - 1
    change_conus = last["conus_millions"] / first["conus_millions"] - 1

    figure, axis = plt.subplots(figsize=(11, 6))
    sns.lineplot(data=annual, x="year", y="all_millions", marker="o", color="#b30000", label="Entire file", ax=axis)
    sns.lineplot(data=annual, x="year", y="conus_millions", marker="o", color="#4C78A8", label="Continental U.S.", ax=axis)
    axis.annotate(
        f"{first['all_millions']:.1f}M",
        (first["year"], first["all_millions"]),
        textcoords="offset points",
        xytext=(12, 8),
    )
    axis.annotate(
        f"{last['all_millions']:.1f}M",
        (last["year"], last["all_millions"]),
        textcoords="offset points",
        xytext=(-52, 8),
    )
    axis.set_title("Strikes by year. The file only contains 2009, 2012, 2015, and 2018")
    axis.set_xlabel("Year")
    axis.set_ylabel("Strikes (millions)")
    axis.set_xticks(list(annual["year"]))
    figure.tight_layout()
    figure.savefig(FIG / "01_annual.png", dpi=140)
    plt.close(figure)

    long = annual.melt(
        id_vars="year",
        value_vars=["east_millions", "gap_millions", "central_millions", "west_millions", "outside_millions"],
        var_name="region",
        value_name="millions",
    )
    long["region"] = long["region"].map(
        {
            "east_millions": "East Coast",
            "gap_millions": "East interior",
            "central_millions": "Central",
            "west_millions": "West",
            "outside_millions": "Outside the continent",
        }
    )
    figure, axes = plt.subplots(1, 2, figsize=(14, 6))
    sns.lineplot(data=long, x="year", y="millions", hue="region", marker="o", ax=axes[0])
    axes[0].set_title("Strikes, in millions")
    axes[0].set_ylabel("Strikes (millions)")
    axes[0].set_xlabel("Year")
    axes[0].set_xticks(list(annual["year"]))
    shares = annual.melt(
        id_vars="year",
        value_vars=["east_share", "gap_share", "central_share", "west_share"],
        var_name="region",
        value_name="share",
    )
    shares["region"] = shares["region"].map(
        {
            "east_share": "East Coast (lon ≥ -83)",
            "gap_share": "East interior (-90 to -83)",
            "central_share": "Central (-103 to -90)",
            "west_share": "West (lon < -103)",
        }
    )
    sns.lineplot(data=shares, x="year", y="share", hue="region", marker="o", ax=axes[1])
    axes[1].set_title("Share of the continental total")
    axes[1].set_ylabel("Share")
    axes[1].set_xlabel("Year")
    axes[1].set_xticks(list(annual["year"]))
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
    figure.tight_layout()
    figure.savefig(FIG / "02_regions.png", dpi=140)
    plt.close(figure)

    lon_centers = LON0 + (np.arange(NLON) + 0.5) * DLON
    lat_centers = LAT0 + (np.arange(NLAT) + 0.5) * DLAT
    panels = [grid[0], grid[-1]]
    vmax = max(panel.max() for panel in panels)
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharex=True, sharey=True)
    for axis, panel, year in zip(axes, panels, (2009, 2018)):
        show = np.ma.masked_less_equal(panel.T, 0)
        image = axis.imshow(
            show,
            origin="lower",
            extent=[lon_centers[0], lon_centers[-1], lat_centers[0], lat_centers[-1]],
            cmap="YlOrRd",
            vmin=0,
            vmax=vmax,
            aspect="auto",
        )
        axis.set_title(str(year))
        axis.set_xlabel("Longitude")
        axis.set_xlim(-125, -66)
        axis.set_ylim(24, 50)
    axes[0].set_ylabel("Latitude")
    figure.colorbar(image, ax=axes, fraction=0.03, pad=0.02, label="Strikes per 0.5° cell")
    figure.suptitle("Same color scale in 2009 and 2018")
    figure.savefig(FIG / "03_maps.png", dpi=140, bbox_inches="tight")
    plt.close(figure)

    figure, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for axis, state in zip(axes, ("Texas", "Oklahoma", "Kansas")):
        part = states[states["state"] == state]
        axis.set_title(f"{state} 2018")
        axis.set_xlabel("Longitude")
        axis.set_ylabel("Latitude")
        if part.empty:
            continue
        pivot = part.pivot_table(index="latitude", columns="longitude", values="strikes", aggfunc="sum")
        pivot = pivot.sort_index().sort_index(axis=1)
        image = axis.imshow(
            pivot.to_numpy(),
            origin="lower",
            cmap="YlOrRd",
            aspect="auto",
            extent=[
                pivot.columns.min() - 0.1,
                pivot.columns.max() + 0.1,
                pivot.index.min() - 0.1,
                pivot.index.max() + 0.1,
            ],
        )
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    figure.savefig(FIG / "04_states.png", dpi=140)
    plt.close(figure)

    slope = np.polyfit(annual["year"], annual["all_millions"], 1)[0]
    shift = haversine_km(
        first["centroid_lon"],
        first["centroid_lat"],
        last["centroid_lon"],
        last["centroid_lat"],
    )
    summary = {
        "rows": int(rows),
        "years": [int(year) for year in annual["year"]],
        "change_all": float(change_all),
        "change_conus": float(change_conus),
        "slope_millions_per_year": float(slope),
        "start_millions": float(first["all_millions"]),
        "end_millions": float(last["all_millions"]),
        "start_conus": float(first["conus_millions"]),
        "end_conus": float(last["conus_millions"]),
        "start_outside": float(first["outside_millions"]),
        "end_outside": float(last["outside_millions"]),
        "east_2009": float(first["east_share"]),
        "east_2018": float(last["east_share"]),
        "gap_2009": float(first["gap_share"]),
        "gap_2018": float(last["gap_share"]),
        "central_2009": float(first["central_share"]),
        "central_2018": float(last["central_share"]),
        "west_2009": float(first["west_share"]),
        "west_2018": float(last["west_share"]),
        "east_m_2009": float(first["east_millions"]),
        "east_m_2018": float(last["east_millions"]),
        "central_m_2009": float(first["central_millions"]),
        "central_m_2018": float(last["central_millions"]),
        "centroid_km": float(shift),
        "centroid_2009": [float(first["centroid_lon"]), float(first["centroid_lat"])],
        "centroid_2018": [float(last["centroid_lon"]), float(last["centroid_lat"])],
        "cities": city.to_dict(orient="records"),
        "annual": json.loads(annual.round(4).to_json(orient="records")),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def load_frame(frame, table, column_sql):
    csv_path = OUT / f"{table}.csv"
    frame.to_csv(csv_path, index=False)
    subprocess.run(["docker", "cp", str(csv_path), f"superset_db:/tmp/{table}.csv"], check=True)
    subprocess.run(["docker", "exec", "superset_db", "chmod", "644", f"/tmp/{table}.csv"], check=True)
    sql = f"""
DROP TABLE IF EXISTS public.{table};
CREATE TABLE public.{table} ({column_sql});
\\copy public.{table} FROM '/tmp/{table}.csv' WITH (FORMAT csv, HEADER true)
GRANT SELECT ON public.{table} TO examples;
"""
    subprocess.run(
        ["docker", "exec", "-i", "superset_db", "psql", "-U", "superset", "-d", "examples", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode(),
        check=True,
    )


def publish(annual, grids, states, summary):
    load_frame(
        annual,
        "lightning_annual",
        "year integer NOT NULL, year_label text NOT NULL, "
        "all_millions double precision NOT NULL, conus_millions double precision NOT NULL, "
        "outside_millions double precision NOT NULL, "
        "east_millions double precision NOT NULL, gap_millions double precision NOT NULL, "
        "central_millions double precision NOT NULL, west_millions double precision NOT NULL, "
        "south_millions double precision NOT NULL, north_millions double precision NOT NULL, "
        "atlantic_millions double precision NOT NULL, pacific_millions double precision NOT NULL, "
        "east_share double precision NOT NULL, gap_share double precision NOT NULL, "
        "central_share double precision NOT NULL, west_share double precision NOT NULL, "
        "centroid_lon double precision NOT NULL, centroid_lat double precision NOT NULL",
    )
    load_frame(
        grids,
        "lightning_conus_grid",
        "year integer NOT NULL, longitude double precision NOT NULL, "
        "latitude double precision NOT NULL, strikes double precision NOT NULL",
    )
    load_frame(
        states,
        "lightning_state_grid_2018",
        "state text NOT NULL, longitude double precision NOT NULL, "
        "latitude double precision NOT NULL, strikes double precision NOT NULL",
    )
    login = api(
        "POST",
        "/api/v1/security/login",
        {"username": "admin", "password": "admin", "provider": "db", "refresh": True},
    )
    token = login["access_token"]
    csrf = api("GET", "/api/v1/security/csrf_token/", token=token)["result"]
    databases = api("GET", "/api/v1/database/?q=(page:0,page_size:20)", token=token)["result"]
    database_id = next(item["id"] for item in databases if item["database_name"] == "examples")
    existing = {
        item["table_name"]: item["id"]
        for item in api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    }

    def ensure(table_name):
        dataset_id = existing.get(table_name)
        if dataset_id is None:
            created = api(
                "POST",
                "/api/v1/dataset/",
                {"database": database_id, "schema": "public", "table_name": table_name},
                token=token,
                csrf=csrf,
            )
            return created.get("id") or created["result"]["id"]
        api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)
        return dataset_id

    annual_id = ensure("lightning_annual")
    grid_id = ensure("lightning_conus_grid")
    state_id = ensure("lightning_state_grid_2018")
    dashboards = api("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)", token=token)["result"]
    for item in dashboards:
        if item["dashboard_title"] == DASHBOARD_TITLE:
            api("DELETE", f"/api/v1/dashboard/{item['id']}", token=token, csrf=csrf)
    charts = api("GET", "/api/v1/chart/?q=(page:0,page_size:300)", token=token)["result"]
    names = {
        "Strikes by year",
        "Where the strikes increased",
        "Regional share inside the continent",
        "Center of mass of the strikes",
        "Strikes in 2009",
        "Strikes in 2018",
        "Texas 2018",
        "Oklahoma 2018",
        "Kansas 2018",
    }
    for item in charts:
        if item["slice_name"] in names:
            api("DELETE", f"/api/v1/chart/{item['id']}", token=token, csrf=csrf)
    dashboard = api(
        "POST",
        "/api/v1/dashboard/",
        {"dashboard_title": DASHBOARD_TITLE, "published": True},
        token=token,
        csrf=csrf,
    )
    dashboard_id = dashboard.get("id") or dashboard["result"]["id"]

    def year_filter(year):
        return {
            "clause": "WHERE",
            "expressionType": "SIMPLE",
            "subject": "year",
            "operator": "==",
            "comparator": year,
        }

    def state_filter(state):
        return {
            "clause": "WHERE",
            "expressionType": "SIMPLE",
            "subject": "state",
            "operator": "==",
            "comparator": state,
        }

    def heatmap(dataset_id, title, filters):
        return {
            "slice_name": title,
            "viz_type": "heatmap_v2",
            "datasource_id": dataset_id,
            "params": {
                "viz_type": "heatmap_v2",
                "datasource": f"{dataset_id}__table",
                "x_axis": "longitude",
                "groupby": ["latitude"],
                "metric": metric("strikes", "Strikes"),
                "adhoc_filters": filters,
                "row_limit": 20000,
                "sort_x_axis": "alpha_asc",
                "sort_y_axis": "alpha_asc",
                "normalize_across": "heatmap",
                "legend_type": "continuous",
                "linear_color_scheme": "schemeYlOrRd",
                "show_legend": True,
                "show_values": False,
                "y_axis_format": ",.0f",
                "bottom_margin": "auto",
                "left_margin": "auto",
                "xscale_interval": 8,
                "yscale_interval": 6,
                "xAxisLabelRotation": 0,
            },
        }

    chart_specs = [
        {
            "slice_name": "Strikes by year",
            "viz_type": "echarts_timeseries_line",
            "datasource_id": annual_id,
            "params": {
                "viz_type": "echarts_timeseries_line",
                "datasource": f"{annual_id}__table",
                "x_axis": "year_label",
                "x_axis_sort": "year_label",
                "x_axis_sort_asc": True,
                "metrics": [
                    metric("all_millions", "Entire file"),
                    metric("conus_millions", "Continental U.S."),
                ],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 20,
                "show_legend": True,
                "legendOrientation": "top",
                "markerEnabled": True,
                "markerSize": 8,
                "show_value": True,
                "y_axis_format": ",.1f",
                "y_axis_title": "Strikes (millions)",
                "y_axis_title_margin": 50,
                "color_scheme": "supersetColors",
                "rich_tooltip": True,
            },
        },
        {
            "slice_name": "Where the strikes increased",
            "viz_type": "echarts_timeseries_line",
            "datasource_id": annual_id,
            "params": {
                "viz_type": "echarts_timeseries_line",
                "datasource": f"{annual_id}__table",
                "x_axis": "year_label",
                "x_axis_sort": "year_label",
                "x_axis_sort_asc": True,
                "metrics": [
                    metric("east_millions", "East Coast"),
                    metric("gap_millions", "East interior"),
                    metric("central_millions", "Central"),
                    metric("west_millions", "West"),
                    metric("outside_millions", "Outside the continent"),
                ],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 20,
                "show_legend": True,
                "legendOrientation": "top",
                "markerEnabled": True,
                "markerSize": 7,
                "y_axis_format": ",.1f",
                "y_axis_title": "Strikes (millions)",
                "y_axis_title_margin": 50,
                "color_scheme": "supersetColors",
                "rich_tooltip": True,
            },
        },
        {
            "slice_name": "Regional share inside the continent",
            "viz_type": "echarts_timeseries_line",
            "datasource_id": annual_id,
            "params": {
                "viz_type": "echarts_timeseries_line",
                "datasource": f"{annual_id}__table",
                "x_axis": "year_label",
                "x_axis_sort": "year_label",
                "x_axis_sort_asc": True,
                "metrics": [
                    metric("east_share", "East Coast"),
                    metric("gap_share", "East interior"),
                    metric("central_share", "Central"),
                    metric("west_share", "West"),
                ],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 20,
                "show_legend": True,
                "legendOrientation": "top",
                "markerEnabled": True,
                "markerSize": 7,
                "y_axis_format": ",.0%",
                "y_axis_title": "Share of the total",
                "y_axis_title_margin": 50,
                "color_scheme": "supersetColors",
                "rich_tooltip": True,
            },
        },
        {
            "slice_name": "Center of mass of the strikes",
            "viz_type": "echarts_timeseries_line",
            "datasource_id": annual_id,
            "params": {
                "viz_type": "echarts_timeseries_line",
                "datasource": f"{annual_id}__table",
                "x_axis": "year_label",
                "x_axis_sort": "year_label",
                "x_axis_sort_asc": True,
                "metrics": [metric("centroid_lon", "Center-of-mass longitude")],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 20,
                "show_legend": False,
                "markerEnabled": True,
                "markerSize": 8,
                "y_axis_format": ",.2f",
                "y_axis_title": "Longitude (more negative = farther west)",
                "y_axis_title_margin": 60,
                "rich_tooltip": True,
            },
        },
        heatmap(grid_id, "Strikes in 2009", [year_filter(2009)]),
        heatmap(grid_id, "Strikes in 2018", [year_filter(2018)]),
        heatmap(state_id, "Texas 2018", [state_filter("Texas")]),
        heatmap(state_id, "Oklahoma 2018", [state_filter("Oklahoma")]),
        heatmap(state_id, "Kansas 2018", [state_filter("Kansas")]),
    ]
    created = []
    for spec in chart_specs:
        result = api(
            "POST",
            "/api/v1/chart/",
            {
                "slice_name": spec["slice_name"],
                "viz_type": spec["viz_type"],
                "datasource_id": spec["datasource_id"],
                "datasource_type": "table",
                "params": json.dumps(spec["params"]),
                "dashboards": [dashboard_id],
            },
            token=token,
            csrf=csrf,
        )
        chart_id = result.get("id") or result["result"]["id"]
        chart_uuid = (result.get("result") or result).get("uuid")
        if not chart_uuid:
            chart_uuid = api("GET", f"/api/v1/chart/{chart_id}", token=token)["result"]["uuid"]
        created.append((chart_id, chart_uuid, spec["slice_name"]))
        print("chart", chart_id, spec["slice_name"])

    start = summary["start_millions"]
    end = summary["end_millions"]
    change_all = summary["change_all"] * 100
    change_conus = summary["change_conus"] * 100
    first_row = summary["annual"][0]
    last_row = summary["annual"][-1]
    dip = next(row for row in summary["annual"] if row["year"] == 2012)
    near_80 = ", ".join(
        f"{item['state']} {item['within_80km'] * 100:.0f}%" for item in summary["cities"]
    )
    near_150 = ", ".join(
        f"{item['state']} {item['within_150km'] * 100:.0f}%" for item in summary["cities"]
    )
    intro = (
        f"The file has **{summary['rows']:,} rows** and only four complete years, January through December: "
        "**2009, 2012, 2015, and 2018**. The other six years in the title are missing. They are not drawn as zero.\n\n"
        f"**{start:.1f} million in 2009 and {end:.1f} million in 2018** (+{change_all:.0f}%). "
        "The video notes 30.1M and 45M, and a 50% increase. "
        "That 50% is the rounding of these two endpoints, summing every row. "
        f"2012 was {dip['all_millions']:.1f} million, below 2009: the rise is not continuous.\n\n"
        f"Inside the continental cut (latitude 24.5 to 49.5, longitude −125 to −66.5) the change is "
        f"**{summary['start_conus']:.1f}M to {summary['end_conus']:.1f}M** (+{change_conus:.0f}%). "
        f"Outside that cut, from {summary['start_outside']:.1f}M to {summary['end_outside']:.1f}M."
    )
    page1 = (
        "**Lightning strikes in the U.S. have increased 50% over the last decade.**\n\n"
        f"Entire file: {start:.1f}M → {end:.1f}M (+{change_all:.0f}%). "
        f"Continental U.S.: {summary['start_conus']:.1f}M → {summary['end_conus']:.1f}M (+{change_conus:.0f}%). "
        "2010, 2011, 2013, 2014, 2016, and 2017 are missing."
    )
    page2 = (
        "**Lightning strikes have moved from the East Coast to the Central Mainlands over the last decade.**\n\n"
        "They did not move. Inside the continent, the East Coast (longitude ≥ −83) went from "
        f"{summary['east_2009'] * 100:.0f}% to {summary['east_2018'] * 100:.0f}% "
        f"and the center (−103 to −90) from {summary['central_2009'] * 100:.0f}% to {summary['central_2018'] * 100:.0f}%. "
        f"In millions, the East Coast rose from {summary['east_m_2009']:.1f} to {summary['east_m_2018']:.1f} "
        f"and the center from {summary['central_m_2009']:.1f} to {summary['central_m_2018']:.1f}. "
        f"The center of mass moved {summary['centroid_km']:.0f} km "
        f"(from {summary['centroid_2009'][0]:.2f}, {summary['centroid_2009'][1]:.2f} "
        f"to {summary['centroid_2018'][0]:.2f}, {summary['centroid_2018'][1]:.2f}). "
        "Both regions gained strikes. The intensity changed, not the map.\n\n"
        f"What did change place is the record outside the cut: in 2018 there are "
        f"{last_row['south_millions']:.1f}M south of 24.5°, {last_row['north_millions']:.1f}M north of 49.5°, "
        f"{last_row['atlantic_millions']:.1f}M in the Atlantic and {last_row['pacific_millions']:.1f}M in the Pacific "
        f"(in 2009: {first_row['south_millions']:.1f}M, {first_row['north_millions']:.1f}M, "
        f"{first_row['atlantic_millions']:.1f}M and {first_row['pacific_millions']:.1f}M)."
    )
    page3 = (
        "**Most number of lightning strikes in 2018 happened in densely populated household areas.**\n\n"
        "The file has no households or population, so that sentence cannot be checked from it alone. "
        f"As an external reference, the 2018 share of strikes within 80 km of a large city is {near_80}. "
        f"Within 150 km: {near_150}. In Texas most strikes are farther than 150 km. "
        "Color runs from gold to red with the strikes in each 0.2° cell. "
        "A detection network can also record more strikes where there are more sensors."
    )

    def markdown(row_id, code, height):
        return {
            "row": {
                "type": "ROW",
                "id": row_id,
                "children": [f"MARKDOWN-{row_id}"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
            },
            "node": {
                "type": "MARKDOWN",
                "id": f"MARKDOWN-{row_id}",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "meta": {"width": 12, "height": height, "code": code},
            },
        }

    blocks = [
        ("ROW-intro", intro, 36, None),
        ("ROW-cap1", page1, 16, None),
        ("ROW-line", None, None, created[0]),
        ("ROW-cap2", page2, 28, None),
        ("ROW-region", None, None, created[1]),
        ("ROW-share", None, None, [created[2], created[3]]),
        ("ROW-maps", None, None, created[4:6]),
        ("ROW-cap3", page3, 22, None),
        ("ROW-states", None, None, created[6:9]),
    ]
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": [item[0] for item in blocks],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": DASHBOARD_TITLE}},
    }
    for row_id, code, height, charts_in_row in blocks:
        if code is not None:
            piece = markdown(row_id, code, height)
            layout[row_id] = piece["row"]
            layout[f"MARKDOWN-{row_id}"] = piece["node"]
            continue
        chart_list = charts_in_row if isinstance(charts_in_row, list) else [charts_in_row]
        keys = []
        width = 12 // len(chart_list)
        layout[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": keys,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        for chart_id, chart_uuid, name in chart_list:
            chart_key = f"CHART-{chart_id}"
            keys.append(chart_key)
            layout[chart_key] = {
                "type": "CHART",
                "id": chart_key,
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "meta": {
                    "chartId": chart_id,
                    "uuid": chart_uuid,
                    "sliceName": name,
                    "width": width,
                    "height": 56 if len(chart_list) > 1 else 48,
                },
            }
    metadata = {
        "chart_configuration": {},
        "global_chart_configuration": {
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": [chart_id for chart_id, _, _ in created],
        },
        "color_scheme": "supersetColors",
        "label_colors": {
            "Entire file": "#b30000",
            "Continental U.S.": "#4C78A8",
            "East Coast": "#4C78A8",
            "East interior": "#72B7B2",
            "Central": "#E45756",
            "West": "#F58518",
            "Outside the continent": "#B279A2",
            "Center-of-mass longitude": "#54A24B",
        },
        "shared_label_colors": [
            "East Coast",
            "East interior",
            "Central",
            "West",
            "Outside the continent",
        ],
        "map_label_colors": {},
        "cross_filters_enabled": False,
        "native_filter_configuration": [],
    }
    api(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        {"position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)},
        token=token,
        csrf=csrf,
    )
    print("DASHBOARD", dashboard_id)


if __name__ == "__main__":
    totals = accumulate()
    totals_rows = totals["rows"]
    annual = annual_frame(totals)
    grids = pd.concat(
        [grid_frame(totals["grid"], [2009]), grid_frame(totals["grid"], [2018])],
        ignore_index=True,
    )
    states = state_frames(totals["state_grid"])
    cities = city_share(states)
    summary = draw(annual, totals["grid"], states, cities, totals["rows"])
    annual.to_csv(OUT / "annual.csv", index=False)
    publish(annual, grids, states, summary)

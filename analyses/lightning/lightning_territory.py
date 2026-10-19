"""Join 2018 lightning to Census territory and household counts.

The household counts come from the 2018 ACS 5-year summary file, table
B11001 (households) and table B01003 (population). The territory comes
from the Census 2018 cartographic boundary files. The Census API now
requires a key, so this script reads those published files directly.
"""

import io
import os
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import shapefile

BASE = os.environ.get("SUPERSET_URL", "http://127.0.0.1:8088")
ROOT = Path(__file__).resolve().parent


def source_csv():
    chosen = os.environ.get("LIGHTNING_CSV")
    if chosen:
        return Path(chosen)
    local = ROOT / ".source"
    if local.exists():
        return Path(local.read_text(encoding="utf-8").strip())
    raise SystemExit("Set LIGHTNING_CSV to the lightning source file.")


CSV_SRC = source_csv()
OUT = ROOT / "outputs"
FIG = ROOT / "figures"
CENSUS = OUT / "census"
DASHBOARD_TITLE = "Lightning history: United States, 2009-2018"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
SEQ = "https://www2.census.gov/programs-surveys/acs/summary_file/2018/data/5_year_seq_by_state"
TIGER = "https://www2.census.gov/geo/tiger/GENZ2018/shp"

STATES = [
    ("Alabama", "al", "01"),
    ("Alaska", "ak", "02"),
    ("Arizona", "az", "04"),
    ("Arkansas", "ar", "05"),
    ("California", "ca", "06"),
    ("Colorado", "co", "08"),
    ("Connecticut", "ct", "09"),
    ("Delaware", "de", "10"),
    ("DistrictOfColumbia", "dc", "11"),
    ("Florida", "fl", "12"),
    ("Georgia", "ga", "13"),
    ("Hawaii", "hi", "15"),
    ("Idaho", "id", "16"),
    ("Illinois", "il", "17"),
    ("Indiana", "in", "18"),
    ("Iowa", "ia", "19"),
    ("Kansas", "ks", "20"),
    ("Kentucky", "ky", "21"),
    ("Louisiana", "la", "22"),
    ("Maine", "me", "23"),
    ("Maryland", "md", "24"),
    ("Massachusetts", "ma", "25"),
    ("Michigan", "mi", "26"),
    ("Minnesota", "mn", "27"),
    ("Mississippi", "ms", "28"),
    ("Missouri", "mo", "29"),
    ("Montana", "mt", "30"),
    ("Nebraska", "ne", "31"),
    ("Nevada", "nv", "32"),
    ("NewHampshire", "nh", "33"),
    ("NewJersey", "nj", "34"),
    ("NewMexico", "nm", "35"),
    ("NewYork", "ny", "36"),
    ("NorthCarolina", "nc", "37"),
    ("NorthDakota", "nd", "38"),
    ("Ohio", "oh", "39"),
    ("Oklahoma", "ok", "40"),
    ("Oregon", "or", "41"),
    ("Pennsylvania", "pa", "42"),
    ("RhodeIsland", "ri", "44"),
    ("SouthCarolina", "sc", "45"),
    ("SouthDakota", "sd", "46"),
    ("Tennessee", "tn", "47"),
    ("Texas", "tx", "48"),
    ("Utah", "ut", "49"),
    ("Vermont", "vt", "50"),
    ("Virginia", "va", "51"),
    ("Washington", "wa", "53"),
    ("WestVirginia", "wv", "54"),
    ("Wisconsin", "wi", "55"),
    ("Wyoming", "wy", "56"),
]
NAME_BY_FIPS = {fips: folder for folder, _abbr, fips in STATES}
FOCUS = {"Texas": "48", "Oklahoma": "40", "Kansas": "20"}
ABBR_BY_FIPS = {fips: abbr for _folder, abbr, fips in STATES}


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return path
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    path.write_bytes(payload)
    print("got", path.name, len(payload), flush=True)
    return path


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


def read_estimates(path, column_index):
    values = {}
    with zipfile.ZipFile(path) as archive:
        name = next(
            item
            for item in archive.namelist()
            if item.lower().startswith("e") and item.lower().endswith(".txt")
        )
        with archive.open(name) as handle:
            for raw in io.TextIOWrapper(handle, encoding="latin1"):
                parts = raw.rstrip("\n").split(",")
                if len(parts) <= column_index:
                    continue
                token = parts[column_index].strip()
                if token in {"", ".", "-"}:
                    continue
                values[parts[5]] = float(token)
    return values


def read_geo(path, sumlevel):
    frame = pd.read_csv(
        path,
        dtype=str,
        encoding="latin1",
        header=None,
        usecols=[2, 4, 48, 49],
        names=["sumlevel", "logrecno", "geoid_full", "name"],
    )
    kept = frame.loc[frame["sumlevel"].str.zfill(3) == sumlevel, ["logrecno", "geoid_full", "name"]].copy()
    kept["geoid"] = kept["geoid_full"].str.replace(r"^\d+US", "", regex=True)
    kept = kept.rename(columns={"logrecno": "LOGRECNO", "name": "NAME"})
    return kept


def acs_one(state_name, abbr, fips, folder, sequence, sumlevel, column_index, column_name):
    root = f"{SEQ}/{state_name}/{folder}"
    geo_path = download(f"{root}/g20185{abbr}.csv", CENSUS / folder / f"g20185{abbr}.csv")
    zip_path = download(
        f"{root}/20185{abbr}{sequence}.zip",
        CENSUS / folder / f"20185{abbr}{sequence}.zip",
    )
    geo = read_geo(geo_path, sumlevel)
    estimates = read_estimates(zip_path, column_index)
    geo[column_name] = geo["LOGRECNO"].map(estimates)
    geo["state_fips"] = fips
    geo["state"] = state_name if state_name != "DistrictOfColumbia" else "District of Columbia"
    print(state_name, column_name, int(geo[column_name].notna().sum()), flush=True)
    return geo[["geoid", "state", "state_fips", "NAME", column_name]]


def acs_table(sumlevel, sequence, column_index, column_name):
    folder = (
        "All_Geographies_Not_Tracts_Block_Groups"
        if sumlevel == "050"
        else "Tracts_Block_Groups_Only"
    )
    chosen = STATES if sumlevel == "050" else [item for item in STATES if item[0] in FOCUS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = list(
            pool.map(
                lambda item: acs_one(item[0], item[1], item[2], folder, sequence, sumlevel, column_index, column_name),
                chosen,
            )
        )
    return pd.concat(frames, ignore_index=True)


def point_in_rings(lon, lat, rings):
    inside = False
    for ring in rings:
        xs = ring[:, 0]
        ys = ring[:, 1]
        previous = len(ring) - 1
        for current in range(len(ring)):
            y1 = ys[current]
            y2 = ys[previous]
            if (y1 > lat) != (y2 > lat):
                x1 = xs[current]
                x2 = xs[previous]
                x_cross = (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1
                if lon < x_cross:
                    inside = not inside
            previous = current
    return inside


def simplify_ring(ring, epsilon=0.02):
    points = np.asarray(ring, dtype=float)
    if len(points) >= 2 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        closed = np.vstack([points, points[:1]])
        return np.round(closed, 4).tolist()

    def rdp(start, end):
        if end <= start + 1:
            return [start]
        segment = points[end] - points[start]
        length = float(np.hypot(segment[0], segment[1])) or 1.0
        delta = points[start + 1 : end] - points[start]
        distance = np.abs(delta[:, 0] * segment[1] - delta[:, 1] * segment[0]) / length
        pivot = start + 1 + int(np.argmax(distance))
        if distance[pivot - start - 1] <= epsilon:
            return [start]
        return rdp(start, pivot) + rdp(pivot, end)

    index = rdp(0, len(points) - 1) + [len(points) - 1]
    slim = np.round(points[index], 4)
    slim = np.vstack([slim, slim[:1]])
    if len(slim) < 4:
        original = np.asarray(ring, dtype=float)
        return np.round(original, 4).tolist()
    return slim.tolist()


def read_shapes(path, geoid_length):
    reader = shapefile.Reader(str(path))
    fields = [field[0] for field in reader.fields[1:]]
    features = []
    for item in reader.iterShapeRecords():
        values = dict(zip(fields, item.record))
        geoid = str(values["GEOID"])
        if geoid_length == 5 and geoid[:2] not in NAME_BY_FIPS:
            continue
        if geoid_length == 11 and geoid[:2] not in FOCUS.values():
            continue
        parts = list(item.shape.parts) + [len(item.shape.points)]
        rings = []
        polygons = []
        for begin, end in zip(parts, parts[1:]):
            ring = np.asarray(item.shape.points[begin:end], dtype=float)
            if len(ring) < 4:
                continue
            rings.append(ring)
            polygons.append(simplify_ring(ring))
        if not rings:
            continue
        bbox = item.shape.bbox
        features.append(
            {
                "geoid": geoid,
                "name": str(values.get("NAME", geoid)),
                "state_fips": geoid[:2],
                "aland": float(values.get("ALAND") or 0),
                "rings": rings,
                "polygons": polygons,
                "bbox": bbox,
            }
        )
    return features


def spatial_index(features, cell):
    buckets = {}
    for feature in features:
        minx, miny, maxx, maxy = feature["bbox"]
        for ix in range(int(np.floor(minx / cell)), int(np.floor(maxx / cell)) + 1):
            for iy in range(int(np.floor(miny / cell)), int(np.floor(maxy / cell)) + 1):
                buckets.setdefault((ix, iy), []).append(feature)
    return buckets


def assign_strikes_areal(cells, features, cell, samples=4):
    """Split each 0.1 degree lightning cell across the tracts it covers.

    Urban tracts are smaller than the lightning grid, so assigning the whole
    cell to its center tract would miss dense neighborhoods.
    """
    index = spatial_index(features, cell)
    totals = {feature["geoid"]: 0.0 for feature in features}
    matched = 0.0
    missed = 0.0
    half = 0.05
    offsets = np.linspace(-half + half / samples, half - half / samples, samples)
    for (lon, lat), strikes in cells.items():
        weights = {}
        hits = 0
        for dx in offsets:
            for dy in offsets:
                x = float(lon + dx)
                y = float(lat + dy)
                bucket = index.get((int(np.floor(x / cell)), int(np.floor(y / cell))), [])
                for feature in bucket:
                    minx, miny, maxx, maxy = feature["bbox"]
                    if x < minx or x > maxx or y < miny or y > maxy:
                        continue
                    if point_in_rings(x, y, feature["rings"]):
                        weights[feature["geoid"]] = weights.get(feature["geoid"], 0) + 1
                        hits += 1
                        break
        if hits == 0:
            missed += strikes
            continue
        for geoid, weight in weights.items():
            share = strikes * weight / hits
            totals[geoid] += share
            matched += share
    return totals, matched, missed


def assign_strikes(cells, features, cell):
    index = spatial_index(features, cell)
    totals = {feature["geoid"]: 0.0 for feature in features}
    matched = 0.0
    missed = 0.0
    for (lon, lat), strikes in cells.items():
        hits = index.get((int(np.floor(lon / cell)), int(np.floor(lat / cell))), [])
        found = False
        for feature in hits:
            minx, miny, maxx, maxy = feature["bbox"]
            if lon < minx or lon > maxx or lat < miny or lat > maxy:
                continue
            if point_in_rings(lon, lat, feature["rings"]):
                totals[feature["geoid"]] += strikes
                matched += strikes
                found = True
                break
        if not found:
            missed += strikes
    return totals, matched, missed


def lightning_cells():
    totals = {}
    rows = 0
    for chunk in pd.read_csv(
        CSV_SRC,
        usecols=["date", "number_of_strikes", "x_coord", "y_coord"],
        chunksize=1_000_000,
    ):
        rows += len(chunk)
        mask = chunk["date"].str.startswith("2018")
        if not mask.any():
            continue
        part = chunk.loc[mask]
        lon = np.round(part["x_coord"].to_numpy(np.float64), 1)
        lat = np.round(part["y_coord"].to_numpy(np.float64), 1)
        count = part["number_of_strikes"].to_numpy(np.float64)
        grouped = pd.DataFrame({"lon": lon, "lat": lat, "strikes": count}).groupby(["lon", "lat"], sort=False)[
            "strikes"
        ].sum()
        for (lon_value, lat_value), strikes in grouped.items():
            totals[(float(lon_value), float(lat_value))] = totals.get((float(lon_value), float(lat_value)), 0.0) + float(
                strikes
            )
        print("lightning rows", rows, "cells", len(totals), flush=True)
    return totals


def place_name(fips):
    folder = NAME_BY_FIPS.get(fips, fips)
    if folder == "DistrictOfColumbia":
        return "District of Columbia"
    return re.sub(r"(?<!^)(?=[A-Z])", " ", folder)


def geometry(feature):
    parts = [ring for ring in feature["polygons"] if len(ring) >= 4]
    if len(parts) == 1:
        payload = {"type": "Polygon", "coordinates": parts}
    else:
        payload = {"type": "MultiPolygon", "coordinates": [[ring] for ring in parts]}
    return json.dumps(payload, separators=(",", ":"))


def assemble(features, households, population, strikes):
    rows = []
    for feature in features:
        geoid = feature["geoid"]
        area = feature["aland"] / 1_000_000
        household_count = households.get(geoid)
        population_count = population.get(geoid)
        strike_count = float(strikes.get(geoid, 0.0))
        rows.append(
            {
                "geoid": geoid,
                "name": feature["name"],
                "state": place_name(feature["state_fips"]),
                "polygon": geometry(feature),
                "strikes": strike_count,
                "households": household_count,
                "population": population_count,
                "area_km2": area,
                "household_density": (household_count / area) if household_count is not None and area > 0 else None,
                "population_density": (population_count / area) if population_count is not None and area > 0 else None,
            }
        )
    frame = pd.DataFrame(rows)
    frame["households"] = frame["households"].fillna(0)
    frame["population"] = frame["population"].fillna(0)
    frame["household_density"] = frame["household_density"].fillna(0)
    frame["population_density"] = frame["population_density"].fillna(0)
    return frame


def quartile_table(frame, scope):
    valid = frame[(frame["area_km2"] > 1) & (frame["households"] > 0)].copy()
    valid["quartile"] = pd.qcut(
        valid["household_density"],
        4,
        labels=["Q1 least dense", "Q2", "Q3", "Q4 most dense"],
    )
    grouped = valid.groupby("quartile", observed=True)[["strikes", "households", "area_km2"]].sum()
    grouped = grouped.reset_index()
    total_strikes = grouped["strikes"].sum()
    total_households = grouped["households"].sum()
    total_area = grouped["area_km2"].sum()
    grouped["scope"] = scope
    grouped["strike_share"] = grouped["strikes"] / total_strikes
    grouped["household_share"] = grouped["households"] / total_households
    grouped["area_share"] = grouped["area_km2"] / total_area
    dense = valid[valid["quartile"].isin(["Q4 most dense", "Q4 más denso"])]
    above = valid[valid["quartile"].isin(["Q3", "Q4 most dense", "Q4 más denso"])]
    summary = {
        "scope": scope,
        "units": int(len(valid)),
        "q4_strike_share": float(dense["strikes"].sum() / total_strikes),
        "q4_area_share": float(dense["area_km2"].sum() / total_area),
        "q4_household_share": float(dense["households"].sum() / total_households),
        "above_median_strike_share": float(above["strikes"].sum() / total_strikes),
        "above_median_area_share": float(above["area_km2"].sum() / total_area),
        "spearman_density": float(
            valid["household_density"].rank().corr(valid["strikes"].div(valid["area_km2"]).rank())
        ),
    }
    return grouped, summary


def draw(counties, tracts, quartile):
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    quartile = quartile.copy()
    quartile["scope"] = quartile["scope"].replace(
        {
            "Condados de EE.UU.": "U.S. counties",
            "Tractos de Texas, Oklahoma y Kansas": "Tracts in Texas, Oklahoma, and Kansas",
            "Tractos de Texas": "Texas tracts",
            "Tractos de Oklahoma": "Oklahoma tracts",
            "Tractos de Kansas": "Kansas tracts",
        }
    )
    quartile["quartile"] = quartile["quartile"].replace(
        {"Q1 menos denso": "Q1 least dense", "Q4 más denso": "Q4 most dense"}
    )
    sns.set_theme(style="whitegrid", context="talk")
    sample = counties[(counties["area_km2"] > 1) & (counties["households"] > 0)].copy()
    sample["strikes_per_km2"] = sample["strikes"] / sample["area_km2"]
    figure, axis = plt.subplots(figsize=(8, 6))
    sns.scatterplot(
        data=sample,
        x="household_density",
        y="strikes_per_km2",
        ax=axis,
        s=22,
        color="#b30000",
        alpha=0.45,
    )
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Households per km²")
    axis.set_ylabel("Strikes per km² in 2018")
    axis.set_title("Counties: household density and strike density")
    figure.tight_layout()
    figure.savefig(FIG / "05_households_counties.png", dpi=140)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(11, 6))
    sns.barplot(data=quartile, x="quartile", y="strike_share", hue="scope", ax=axis)
    axis.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
    axis.set_xlabel("Households per km², by quartile")
    axis.set_ylabel("Share of 2018 strikes")
    axis.set_title("Do strikes fall where households per km² are highest?")
    figure.tight_layout()
    figure.savefig(FIG / "06_household_quartiles.png", dpi=140)
    plt.close(figure)


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


def publish(counties, tracts, quartile, summaries):
    load_frame(
        counties[
            [
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
            ]
        ],
        "lightning_county_2018",
        "geoid text, name text, state text, polygon text, strikes double precision, "
        "households double precision, population double precision, area_km2 double precision, "
        "household_density double precision, population_density double precision",
    )
    load_frame(
        tracts[
            [
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
            ]
        ],
        "lightning_tract_2018",
        "geoid text, name text, state text, polygon text, strikes double precision, "
        "households double precision, population double precision, area_km2 double precision, "
        "household_density double precision, population_density double precision",
    )
    load_frame(
        quartile[
            ["scope", "quartile", "strikes", "households", "area_km2", "strike_share", "household_share", "area_share"]
        ],
        "lightning_household_quartile",
        "scope text, quartile text, strikes double precision, households double precision, "
        "area_km2 double precision, strike_share double precision, household_share double precision, "
        "area_share double precision",
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

    county_id = ensure("lightning_county_2018")
    tract_id = ensure("lightning_tract_2018")
    quartile_id = ensure("lightning_household_quartile")
    dashboards = api("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)", token=token)["result"]
    dashboard_id = next(item["id"] for item in dashboards if item["dashboard_title"] == DASHBOARD_TITLE)
    charts = api("GET", "/api/v1/chart/?q=(page:0,page_size:300)", token=token)["result"]
    names = {
        "2018 strikes by county",
        "2018 households per km²",
        "Territorio: hogares por km² en 2018",
        "Texas 2018 on the territory",
        "Oklahoma 2018 on the territory",
        "Kansas 2018 on the territory",
        "Strike share by household quartile, counties",
        "Strike share by household quartile, three states",
        "Rayos por cuartil de hogares, condados",
        "Rayos por cuartil de hogares, tres estados",
    }
    for item in charts:
        if item["slice_name"] in names:
            api("DELETE", f"/api/v1/chart/{item['id']}", token=token, csrf=csrf)

    def scope_filter(scope):
        return {
            "clause": "WHERE",
            "expressionType": "SIMPLE",
            "subject": "scope",
            "operator": "==",
            "comparator": scope,
        }

    def state_filter(state):
        return {
            "clause": "WHERE",
            "expressionType": "SIMPLE",
            "subject": "state",
            "operator": "==",
            "comparator": state,
        }

    def polygon_chart(dataset_id, title, value_column, value_label, filters, viewport, autozoom):
        return {
            "slice_name": title,
            "viz_type": "deck_polygon",
            "datasource_id": dataset_id,
            "params": {
                "viz_type": "deck_polygon",
                "datasource": f"{dataset_id}__table",
                "line_column": "polygon",
                "line_type": "json",
                "metric": metric(value_column, value_label),
                "adhoc_filters": filters,
                "row_limit": 20000,
                "filter_nulls": True,
                "map_renderer": "maplibre",
                "maplibre_style": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                "viewport": viewport,
                "autozoom": autozoom,
                "color_scheme_type": "linear_palette",
                "linear_color_scheme": "schemeYlOrRd",
                "filled": True,
                "stroked": False,
                "opacity": 80,
                "legend_position": "tr",
                "legend_format": ",.0f",
            },
        }

    us_view = {"longitude": -98.6, "latitude": 39.2, "zoom": 3.35, "bearing": 0, "pitch": 0}
    chart_specs = [
        polygon_chart(
            county_id,
            "2018 strikes by county",
            "strikes",
            "Strikes",
            [],
            us_view,
            False,
        ),
        polygon_chart(
            county_id,
            "2018 households per km²",
            "household_density",
            "Households per km²",
            [],
            us_view,
            False,
        ),
        polygon_chart(tract_id, "Texas 2018 on the territory", "strikes", "Strikes", [state_filter("Texas")], us_view, True),
        polygon_chart(
            tract_id,
            "Oklahoma 2018 on the territory",
            "strikes",
            "Strikes",
            [state_filter("Oklahoma")],
            us_view,
            True,
        ),
        polygon_chart(
            tract_id,
            "Kansas 2018 on the territory",
            "strikes",
            "Strikes",
            [state_filter("Kansas")],
            us_view,
            True,
        ),
    ]
    for title, scope in (
        ("Strike share by household quartile, counties", "U.S. counties"),
        ("Strike share by household quartile, three states", "Tracts in Texas, Oklahoma, and Kansas"),
    ):
        chart_specs.append(
            {
                "slice_name": title,
                "viz_type": "echarts_timeseries_bar",
                "datasource_id": quartile_id,
                "params": {
                    "viz_type": "echarts_timeseries_bar",
                    "datasource": f"{quartile_id}__table",
                    "x_axis": "quartile",
                    "x_axis_sort": "quartile",
                    "x_axis_sort_asc": True,
                    "metrics": [
                        metric("strike_share", "Share of strikes"),
                        metric("area_share", "Share of the land"),
                        metric("household_share", "Share of households"),
                    ],
                    "groupby": [],
                    "adhoc_filters": [scope_filter(scope)],
                    "row_limit": 20,
                    "show_legend": True,
                    "legendOrientation": "top",
                    "y_axis_format": ",.0%",
                    "y_axis_title": "Share of the total",
                    "rich_tooltip": True,
                    "color_scheme": "supersetColors",
                },
            }
        )
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
        print("chart", chart_id, spec["slice_name"], flush=True)

    county_summary = next(item for item in summaries if item["scope"] == "U.S. counties")
    tract_summary = next(item for item in summaries if item["scope"] == "Tracts in Texas, Oklahoma, and Kansas")
    caption = (
        "The territory is the county and, in Texas, Oklahoma, and Kansas, the 2018 census tract. "
        "Households and population come from the 2014-2018 American Community Survey, tables B11001 and B01003, "
        "published by the Census Bureau. Area is the land area in that year's cartographic file.\n\n"
        f"In the counties, the quartile with the most households per km² holds "
        f"**{county_summary['q4_strike_share'] * 100:.0f}%** of the strikes that fall in the country, "
        f"{county_summary['q4_household_share'] * 100:.0f}% of households, and only "
        f"{county_summary['q4_area_share'] * 100:.0f}% of the land. "
        f"The rank correlation between households per km² and strikes per km² is {county_summary['spearman_density']:.2f}.\n\n"
        f"In the tracts of Texas, Oklahoma, and Kansas the same quartile holds "
        f"**{tract_summary['q4_strike_share'] * 100:.1f}%** of the strikes, "
        f"{tract_summary['q4_household_share'] * 100:.0f}% of households, and "
        f"{tract_summary['q4_area_share'] * 100:.1f}% of the land. "
        f"Above the median falls {tract_summary['above_median_strike_share'] * 100:.1f}% of those strikes. "
        + " ".join(
            f"{label}: {item['q4_strike_share'] * 100:.1f}% of strikes in the densest quartile."
            for item in summaries
            for label in [{"Texas tracts": "Texas", "Oklahoma tracts": "Oklahoma", "Kansas tracts": "Kansas"}.get(item["scope"], "")]
            if label
        )
    )
    dashboard = api("GET", f"/api/v1/dashboard/{dashboard_id}", token=token)["result"]
    layout = json.loads(dashboard["position_json"])
    metadata = json.loads(dashboard["json_metadata"] or "{}")
    for row_id in list(layout.get("GRID_ID", {}).get("children", [])):
        if row_id.startswith("ROW-territory") or row_id.startswith("ROW-household"):
            for child in layout.get(row_id, {}).get("children", []):
                layout.pop(child, None)
            layout.pop(row_id, None)
            layout["GRID_ID"]["children"].remove(row_id)

    def add_markdown(row_id, code, height):
        layout["GRID_ID"]["children"].append(row_id)
        layout[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": [f"MARKDOWN-{row_id}"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        layout[f"MARKDOWN-{row_id}"] = {
            "type": "MARKDOWN",
            "id": f"MARKDOWN-{row_id}",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {"width": 12, "height": height, "code": code},
        }

    def add_charts(row_id, charts_in_row, height):
        keys = []
        width = 12 // len(charts_in_row)
        layout[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": keys,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        layout["GRID_ID"]["children"].append(row_id)
        for chart_id, chart_uuid, name in charts_in_row:
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
                    "height": height,
                },
            }

    add_markdown("ROW-household", caption, 32)
    add_charts("ROW-territory-counties", created[0:2], 62)
    add_charts("ROW-territory-states", created[2:5], 62)
    add_charts("ROW-territory-quartile", created[5:7], 46)
    metadata.setdefault("label_colors", {}).update(
        {
            "Share of strikes": "#b30000",
            "Share of the land": "#4C78A8",
            "Share of households": "#F58518",
        }
    )
    metadata.setdefault("global_chart_configuration", {}).setdefault("chartsInScope", [])
    for chart_id, _uuid, _name in created:
        if chart_id not in metadata["global_chart_configuration"]["chartsInScope"]:
            metadata["global_chart_configuration"]["chartsInScope"].append(chart_id)
    api(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        {"position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)},
        token=token,
        csrf=csrf,
    )
    print("DASHBOARD", dashboard_id)


def download_county_shapes():
    for name in ("cb_2018_us_county_5m.zip", "cb_2018_us_county_20m.zip"):
        try:
            path = download(f"{TIGER}/{name}", CENSUS / name)
        except urllib.error.HTTPError:
            continue
        folder = CENSUS / path.stem
        folder.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(folder)
        return read_shapes(next(folder.glob("*.shp")), 5)
    raise FileNotFoundError("Census county shapefile")


def main():
    households = acs_table("050", "0036000", 6, "households")
    population = acs_table("050", "0003000", 129, "population")
    household_map = dict(zip(households["geoid"], households["households"]))
    population_map = dict(zip(population["geoid"], population["population"]))
    print(
        "county households",
        round(households["households"].sum()),
        "population",
        round(population["population"].sum()),
        flush=True,
    )
    county_features = download_county_shapes()
    tract_features = []
    for state_name, fips in FOCUS.items():
        zip_path = download(f"{TIGER}/cb_2018_{fips}_tract_500k.zip", CENSUS / f"cb_2018_{fips}_tract_500k.zip")
        folder = CENSUS / f"cb_2018_{fips}_tract_500k"
        folder.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(folder)
        tract_features.extend(read_shapes(next(folder.glob("*.shp")), 11))
        print(state_name, "tract shapes", len(tract_features), flush=True)
    tract_households = acs_table("140", "0036000", 6, "households")
    tract_population = acs_table("140", "0003000", 129, "population")
    cells = lightning_cells()
    county_strikes, county_matched, county_missed = assign_strikes(cells, county_features, 1.0)
    focus_cells = {
        key: value
        for key, value in cells.items()
        if -107 <= key[0] <= -93 and 25 <= key[1] <= 41
    }
    tract_strikes, tract_matched, tract_missed = assign_strikes_areal(focus_cells, tract_features, 0.2)
    print(
        "matched county strikes",
        round(county_matched),
        "outside counties",
        round(county_missed),
        "tract matched",
        round(tract_matched),
        "tract missed in box",
        round(tract_missed),
        flush=True,
    )
    counties = assemble(county_features, household_map, population_map, county_strikes)
    tracts = assemble(
        tract_features,
        dict(zip(tract_households["geoid"], tract_households["households"])),
        dict(zip(tract_population["geoid"], tract_population["population"])),
        tract_strikes,
    )
    county_quartile, county_summary = quartile_table(counties, "U.S. counties")
    tract_quartile, tract_summary = quartile_table(tracts, "Tracts in Texas, Oklahoma, and Kansas")
    state_frames = []
    state_summaries = []
    for state_name in ("Texas", "Oklahoma", "Kansas"):
        part, summary = quartile_table(tracts[tracts["state"] == state_name], f"{state_name} tracts")
        state_frames.append(part)
        state_summaries.append(summary)
    quartile = pd.concat([county_quartile, tract_quartile, *state_frames], ignore_index=True)
    summaries = [county_summary, tract_summary, *state_summaries]
    (OUT / "household_summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(json.dumps(summaries, indent=2))
    draw(counties, tracts, quartile[quartile["scope"].isin([
        "U.S. counties",
        "Tracts in Texas, Oklahoma, and Kansas",
    ])])
    publish(counties, tracts, quartile, summaries)


if __name__ == "__main__":
    main()

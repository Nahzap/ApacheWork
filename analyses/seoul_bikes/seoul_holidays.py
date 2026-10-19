"""Holiday impact on Seoul bike rentals, 2017 and 2018.

Pandas keeps functioning days, sums each day, and compares every holiday
with the neighboring non-holidays and with the other dates of the same
weekday. Superset only draws those daily totals.
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BASE = os.environ.get("SUPERSET_URL", "http://127.0.0.1:8088")
ROOT = Path(__file__).resolve().parent
CSV_SRC = Path(os.environ.get(
    "SEOUL_CSV",
    r"D:\Coursera\Course 2\Seoul bicycle rental dataset - Seoul bicycle rental dataset.csv",
))
WORK = ROOT / "outputs"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
DASHBOARD_TITLE = "Impact of Holidays on Seoul Bike Rentals in 2017 and 2018."
ADJACENT_TITLE = "Adjacent days"
WEEKDAY_TITLE = "Matching weekdays"
TABLE = "seoul_holiday_days"
BAND_TABLE = "seoul_holiday_weekday_bands"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_COLORS = {
    "Monday": "#5B8FF9",
    "Tuesday": "#5AD8A6",
    "Wednesday": "#F6BD16",
    "Thursday": "#E8684A",
    "Friday": "#6DC8EC",
    "Saturday": "#9270CA",
    "Sunday": "#FF99C3",
}
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
ORANGE = "#F58518"
BLUE = "#4C78A8"


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
        raise RuntimeError(f"{method} {path} -> {error.code} {detail[:2500]}") from error


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


def load_frame(frame, table, column_sql):
    csv_path = WORK / f"_{table}.csv"
    frame.to_csv(csv_path, index=False)
    subprocess.run(["docker", "cp", str(csv_path), f"superset_db:/tmp/{table}.csv"], check=True)
    subprocess.run(["docker", "exec", "superset_db", "chmod", "644", f"/tmp/{table}.csv"], check=True)
    sql = f"""
DROP TABLE IF EXISTS public.{table};
CREATE TABLE public.{table} ({column_sql});
\\copy public.{table} FROM '/tmp/{table}.csv' WITH (FORMAT csv, HEADER true, NULL '')
GRANT SELECT ON public.{table} TO examples;
"""
    subprocess.run(
        ["docker", "exec", "-i", "superset_db", "psql", "-U", "superset", "-d", "examples", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode(),
        check=True,
    )
    print("loaded", table, len(frame), flush=True)


def prepare():
    raw = pd.read_csv(CSV_SRC, encoding="latin1")
    raw["rental_date"] = pd.to_datetime(raw["Date"], dayfirst=True)
    functioning = raw[raw["Functioning Day"] == "Yes"].copy()
    daily = (
        functioning.groupby("rental_date", as_index=False)
        .agg(
            daily_total=("Rented Bike Count", "sum"),
            hours=("Rented Bike Count", "size"),
            holiday_flag=("Holiday", "nunique"),
            holiday_name=("Holiday", "first"),
        )
        .sort_values("rental_date")
        .reset_index(drop=True)
    )
    if int((daily["holiday_flag"] != 1).sum()) != 0:
        raise SystemExit("a date is marked both holiday and not")
    daily["is_holiday"] = daily["holiday_name"].eq("Holiday")
    daily["year_label"] = daily["rental_date"].dt.strftime("%Y")
    daily["month_label"] = daily["rental_date"].dt.month.map(lambda month: f"{month:02d} · {MONTHS[month - 1]}")
    daily["weekday_name"] = daily["rental_date"].dt.day_name()
    daily["weekday_label"] = daily["weekday_name"].map(
        lambda name: f"{WEEKDAYS.index(name) + 1} · {name}"
    )
    daily["day_key"] = daily["rental_date"].dt.strftime("%Y-%m-%d")
    daily["weekday_day"] = daily["weekday_label"] + " · " + daily["day_key"]

    neighbor_means = []
    weekday_means = []
    for row in daily.itertuples(index=False):
        if not row.is_holiday:
            neighbor_means.append(pd.NA)
            weekday_means.append(pd.NA)
            continue
        earlier = daily[(daily["rental_date"] < row.rental_date) & (~daily["is_holiday"])]
        later = daily[(daily["rental_date"] > row.rental_date) & (~daily["is_holiday"])]
        neighbors = []
        if not earlier.empty:
            neighbors.append(float(earlier.iloc[-1]["daily_total"]))
        if not later.empty:
            neighbors.append(float(later.iloc[0]["daily_total"]))
        neighbor_means.append(float(pd.Series(neighbors).mean()) if neighbors else pd.NA)
        peers = daily[
            (daily["year_label"] == row.year_label)
            & (daily["weekday_name"] == row.weekday_name)
            & (~daily["is_holiday"])
        ]
        weekday_means.append(float(peers["daily_total"].mean()) if not peers.empty else pd.NA)
    daily["neighbor_mean"] = neighbor_means
    daily["weekday_mean"] = weekday_means
    holidays = daily[daily["is_holiday"]].copy()
    regular = daily[~daily["is_holiday"]]
    holiday_mean = float(holidays["daily_total"].mean())
    regular_mean = float(regular["daily_total"].mean())
    below_neighbor = int((holidays["daily_total"] < holidays["neighbor_mean"]).sum())
    below_weekday = int((holidays["daily_total"] < holidays["weekday_mean"]).sum())
    summary = {
        "days": int(len(daily)),
        "holidays": int(len(holidays)),
        "holiday_mean": round(holiday_mean),
        "regular_mean": round(regular_mean),
        "difference_pct": round(100 * (holiday_mean - regular_mean) / regular_mean, 1),
        "below_neighbor": below_neighbor,
        "with_neighbor": int(holidays["neighbor_mean"].notna().sum()),
        "below_weekday": below_weekday,
        "with_weekday": int(holidays["weekday_mean"].notna().sum()),
        "holiday_hours": round(float(holidays["hours"].mean()), 2),
        "regular_hours": round(float(regular["hours"].mean()), 2),
    }
    print(json.dumps(summary, indent=2), flush=True)
    print(
        holidays[["day_key", "weekday_name", "daily_total", "neighbor_mean", "weekday_mean"]].to_string(index=False),
        flush=True,
    )

    daily["holiday_total"] = daily["daily_total"].where(daily["is_holiday"])
    daily["regular_total"] = daily["daily_total"].where(~daily["is_holiday"])
    frame = daily[
        [
            "day_key",
            "weekday_day",
            "year_label",
            "month_label",
            "weekday_label",
            "holiday_total",
            "regular_total",
        ]
    ].copy()
    bands = (
        daily.groupby(["weekday_name", "year_label"], as_index=False)
        .agg(band_start=("weekday_day", "min"), band_end=("weekday_day", "max"))
        .sort_values(["weekday_name", "year_label"])
    )
    return frame, bands, summary


def bar_params(dataset_id, x_axis, annotation_layers=None):
    params = {
        "viz_type": "echarts_timeseries_bar",
        "datasource": f"{dataset_id}__table",
        "x_axis": x_axis,
        "x_axis_sort": x_axis,
        "x_axis_sort_asc": True,
        "metrics": [
            metric("holiday_total", "Holiday"),
            metric("regular_total", "No holiday"),
        ],
        "groupby": [],
        "adhoc_filters": [],
        "row_limit": 2000,
        "show_legend": True,
        "legendType": "plain",
        "legendOrientation": "top",
        "zoomable": True,
        "y_axis_format": ",.0f",
        "x_axis_title": "",
        "y_axis_title": "Total rented bikes",
        "y_axis_title_margin": 70,
        "xAxisLabelRotation": 45,
        "color_scheme": "supersetColors",
        "orientation": "vertical",
        "rich_tooltip": True,
        "time_grain_sqla": None,
    }
    if annotation_layers:
        params["annotation_layers"] = annotation_layers
    return params


def ensure_dataset(token, csrf, database_id, table):
    datasets = api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    dataset_id = next((item["id"] for item in datasets if item["table_name"] == table), None)
    if dataset_id is None:
        created = api(
            "POST",
            "/api/v1/dataset/",
            {"database": database_id, "schema": "public", "table_name": table},
            token=token,
            csrf=csrf,
        )
        dataset_id = created.get("id") or created["result"]["id"]
    else:
        api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)
    return dataset_id


def band_layer(name, chart_id):
    return {
        "annotationType": "INTERVAL",
        "name": name,
        "show": True,
        "showLabel": False,
        "showMarkers": False,
        "color": WEEKDAY_COLORS[name],
        "opacity": "opacityLow",
        "style": "solid",
        "width": 1,
        "sourceType": "table",
        "value": chart_id,
        "timeColumn": "band_start",
        "intervalEndColumn": "band_end",
        "titleColumn": "",
        "descriptionColumns": [],
        "overrides": {"time_range": None},
    }


def publish_bands(token, csrf, database_id, bands):
    load_frame(
        bands,
        BAND_TABLE,
        "weekday_name text, year_label text, band_start text, band_end text",
    )
    dataset_id = ensure_dataset(token, csrf, database_id, BAND_TABLE)
    charts = api("GET", "/api/v1/chart/?q=(page:0,page_size:200)", token=token)["result"]
    by_name = {item["slice_name"]: item for item in charts}
    layers = []
    for name in WEEKDAYS:
        slice_name = f"Weekday background: {name}"
        params = {
            "viz_type": "table",
            "datasource": f"{dataset_id}__table",
            "query_mode": "raw",
            "all_columns": ["band_start", "band_end", "weekday_name", "year_label"],
            "adhoc_filters": [
                {
                    "clause": "WHERE",
                    "expressionType": "SIMPLE",
                    "subject": "weekday_name",
                    "operator": "==",
                    "comparator": name,
                    "filterOptionName": "filter_" + name.lower(),
                }
            ],
            "row_limit": 10,
        }
        query_context = json.dumps({
            "datasource": {"id": dataset_id, "type": "table"},
            "force": False,
            "queries": [
                {
                    "columns": ["band_start", "band_end", "weekday_name", "year_label"],
                    "filters": [{"col": "weekday_name", "op": "==", "val": name}],
                    "row_limit": 10,
                }
            ],
            "result_format": "json",
            "result_type": "full",
        })
        payload = {
            "slice_name": slice_name,
            "viz_type": "table",
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params),
            "query_context": query_context,
            "dashboards": [],
        }
        current = by_name.get(slice_name)
        if current is None:
            result = api("POST", "/api/v1/chart/", payload, token=token, csrf=csrf)
            chart_id = result.get("id") or result["result"]["id"]
        else:
            chart_id = current["id"]
            api("PUT", f"/api/v1/chart/{chart_id}", payload, token=token, csrf=csrf)
        layers.append(band_layer(name, chart_id))
        print("band", chart_id, name, flush=True)
    return layers


def publish(frame, bands, summary):
    load_frame(
        frame,
        TABLE,
        "day_key text, weekday_day text, year_label text, month_label text, weekday_label text, "
        "holiday_total double precision, regular_total double precision",
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
    datasets = api("GET", "/api/v1/dataset/?q=(page:0,page_size:200)", token=token)["result"]
    dataset_id = next((item["id"] for item in datasets if item["table_name"] == TABLE), None)
    if dataset_id is None:
        created = api(
            "POST",
            "/api/v1/dataset/",
            {"database": database_id, "schema": "public", "table_name": TABLE},
            token=token,
            csrf=csrf,
        )
        dataset_id = created.get("id") or created["result"]["id"]
    else:
        api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)

    dashboards = api("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)", token=token)["result"]
    dashboard = next((item for item in dashboards if item["dashboard_title"] == DASHBOARD_TITLE), None)
    if dashboard is None:
        created = api(
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
    layers = publish_bands(token, csrf, database_id, bands)

    linked = api("GET", f"/api/v1/dashboard/{dashboard_id}/charts", token=token)["result"]
    by_name = {item["slice_name"]: item for item in linked}
    created = []
    for slice_name, x_axis in ((ADJACENT_TITLE, "day_key"), (WEEKDAY_TITLE, "weekday_day")):
        params = bar_params(
            dataset_id,
            x_axis,
            layers if slice_name == WEEKDAY_TITLE else None,
        )
        payload = {
            "slice_name": slice_name,
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params),
            "dashboards": [dashboard_id],
        }
        current = by_name.get(slice_name)
        if current is None:
            result = api("POST", "/api/v1/chart/", payload, token=token, csrf=csrf)
            chart_id = result.get("id") or result["result"]["id"]
        else:
            chart_id = current["id"]
            api("PUT", f"/api/v1/chart/{chart_id}", payload, token=token, csrf=csrf)
        detail = api("GET", f"/api/v1/chart/{chart_id}", token=token)["result"]
        created.append((chart_id, detail["uuid"], slice_name))
        print("chart", chart_id, slice_name, flush=True)

    adjacent_id, weekday_id = created[0][0], created[1][0]
    years = ["2017", "2018"]
    months = [f"{index:02d} · {name}" for index, name in enumerate(MONTHS, start=1)]
    weekdays = [f"{index} · {name}" for index, name in enumerate(WEEKDAYS, start=1)]

    def select_filter(filter_id, name, column, values, chart_ids, excluded, description):
        return {
            "id": filter_id,
            "controlValues": {
                "enableEmptyFilter": False,
                "defaultToFirstItem": False,
                "creatable": False,
                "multiSelect": True,
                "searchAllOptions": False,
                "inverseSelection": False,
            },
            "name": name,
            "filterType": "filter_select",
            "targets": [{"datasetId": dataset_id, "column": {"name": column}}],
            "defaultDataMask": {
                "extraFormData": {"filters": [{"col": column, "op": "IN", "val": values}]},
                "filterState": {"value": values},
                "ownState": {},
            },
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": excluded},
            "chartsInScope": chart_ids,
            "tabsInScope": [],
            "type": "NATIVE_FILTER",
            "description": description,
        }

    metadata = {
        "native_filter_configuration": [
            select_filter(
                "NATIVE_FILTER-year",
                "Year",
                "year_label",
                years,
                [adjacent_id, weekday_id],
                [],
                "2017 and 2018 are both selected.",
            ),
            select_filter(
                "NATIVE_FILTER-month",
                "Month",
                "month_label",
                months,
                [adjacent_id],
                [weekday_id],
                "Limits the adjacent-day chart.",
            ),
            select_filter(
                "NATIVE_FILTER-weekday",
                "Weekday",
                "weekday_label",
                weekdays,
                [weekday_id],
                [adjacent_id],
                "Limits the matching-weekday chart.",
            ),
        ],
        "cross_filters_enabled": False,
        "label_colors": {"Holiday": ORANGE, "No holiday": BLUE},
        "shared_label_colors": {},
        "map_label_colors": {},
        "color_scheme_domain": [],
        "chart_configuration": {},
        "global_chart_configuration": {
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": [],
        },
    }
    direction = "lower" if summary["difference_pct"] < 0 else "higher"
    intro = "\n".join(
        [
            f"**{DASHBOARD_TITLE}**",
            "",
            "Only days with Functioning Day = Yes are included. Each bar is the daily total, the sum of the hours. Holiday is orange and No holiday is blue.",
            "",
            (
                f"Across {summary['holidays']} holidays and {summary['days'] - summary['holidays']} regular days, "
                f"a holiday averages {summary['holiday_mean']:,} bikes and a regular day averages "
                f"{summary['regular_mean']:,}. The holiday total is {abs(summary['difference_pct'])}% {direction} than a regular day."
            ),
            "",
            (
                f"Against the previous and next regular day, {summary['below_neighbor']} of {summary['with_neighbor']} "
                f"holidays rent fewer bikes. Against the other same weekdays that year, "
                f"{summary['below_weekday']} of {summary['with_weekday']} rent fewer."
            ),
            "",
            "On Matching weekdays the background marks the day: Monday blue, Tuesday green, Wednesday yellow, Thursday red, Friday cyan, Saturday purple, and Sunday pink. Each color runs through the last day of that series.",
            "",
            "Year moves both charts. Month keeps one month on Adjacent days. Weekday keeps one weekday on Matching weekdays.",
        ]
    )
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": ["ROW-intro", "ROW-adjacent", "ROW-weekday"],
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
            "meta": {"width": 12, "height": 40, "code": intro},
        },
    }

    def add_chart(row_id, chart, height):
        chart_id, chart_uuid, name = chart
        chart_key = f"CHART-{chart_id}"
        layout[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": [chart_key],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        layout[chart_key] = {
            "type": "CHART",
            "id": chart_key,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {
                "chartId": chart_id,
                "uuid": chart_uuid,
                "sliceName": name,
                "width": 12,
                "height": height,
            },
        }

    add_chart("ROW-adjacent", created[0], 54)
    add_chart("ROW-weekday", created[1], 54)
    api(
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


def main():
    frame, bands, summary = prepare()
    publish(frame, bands, summary)


if __name__ == "__main__":
    main()

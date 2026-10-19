"""Prepare Seoul bike cuts in Python and draw them in Superset.

Pandas does the filtering and the averages. Postgres only stores the
resulting tables, and the charts read those columns without further
aggregation logic.
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
DASHBOARD_TITLE = "Seoul: weekday bike-maintenance hours (2018)"
BAR_TITLE = "Seoul Average Bike Rentals per Hour on Weekdays in 2018"
SEASON_TITLE = "Seasonal Seoul Average Bike Rentals per Hour on Weekdays in 2018"
HOUR_TITLE = "Hour by hour: weekdays in 2018"
WEEK_TITLE = "Week by week: 8 a.m., 10 a.m., and 5 p.m."
DAY_TITLE = "Day by day: 8 a.m., 10 a.m., and 5 p.m."

SEASON_LABEL = {
    "Winter": "1 · Winter",
    "Spring": "2 · Spring",
    "Summer": "3 · Summer",
    "Autumn": "4 · Autumn",
}
WEEKDAY_COLUMN = {
    "Monday": "monday",
    "Tuesday": "tuesday",
    "Wednesday": "wednesday",
    "Thursday": "thursday",
    "Friday": "friday",
}
WEEKDAY_LABEL = {
    "Monday": "Monday",
    "Tuesday": "Tuesday",
    "Wednesday": "Wednesday",
    "Thursday": "Thursday",
    "Friday": "Friday",
}
SERIES_COLORS = {
    "Monday": "#4C78A8",
    "Tuesday": "#F58518",
    "Wednesday": "#54A24B",
    "Thursday": "#E45756",
    "Friday": "#B279A2",
    "8 a.m.": "#F58518",
    "10 a.m.": "#4C78A8",
    "5 p.m.": "#E45756",
}


def hour_label(hour: int) -> str:
    if hour == 0:
        clock = "12 a.m."
    elif hour < 12:
        clock = f"{hour} a.m."
    elif hour == 12:
        clock = "12 p.m."
    else:
        clock = f"{hour - 12} p.m."
    return f"{hour:02d} · {clock}"


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
        "aggregate": "AVG",
        "column": {"column_name": column},
        "expressionType": "SIMPLE",
        "hasCustomLabel": True,
        "label": label,
        "optionName": "metric_" + column,
        "sqlExpression": None,
    }


def load_frame(frame, table, column_sql):
    if frame.isna().any().any():
        raise SystemExit(f"{table} has nulls\n{frame.isna().sum()}")
    csv_path = WORK / f"_{table}.csv"
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
    print("loaded", table, len(frame))


def main():
    raw = pd.read_csv(CSV_SRC, encoding="latin1")
    raw = raw.rename(
        columns={
            "Date": "rental_date",
            "Rented Bike Count": "rented_bike_count",
            "Hour": "hour",
            "Seasons": "seasons",
        }
    )
    raw["rental_date"] = pd.to_datetime(raw["rental_date"], dayfirst=True)
    raw["weekday_name"] = raw["rental_date"].dt.day_name()
    raw["weekday_num"] = raw["rental_date"].dt.dayofweek + 1
    raw["rental_year"] = raw["rental_date"].dt.year
    raw["hour_label"] = raw["hour"].map(hour_label)
    raw["season_label"] = raw["seasons"].map(SEASON_LABEL)
    raw["week_label"] = raw["rental_date"].dt.strftime("%G-W%V")

    weekdays = raw[(raw["rental_year"] == 2018) & (raw["weekday_num"].between(1, 5))].copy()
    work_window = weekdays[weekdays["hour"].between(8, 17)].copy()

    hour_avg = (
        work_window.groupby(["hour", "hour_label"], as_index=False)["rented_bike_count"]
        .mean()
        .rename(columns={"rented_bike_count": "avg_rentals"})
        .sort_values("hour")
    )
    season_hour = (
        work_window.groupby(["season_label", "hour_label"], as_index=False)["rented_bike_count"]
        .mean()
        .rename(columns={"rented_bike_count": "avg_rentals"})
        .sort_values(["season_label", "hour_label"])
    )
    hour_by_weekday = (
        weekdays.groupby(["hour", "weekday_name"])["rented_bike_count"]
        .mean()
        .unstack("weekday_name")
        .rename(columns=WEEKDAY_COLUMN)
        .reset_index()
        .sort_values("hour")
    )
    hour_by_weekday = hour_by_weekday[
        ["hour", "monday", "tuesday", "wednesday", "thursday", "friday"]
    ]
    week_hours = (
        weekdays[weekdays["hour"].isin([8, 10, 17])]
        .groupby(["week_label", "hour"])["rented_bike_count"]
        .mean()
        .unstack("hour")
        .rename(columns={8: "avg_8am", 10: "avg_10am", 17: "avg_5pm"})
        .reset_index()
        .sort_values("week_label")
    )
    day_hours = (
        weekdays[weekdays["hour"].isin([8, 10, 17])]
        .pivot_table(
            index=["rental_date", "weekday_name"],
            columns="hour",
            values="rented_bike_count",
            aggfunc="mean",
        )
        .rename(columns={8: "bikes_8am", 10: "bikes_10am", 17: "bikes_5pm"})
        .reset_index()
        .sort_values("rental_date")
    )
    day_hours["workday"] = (
        day_hours["rental_date"].dt.strftime("%Y-%m-%d")
        + " · "
        + day_hours["weekday_name"].map(WEEKDAY_LABEL)
    )
    day_hours = day_hours[["workday", "bikes_8am", "bikes_10am", "bikes_5pm"]]

    per_day = work_window.pivot(index="rental_date", columns="hour", values="rented_bike_count")
    day_min = per_day.idxmin(axis=1)
    per_week = (
        work_window.groupby(["week_label", "hour"])["rented_bike_count"].mean().unstack("hour")
    )
    week_min = per_week.idxmin(axis=1)
    workday_min = (
        work_window.groupby(["weekday_name", "hour"])["rented_bike_count"].mean().groupby("weekday_name").idxmin()
    )
    print("DAY MIN HOURS")
    print(day_min.value_counts().sort_index().to_string())
    print("WEEK MIN HOURS")
    print(week_min.value_counts().sort_index().to_string())
    print("WEEKDAY WORK-HOUR MIN")
    print(workday_min.to_string())

    n_days = int(day_min.shape[0])
    n_days_10 = int((day_min == 10).sum())
    n_days_8 = int((day_min == 8).sum())
    n_weeks = int(week_min.shape[0])
    n_weeks_10 = int((week_min == 10).sum())
    lowest_hour = float(hour_avg.loc[hour_avg["hour"] == 10, "avg_rentals"].iloc[0])
    peak_hour = float(hour_avg["avg_rentals"].max())

    load_frame(
        hour_avg[["hour_label", "avg_rentals"]],
        "seoul_prep_hour_avg",
        "hour_label text NOT NULL, avg_rentals double precision NOT NULL",
    )
    load_frame(
        season_hour[["season_label", "hour_label", "avg_rentals"]],
        "seoul_prep_season_hour",
        "season_label text NOT NULL, hour_label text NOT NULL, avg_rentals double precision NOT NULL",
    )
    load_frame(
        hour_by_weekday,
        "seoul_prep_hour_weekday",
        "hour integer NOT NULL, monday double precision NOT NULL, tuesday double precision NOT NULL, "
        "wednesday double precision NOT NULL, thursday double precision NOT NULL, friday double precision NOT NULL",
    )
    load_frame(
        week_hours[["week_label", "avg_8am", "avg_10am", "avg_5pm"]],
        "seoul_prep_week",
        "week_label text NOT NULL, avg_8am double precision NOT NULL, avg_10am double precision NOT NULL, "
        "avg_5pm double precision NOT NULL",
    )
    load_frame(
        day_hours,
        "seoul_prep_day",
        "workday text NOT NULL, bikes_8am double precision NOT NULL, bikes_10am double precision NOT NULL, "
        "bikes_5pm double precision NOT NULL",
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
    by_table = {item["table_name"]: item["id"] for item in datasets}


    def ensure_dataset(table_name):
        dataset_id = by_table.get(table_name)
        if dataset_id is None:
            created = api(
                "POST",
                "/api/v1/dataset/",
                {"database": database_id, "schema": "public", "table_name": table_name},
                token=token,
                csrf=csrf,
            )
            dataset_id = created.get("id") or created["result"]["id"]
            print("dataset created", table_name, dataset_id)
            return dataset_id
        api("PUT", f"/api/v1/dataset/{dataset_id}/refresh", token=token, csrf=csrf)
        print("dataset refreshed", table_name, dataset_id)
        return dataset_id


    dataset_ids = {
        name: ensure_dataset(name)
        for name in [
            "seoul_prep_hour_avg",
            "seoul_prep_season_hour",
            "seoul_prep_hour_weekday",
            "seoul_prep_week",
            "seoul_prep_day",
        ]
    }

    dashboards = api("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)", token=token)["result"]
    dashboard_id = next(item["id"] for item in dashboards if item["dashboard_title"] == DASHBOARD_TITLE)
    charts = api("GET", "/api/v1/chart/?q=(page:0,page_size:200)", token=token)["result"]
    for item in charts:
        if item["slice_name"] in {HOUR_TITLE, WEEK_TITLE, DAY_TITLE}:
            api("DELETE", f"/api/v1/chart/{item['id']}", token=token, csrf=csrf)
            print("deleted chart", item["id"], item["slice_name"])


    def line_params(dataset_id, x_axis, metrics, y_title, rotation=0, markers=False, zoomable=False):
        return {
            "viz_type": "echarts_timeseries_line",
            "datasource": f"{dataset_id}__table",
            "x_axis": x_axis,
            "x_axis_sort": x_axis,
            "x_axis_sort_asc": True,
            "metrics": metrics,
            "groupby": [],
            "adhoc_filters": [],
            "row_limit": 1000,
            "show_legend": True,
            "legendType": "plain",
            "legendOrientation": "top",
            "markerEnabled": markers,
            "markerSize": 6,
            "zoomable": zoomable,
            "y_axis_format": ",.0f",
            "x_axis_title": "",
            "y_axis_title": y_title,
            "y_axis_title_margin": 60,
            "xAxisLabelRotation": rotation,
            "color_scheme": "supersetColors",
            "rich_tooltip": True,
            "time_grain_sqla": None,
        }


    def save_existing(slice_name, dataset_key, params):
        chart = next(item for item in charts if item["slice_name"] == slice_name)
        params = dict(params)
        params["datasource"] = f"{dataset_ids[dataset_key]}__table"
        api(
            "PUT",
            f"/api/v1/chart/{chart['id']}",
            {
                "datasource_id": dataset_ids[dataset_key],
                "datasource_type": "table",
                "params": json.dumps(params),
            },
            token=token,
            csrf=csrf,
        )
        detail = api("GET", f"/api/v1/chart/{chart['id']}", token=token)["result"]
        print("updated", slice_name, detail["id"])
        return detail["id"], detail["uuid"], slice_name


    bar_chart = save_existing(
        BAR_TITLE,
        "seoul_prep_hour_avg",
        {
            "viz_type": "echarts_timeseries_bar",
            "x_axis": "hour_label",
            "x_axis_sort": "hour_label",
            "x_axis_sort_asc": True,
            "metrics": [metric("avg_rentals", "Average rented bikes")],
            "groupby": [],
            "adhoc_filters": [],
            "row_limit": 100,
            "color_by_primary_axis": True,
            "show_legend": False,
            "show_value": True,
            "value_label_position": "outsideEnd",
            "y_axis_format": ",.0f",
            "x_axis_title": "",
            "y_axis_title": "Average rented bikes",
            "y_axis_title_margin": 50,
            "xAxisLabelRotation": 35,
            "color_scheme": "supersetColors",
            "orientation": "vertical",
            "rich_tooltip": True,
        },
    )
    season_chart = save_existing(
        SEASON_TITLE,
        "seoul_prep_season_hour",
        {
            "viz_type": "heatmap_v2",
            "x_axis": "hour_label",
            "groupby": ["season_label"],
            "metric": metric("avg_rentals", "Average rented bikes"),
            "adhoc_filters": [],
            "row_limit": 100,
            "sort_x_axis": "alpha_asc",
            "sort_y_axis": "alpha_desc",
            "normalize_across": "heatmap",
            "legend_type": "continuous",
            "linear_color_scheme": "oranges",
            "show_legend": True,
            "show_values": True,
            "show_percentage": False,
            "y_axis_format": ",.0f",
            "bottom_margin": "auto",
            "left_margin": "auto",
            "xscale_interval": 1,
            "yscale_interval": 1,
            "xAxisLabelRotation": 35,
            "value_bounds": [None, None],
        },
    )

    detail_specs = [
        (
            HOUR_TITLE,
            "echarts_timeseries_line",
            "seoul_prep_hour_weekday",
            line_params(
                dataset_ids["seoul_prep_hour_weekday"],
                "hour",
                [
                    metric("monday", "Monday"),
                    metric("tuesday", "Tuesday"),
                    metric("wednesday", "Wednesday"),
                    metric("thursday", "Thursday"),
                    metric("friday", "Friday"),
                ],
                "Average bikes",
                rotation=0,
                markers=True,
            ),
            "Each point is the average of that hour on that weekday. Python computed the average over weekdays in 2018, from 0 to 23.",
        ),
        (
            WEEK_TITLE,
            "echarts_timeseries_line",
            "seoul_prep_week",
            line_params(
                dataset_ids["seoul_prep_week"],
                "week_label",
                [
                    metric("avg_8am", "8 a.m."),
                    metric("avg_10am", "10 a.m."),
                    metric("avg_5pm", "5 p.m."),
                ],
                "Average bikes",
                rotation=45,
                markers=True,
                zoomable=True,
            ),
            "Each point is the average of that hour in the ISO week. The three series come from the table prepared in Python.",
        ),
        (
            DAY_TITLE,
            "echarts_timeseries_line",
            "seoul_prep_day",
            line_params(
                dataset_ids["seoul_prep_day"],
                "workday",
                [
                    metric("bikes_8am", "8 a.m."),
                    metric("bikes_10am", "10 a.m."),
                    metric("bikes_5pm", "5 p.m."),
                ],
                "Rented bikes",
                rotation=0,
                markers=False,
                zoomable=True,
            ),
            "Each point is one weekday in 2018. The value is that hour's rentals, not a daily average.",
        ),
    ]

    created = [bar_chart, season_chart]
    for slice_name, viz_type, dataset_key, params, description in detail_specs:
        result = api(
            "POST",
            "/api/v1/chart/",
            {
                "slice_name": slice_name,
                "description": description,
                "viz_type": viz_type,
                "datasource_id": dataset_ids[dataset_key],
                "datasource_type": "table",
                "params": json.dumps(params),
                "dashboards": [dashboard_id],
            },
            token=token,
            csrf=csrf,
        )
        chart_id = result.get("id") or result["result"]["id"]
        chart_uuid = (result.get("result") or result).get("uuid")
        if not chart_uuid:
            chart_uuid = api("GET", f"/api/v1/chart/{chart_id}", token=token)["result"]["uuid"]
        created.append((chart_id, chart_uuid, slice_name))
        print("chart", chart_id, slice_name)

    intro = (
        "**Lowest bicycle traffic times: 9 a.m. to 3 p.m.**\n\n"
        "The averages were computed in Python over weekdays in 2018. "
        "Superset only draws those tables.\n\n"
        "From 8 a.m. to 5 p.m., the lowest average is still **10 a.m.** "
        f"({lowest_hour:,.0f} bikes; at 8 a.m. the average rises to {peak_hour:,.0f}). "
        f"That is not every day: 10 a.m. is the lowest hour of the workday "
        f"on **{n_days_10} of {n_days} days** and in **{n_weeks_10} of {n_weeks} weeks**. "
        f"On {n_days_8} days the minimum was 8 a.m.\n\n"
        "The lines below go into the detail: hour by hour (0 to 23, one line per weekday), "
        "week by week, and day by day. On those last two charts, the blue line is 10 a.m."
    )

    order = [
        ("ROW-intro", None, 12, 34),
        ("ROW-hour", created[2], 12, 52),
        ("ROW-week", created[3], 12, 48),
        ("ROW-day", created[4], 12, 52),
        ("ROW-bar", created[0], 12, 50),
        ("ROW-season", created[1], 12, 46),
    ]
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": [row_id for row_id, _, _, _ in order],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {
            "type": "HEADER",
            "id": "HEADER_ID",
            "meta": {"text": DASHBOARD_TITLE},
        },
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
            "meta": {"width": 12, "height": 34, "code": intro},
        },
    }
    for row_id, chart, width, height in order[1:]:
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
                "width": width,
                "height": height,
            },
        }

    current = api("GET", f"/api/v1/dashboard/{dashboard_id}", token=token)["result"]
    metadata = json.loads(current.get("json_metadata") or "{}")
    label_colors = dict(metadata.get("label_colors") or {})
    label_colors.update(SERIES_COLORS)
    metadata["label_colors"] = label_colors
    metadata["shared_label_colors"] = sorted(set(metadata.get("shared_label_colors") or []) | set(SERIES_COLORS))
    metadata["map_label_colors"] = label_colors
    metadata["global_chart_configuration"] = {
        "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
        "chartsInScope": [chart_id for chart_id, _, _ in created],
    }
    api(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        {"position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)},
        token=token,
        csrf=csrf,
    )
    print("READY", dashboard_id)
    print("DAYS", n_days, "AT_10", n_days_10, "AT_8", n_days_8)
    print("WEEKS", n_weeks, "AT_10", n_weeks_10)


if __name__ == "__main__":
    main()

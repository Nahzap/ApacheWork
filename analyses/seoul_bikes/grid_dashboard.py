"""Official board for Seoul bike maintenance, 2018.

Five charts, and only these five. Reads the tables already prepared by
seoul_detail.py. Does not reload those tables and does not delete charts.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

BASE = os.environ.get("SUPERSET_URL", "http://127.0.0.1:8088")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
PNG = OUT / "ejercicio_1_oficial.png"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

DASHBOARD_TITLE = "Seoul: horarios de mantenimiento de bicicletas (2018)"
BAR_TITLE = "Seoul Average Bike Rentals per Hour on Weekdays in 2018"
SEASON_TITLE = "Seasonal Seoul Average Bike Rentals per Hour on Weekdays in 2018"
HOUR_TITLE = "Hora a hora: días hábiles de 2018"
WEEK_TITLE = "Semana a semana: 8 a.m., 10 a.m. y 5 p.m."
DAY_TITLE = "Jornada a jornada: 8 a.m., 10 a.m. y 5 p.m."

INK = "#1c1c1c"
MUTED = "#5e5e5e"
GRID = "#e4e4e4"
PAGE = "#f6f4ef"
BLUE = "#4C78A8"
ORANGE = "#F58518"
RED = "#E45756"
GREEN = "#54A24B"
PURPLE = "#B279A2"
NEUTRAL = "#8b93a7"

WEEKDAYS = (
    ("monday", "Lunes", BLUE),
    ("tuesday", "Martes", ORANGE),
    ("wednesday", "Miércoles", GREEN),
    ("thursday", "Jueves", RED),
    ("friday", "Viernes", PURPLE),
)
HOURS = (
    ("avg_8am", "8 a.m.", ORANGE),
    ("avg_10am", "10 a.m.", BLUE),
    ("avg_5pm", "5 p.m.", RED),
)


def clock(hour_label: str) -> str:
    return hour_label.split("·")[-1].strip()


def season_name(label: str) -> str:
    return label.split("·")[-1].strip()


def load_tables():
    hour_avg = pd.read_csv(OUT / "_seoul_prep_hour_avg.csv")
    hour_week = pd.read_csv(OUT / "_seoul_prep_hour_weekday.csv")
    week = pd.read_csv(OUT / "_seoul_prep_week.csv")
    season = pd.read_csv(OUT / "_seoul_prep_season_hour.csv")
    return hour_avg, hour_week, week, season


def style_axis(ax):
    ax.set_facecolor("white")
    ax.tick_params(colors=INK, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color("#ececec")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def panel_title(ax, text):
    ax.set_title(text, loc="left", fontsize=13, color=INK, pad=10, fontweight="medium")


def draw_bars(ax, hour_avg):
    labels = [clock(value) for value in hour_avg["hour_label"]]
    values = hour_avg["avg_rentals"].to_numpy()
    colors = []
    for label in labels:
        if label == "10 a.m.":
            colors.append(BLUE)
        elif label == "8 a.m.":
            colors.append(ORANGE)
        elif label == "5 p.m.":
            colors.append(RED)
        else:
            colors.append(NEUTRAL)
    bars = ax.bar(labels, values, color=colors, width=0.72, zorder=3)
    ax.set_ylim(0, 1650)
    ax.set_ylabel("Promedio", color=MUTED, fontsize=9)
    for bar, value, color in zip(bars, values, colors):
        if color == NEUTRAL:
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 36,
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=8,
            color=INK,
        )
    style_axis(ax)
    panel_title(ax, "Promedio de 8 a.m. a 5 p.m.")
    ax.tick_params(axis="x", labelrotation=0)
    for label in ax.get_xticklabels():
        label.set_fontsize(8)


def draw_hours(ax, hour_week):
    for column, name, color in WEEKDAYS:
        ax.plot(hour_week["hour"], hour_week[column], color=color, linewidth=1.8, label=name, zorder=3)
    ax.set_xlim(0, 23)
    ax.set_ylim(0, 2100)
    ax.set_xticks(range(0, 24, 2))
    ax.set_ylabel("Promedio", color=MUTED, fontsize=9)
    ax.set_xlabel("Hora", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Hora a hora, lunes a viernes")
    ax.legend(
        ncol=5,
        frameon=False,
        loc="upper left",
        bbox_to_anchor=(0, 1.0),
        fontsize=8,
        labelcolor=INK,
        handlelength=1.4,
        columnspacing=0.9,
    )


def draw_weeks(ax, week):
    for column, name, color in HOURS:
        width = 2.2 if column == "avg_10am" else 1.5
        ax.plot(range(len(week)), week[column], color=color, linewidth=width, label=name, zorder=3)
    ax.set_ylim(0, max(week[["avg_8am", "avg_10am", "avg_5pm"]].max()) * 1.18)
    step = 4
    ticks = list(range(0, len(week), step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([week["week_label"].iloc[i].replace("2018-", "") for i in ticks], fontsize=8)
    ax.set_ylabel("Promedio", color=MUTED, fontsize=9)
    ax.set_xlabel("Semana ISO", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Semana a semana")
    ax.legend(
        ncol=3,
        frameon=False,
        loc="upper left",
        fontsize=8,
        labelcolor=INK,
        handlelength=1.4,
        columnspacing=0.9,
    )


def draw_season(ax, season):
    frame = season.copy()
    frame["clock"] = frame["hour_label"].map(clock)
    frame["season"] = frame["season_label"].map(season_name)
    order = [season_name(value) for value in sorted(frame["season_label"].unique())]
    clocks = [clock(value) for value in sorted(frame["hour_label"].unique())]
    pivot = (
        frame.pivot(index="season", columns="clock", values="avg_rentals")
        .reindex(index=order, columns=clocks)
    )
    cmap = LinearSegmentedColormap.from_list("rentals", ["#fff4e8", "#f58518", "#7a2e0e"])
    image = ax.imshow(pivot.to_numpy(), aspect="auto", cmap=cmap, vmin=0)
    ax.set_xticks(range(len(clocks)))
    ax.set_xticklabels(clocks, fontsize=8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=9)
    ax.tick_params(length=0, colors=INK)
    limit = pivot.to_numpy().max()
    for row in range(pivot.shape[0]):
        for col in range(pivot.shape[1]):
            value = pivot.iloc[row, col]
            tone = "white" if value > limit * 0.62 else INK
            ax.text(col, row, f"{value:,.0f}", ha="center", va="center", fontsize=7, color=tone)
    ax.set_frame_on(False)
    panel_title(ax, "Por estación")
    colorbar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=8, length=0, colors=MUTED)


def draw_days(ax, day):
    ax.plot(day["bikes_8am"], color=ORANGE, linewidth=1.15, label="8 a.m.", zorder=3)
    ax.plot(day["bikes_10am"], color=BLUE, linewidth=1.45, label="10 a.m.", zorder=4)
    ax.plot(day["bikes_5pm"], color=RED, linewidth=1.15, label="5 p.m.", zorder=3)
    ax.set_ylim(0, max(day[["bikes_8am", "bikes_10am", "bikes_5pm"]].max()) * 1.12)
    months = []
    for index, label in enumerate(day["jornada"]):
        if label.endswith("01") or "-01-" in label[:8] and label[8:10] == "01":
            months.append(index)
    if not months:
        months = list(range(0, len(day), 20))
    ticks = [index for index, label in enumerate(day["jornada"]) if label[8:10] == "01"]
    ax.set_xticks(ticks)
    ax.set_xticklabels([day["jornada"].iloc[i][:7] for i in ticks], fontsize=8)
    ax.set_xlim(0, len(day) - 1)
    ax.set_ylabel("Bicicletas", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Jornada a jornada")
    ax.legend(
        ncol=3,
        frameon=False,
        loc="upper left",
        fontsize=8,
        labelcolor=INK,
        handlelength=1.4,
        columnspacing=0.9,
    )


def render(path=PNG):
    hour_avg, hour_week, week, season = load_tables()
    day = pd.read_csv(OUT / "_seoul_prep_day.csv")
    plt.rcParams["font.family"] = "Segoe UI"
    figure = plt.figure(figsize=(16, 13), dpi=110)
    figure.patch.set_facecolor(PAGE)
    grid = figure.add_gridspec(3, 2, height_ratios=[1.05, 1.05, 1.05])
    axes = [
        figure.add_subplot(grid[0, 0]),
        figure.add_subplot(grid[0, 1]),
        figure.add_subplot(grid[1, 0]),
        figure.add_subplot(grid[1, 1]),
        figure.add_subplot(grid[2, :]),
    ]
    draw_bars(axes[0], hour_avg)
    draw_hours(axes[1], hour_week)
    draw_weeks(axes[2], week)
    draw_season(axes[3], season)
    draw_days(axes[4], day)
    lowest = float(hour_avg.loc[hour_avg["hour_label"].str.contains("10 a.m."), "avg_rentals"].iloc[0])
    figure.suptitle(
        "Seúl 2018 · días hábiles · mantenimiento",
        fontsize=18,
        color=INK,
        x=0.055,
        ha="left",
        fontweight="medium",
    )
    figure.text(
        0.055,
        0.935,
        f"En la ventana de 8 a.m. a 5 p.m. el promedio más bajo es las 10 a.m. ({lowest:,.0f} bicicletas). "
        "En las barras y en las líneas, esa hora va en azul.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )
    figure.subplots_adjust(left=0.055, right=0.975, top=0.90, bottom=0.05, wspace=0.22, hspace=0.48)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120, facecolor=figure.get_facecolor())
    plt.close(figure)
    print("figure", path)
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
        raise RuntimeError(f"{method} {path} -> {error.code} {detail[:1800]}") from error


def chart_box(chart_id, chart_uuid, name, row_id, width, height):
    chart_key = f"CHART-{chart_id}"
    return chart_key, {
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


def publish_grid():
    login = api(
        "POST",
        "/api/v1/security/login",
        {"username": "admin", "password": "admin", "provider": "db", "refresh": True},
    )
    token = login["access_token"]
    csrf = api("GET", "/api/v1/security/csrf_token/", token=token)["result"]
    dashboards = api("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)", token=token)["result"]
    dashboard_id = next(item["id"] for item in dashboards if item["dashboard_title"] == DASHBOARD_TITLE)
    charts = api("GET", "/api/v1/chart/?q=(page:0,page_size:200)", token=token)["result"]
    wanted = [BAR_TITLE, HOUR_TITLE, WEEK_TITLE, SEASON_TITLE, DAY_TITLE]
    found = {}
    for item in charts:
        if item["slice_name"] in wanted and item["slice_name"] not in found:
            detail = api("GET", f"/api/v1/chart/{item['id']}", token=token)["result"]
            found[item["slice_name"]] = detail
    missing = [name for name in wanted if name not in found]
    if missing:
        raise SystemExit("missing charts: " + ", ".join(missing))

    tune_bar(found[BAR_TITLE], token, csrf)
    tune_line(found[HOUR_TITLE], token, csrf, "Hora")
    tune_line(found[WEEK_TITLE], token, csrf, "Semana")
    tune_line(found[DAY_TITLE], token, csrf, "Jornada")
    tune_heatmap(found[SEASON_TITLE], token, csrf)

    rows = (
        ("ROW-1", [(found[BAR_TITLE], 6), (found[HOUR_TITLE], 6)], 78),
        ("ROW-2", [(found[WEEK_TITLE], 6), (found[SEASON_TITLE], 6)], 78),
        ("ROW-3", [(found[DAY_TITLE], 12)], 78),
    )
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": [row_id for row_id, _, _ in rows],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {
            "type": "HEADER",
            "id": "HEADER_ID",
            "meta": {"text": DASHBOARD_TITLE},
        },
    }
    for row_id, pair, height in rows:
        keys = []
        for detail, width in pair:
            key, component = chart_box(
                detail["id"], detail["uuid"], detail["slice_name"], row_id, width, height
            )
            layout[key] = component
            keys.append(key)
        layout[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": keys,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
    current = api("GET", f"/api/v1/dashboard/{dashboard_id}", token=token)["result"]
    metadata = json.loads(current.get("json_metadata") or "{}")
    label_colors = dict(metadata.get("label_colors") or {})
    label_colors.update(
        {
            "Lunes": BLUE,
            "Martes": ORANGE,
            "Miércoles": GREEN,
            "Jueves": RED,
            "Viernes": PURPLE,
            "8 a.m.": ORANGE,
            "10 a.m.": BLUE,
            "5 p.m.": RED,
            "08 · 8 a.m.": ORANGE,
            "09 · 9 a.m.": NEUTRAL,
            "10 · 10 a.m.": BLUE,
            "11 · 11 a.m.": NEUTRAL,
            "12 · 12 p.m.": NEUTRAL,
            "13 · 1 p.m.": NEUTRAL,
            "14 · 2 p.m.": NEUTRAL,
            "15 · 3 p.m.": NEUTRAL,
            "16 · 4 p.m.": NEUTRAL,
            "17 · 5 p.m.": RED,
        }
    )
    metadata["label_colors"] = label_colors
    metadata["map_label_colors"] = label_colors
    api(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        {"position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)},
        token=token,
        csrf=csrf,
    )
    print("dashboard", dashboard_id, "5 charts")
    return dashboard_id


def put_params(detail, params, token, csrf):
    api(
        "PUT",
        f"/api/v1/chart/{detail['id']}",
        {
            "params": json.dumps(params),
            "datasource_id": detail.get("datasource_id"),
            "datasource_type": detail.get("datasource_type") or "table",
        },
        token=token,
        csrf=csrf,
    )


def tune_bar(detail, token, csrf):
    params = json.loads(detail["params"])
    params.update(
        {
            "color_by_primary_axis": True,
            "show_legend": False,
            "show_value": True,
            "value_label_position": "outsideEnd",
            "orientation": "vertical",
            "x_axis_sort_asc": True,
            "truncateYAxis": False,
            "truncate_y_axis": False,
            "truncateXAxis": False,
            "y_axis_bounds": [0, 1700],
            "y_axis_title": "Bicicletas",
            "y_axis_title_margin": 12,
            "x_axis_title": "",
            "xAxisLabelRotation": 0,
            "zoomable": False,
        }
    )
    put_params(detail, params, token, csrf)


def tune_line(detail, token, csrf, x_title):
    params = json.loads(detail["params"])
    params.update(
        {
            "y_axis_title": "Bicicletas",
            "y_axis_title_margin": 36,
            "x_axis_title": x_title,
            "xAxisLabelRotation": 0,
            "truncateYAxis": False,
            "y_axis_bounds": [0, None],
            "legendOrientation": "top",
            "legendType": "plain",
            "show_legend": True,
            "zoomable": False,
            "markerEnabled": False,
        }
    )
    put_params(detail, params, token, csrf)


def tune_heatmap(detail, token, csrf):
    params = json.loads(detail["params"])
    params.update(
        {
            "xAxisLabelRotation": 30,
            "left_margin": "auto",
            "bottom_margin": "auto",
            "show_values": True,
            "show_legend": True,
        }
    )
    put_params(detail, params, token, csrf)


def main():
    render()
    publish_grid()


if __name__ == "__main__":
    main()

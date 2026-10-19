"""Boards for the U.S. lightning study.

`render` draws the 2009-2018 study from the summaries already on disk.
`render_tableau` draws the five charts of
"Lightning strikes: ejercicios de Tableau". `render_historia` draws the
charts of "Historia: rayos en Estados Unidos, 2009-2018", including the
county maps and Texas, Oklahoma and Kansas. None of these paths reread
the 12 million-row file or rewrite a Superset dashboard.
"""

import io
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PolyCollection
from matplotlib.colors import LogNorm

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
PNG = OUT / "ejercicio_1_oficial.png"

INK = "#1c1c1c"
MUTED = "#5e5e5e"
GRID = "#e4e4e4"
PAGE = "#f6f4ef"
BLUE = "#4C78A8"
ORANGE = "#F58518"
RED = "#E45756"
GREEN = "#54A24B"
PURPLE = "#B279A2"

REGIONS = (
    ("east_millions", "Costa este", ORANGE),
    ("central_millions", "Centro", BLUE),
    ("west_millions", "Oeste", GREEN),
    ("outside_millions", "Fuera del continente", PURPLE),
)
SHARES = (
    ("east_share", "Costa este", ORANGE),
    ("central_share", "Centro", BLUE),
    ("west_share", "Oeste", GREEN),
    ("gap_share", "Interior este", "#9c755f"),
)


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


def draw_annual(ax, annual):
    ax.plot(annual["year"], annual["all_millions"], color=RED, marker="o", linewidth=2.2, label="Todo el archivo", zorder=3)
    ax.plot(annual["year"], annual["conus_millions"], color=BLUE, marker="o", linewidth=2.2, label="Continente", zorder=3)
    ax.set_ylim(0, annual["all_millions"].max() * 1.25)
    ax.set_xticks(list(annual["year"]))
    ax.set_ylabel("Millones", color=MUTED, fontsize=9)
    for _, row in annual.iterrows():
        ax.text(row["year"], row["all_millions"] + 1.1, f"{row['all_millions']:.1f}", ha="center", fontsize=8, color=INK)
    style_axis(ax)
    panel_title(ax, "Rayos por año")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left")


def draw_regions(ax, annual):
    for column, name, color in REGIONS:
        ax.plot(annual["year"], annual[column], color=color, marker="o", linewidth=2, label=name, zorder=3)
    ax.set_ylim(0, annual["central_millions"].max() * 1.35)
    ax.set_xticks(list(annual["year"]))
    ax.set_ylabel("Millones", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Millones por región")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left", ncol=2)


def draw_shares(ax, annual):
    for column, name, color in SHARES:
        ax.plot(annual["year"], annual[column] * 100, color=color, marker="o", linewidth=2, label=name, zorder=3)
    ax.set_ylim(0, 60)
    ax.set_xticks(list(annual["year"]))
    ax.set_ylabel("Parte del continente (%)", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Parte regional")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper right")


def draw_centroid(ax, annual):
    ax.plot(annual["year"], annual["centroid_lon"], color=BLUE, marker="o", linewidth=2.2, zorder=3)
    ax.set_xticks(list(annual["year"]))
    low = annual["centroid_lon"].min() - 0.6
    high = annual["centroid_lon"].max() + 0.6
    ax.set_ylim(low, high)
    ax.set_ylabel("Longitud", color=MUTED, fontsize=9)
    for _, row in annual.iterrows():
        ax.text(row["year"], row["centroid_lon"] - 0.18, f"{row['centroid_lon']:.2f}", ha="center", fontsize=8, color=INK)
    style_axis(ax)
    panel_title(ax, "Centro de masa, 62 km al oeste")


def draw_households(ax, quartiles):
    scopes = ["Condados de EE.UU.", "Tractos de Texas, Oklahoma y Kansas"]
    labels = ["Q1\nmenos denso", "Q2", "Q3", "Q4\nmás denso"]
    width = 0.18
    colors = (ORANGE, "#f2c39a", BLUE, "#a8c4e0")
    for index, scope in enumerate(scopes):
        part = quartiles[quartiles["scope"] == scope].copy()
        part["order"] = part["quartile"].str[:2]
        part = part.sort_values("order")
        offset = (index - 0.5) * width * 2.3
        ax.bar(
            [i + offset for i in range(4)],
            part["household_share"] * 100,
            width=width,
            color=colors[index * 2],
            label=f"Hogares · {scope.split(' de ')[0]}",
            zorder=3,
        )
        ax.bar(
            [i + offset + width for i in range(4)],
            part["strike_share"] * 100,
            width=width,
            color=colors[index * 2 + 1],
            label=f"Rayos · {scope.split(' de ')[0]}",
            zorder=3,
        )
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Parte del total (%)", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Los hogares densos no concentran los rayos")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, ncol=4, loc="upper left")


def render(path=PNG):
    annual = pd.read_csv(OUT / "annual.csv")
    quartiles = pd.read_csv(OUT / "lightning_household_quartile.csv")
    plt.rcParams["font.family"] = "Segoe UI"
    figure = plt.figure(figsize=(16, 13), dpi=110)
    figure.patch.set_facecolor(PAGE)
    grid = figure.add_gridspec(3, 2, height_ratios=[1.05, 1.05, 1.15])
    axes = [
        figure.add_subplot(grid[0, 0]),
        figure.add_subplot(grid[0, 1]),
        figure.add_subplot(grid[1, 0]),
        figure.add_subplot(grid[1, 1]),
        figure.add_subplot(grid[2, :]),
    ]
    draw_annual(axes[0], annual)
    draw_regions(axes[1], annual)
    draw_shares(axes[2], annual)
    draw_centroid(axes[3], annual)
    draw_households(axes[4], quartiles)
    start = float(annual.iloc[0]["all_millions"])
    end = float(annual.iloc[-1]["all_millions"])
    figure.suptitle(
        "Rayos en Estados Unidos, 2009-2018",
        fontsize=18,
        color=INK,
        x=0.055,
        ha="left",
        fontweight="medium",
    )
    figure.text(
        0.055,
        0.935,
        f"El archivo pasa de {start:.1f} M a {end:.1f} M (+{(end / start - 1):.0%}). "
        "2012 queda por debajo de 2009. El centro no le gana terreno a la costa en porcentaje, "
        "y el cuartil más denso de hogares no se queda con los rayos.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )
    figure.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.06, wspace=0.24, hspace=0.48)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120, facecolor=figure.get_facecolor())
    plt.close(figure)
    print("figure", path)
    return path


TABLEAU_PNG = OUT / "lightning_tableau.png"
TABLEAU_TITLE = "Lightning strikes: ejercicios de Tableau"
MARK_BREAKS = (
    (40, 108, "#B71C1C"),
    (32, 39, "#E53935"),
    (28, 31, "#F4511E"),
    (23, 27, "#FF9800"),
    (19, 22, "#FFCA28"),
    (15, 18, "#C0CA33"),
    (11, 14, "#66BB6A"),
    (7, 10, "#26A69A"),
    (3, 6, "#26C6DA"),
    (1, 2, "#3DBCF2"),
)


def copy_sql(sql):
    completed = subprocess.run(
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
            f"COPY ({sql}) TO STDOUT WITH CSV HEADER",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return pd.read_csv(io.StringIO(completed.stdout))


def draw_country(ax):
    payload = json.loads((ROOT / "data" / "us-states.json").read_text(encoding="utf-8"))
    for feature in payload["features"]:
        if feature["properties"]["name"] in {"Alaska", "Hawaii"}:
            continue
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon":
            rings = [geometry["coordinates"][0]]
        else:
            rings = [part[0] for part in geometry["coordinates"]]
        for ring in rings:
            ax.plot([point[0] for point in ring], [point[1] for point in ring], color="#c8c2b8", linewidth=0.35, zorder=1)
    ax.set_xlim(-128, -66)
    ax.set_ylim(23, 50)
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#f7f4ee")
    ax.tick_params(colors=MUTED, labelsize=7, length=0)
    for spine in ax.spines.values():
        spine.set_color("#ececec")


def mark_colors(values):
    colors = np.full(len(values), "#787878", dtype=object)
    for low, high, color in MARK_BREAKS:
        colors[(values >= low) & (values <= high)] = color
    return colors


def draw_usa(ax, points):
    draw_country(ax)
    ceiling = max(float(np.percentile(points["strikes"], 98)), 2)
    ax.scatter(
        points["longitude"],
        points["latitude"],
        c=points["strikes"],
        cmap="YlOrRd",
        norm=LogNorm(vmin=1, vmax=ceiling),
        s=2,
        linewidths=0,
        zorder=2,
    )
    ax.set_xlim(-128, -66)
    ax.set_ylim(23, 50)
    panel_title(ax, "Rayos en 2018")
    ax.set_xlabel("Todo el país. El calor es la suma de rayos de cada celda.", color=MUTED, fontsize=8)


def draw_marks(ax, cloud):
    draw_country(ax)
    ax.scatter(
        cloud["longitude"],
        cloud["latitude"],
        c=mark_colors(cloud["marks"].to_numpy()),
        s=3,
        linewidths=0,
        zorder=2,
    )
    ax.set_xlim(-128, -66)
    ax.set_ylim(23, 50)
    panel_title(ax, "Lugar y percentil")
    ax.set_xlabel("Azul: 1 a 2 rayos. Rojo: 40 a 108.", color=MUTED, fontsize=8)


def draw_month_heat(ax, heat):
    ordered = heat.sort_values(["year", "month_num"])
    pivot = ordered.pivot(index="year", columns="month_num", values="number_of_strikes")
    image = ax.imshow(pivot.to_numpy(), cmap="Oranges", aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(year) for year in pivot.index])
    for row_index, year in enumerate(pivot.index):
        for column_index, month in enumerate(pivot.columns):
            value = pivot.loc[year, month]
            text = f"{value / 1_000_000:.1f}M" if value >= 1_000_000 else f"{value / 1000:.0f}k"
            ax.text(column_index, row_index, text, ha="center", va="center", fontsize=6.5, color=INK)
    ax.tick_params(length=0, colors=INK, labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.figure.colorbar(image, ax=ax, fraction=0.02, pad=0.02).outline.set_visible(False)
    panel_title(ax, "Strikes por mes y año")


def draw_box(ax, daily):
    labels = list(daily["quarter"].drop_duplicates())
    series = [daily.loc[daily["quarter"] == label, "number_of_strikes"].to_numpy() for label in labels]
    result = ax.boxplot(series, patch_artist=True, whis=1.5, flierprops={"marker": ".", "markersize": 2, "alpha": 0.35})
    ax.set_xticklabels(labels, rotation=45, ha="right")
    for box in result["boxes"]:
        box.set_facecolor(BLUE)
        box.set_edgecolor(BLUE)
    ax.set_ylim(0, None)
    ax.tick_params(axis="x", labelrotation=45)
    ax.set_ylabel("Rayos por día", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Caja por trimestre")


def draw_bins(ax, bins):
    ordered = bins.sort_values("bin_start")
    ax.bar(range(len(ordered)), ordered["locations"], color=ORANGE, width=0.86, zorder=3)
    ax.set_xticks(range(len(ordered)))
    ax.set_xticklabels(ordered["bin_label"], rotation=60, ha="right", fontsize=7)
    ax.set_ylim(0, ordered["locations"].max() * 1.08)
    ax.set_ylabel("Lugares", color=MUTED, fontsize=9)
    ax.set_xlabel("Rayos, de 10 en 10, entre 1 y 200", color=MUTED, fontsize=8)
    style_axis(ax)
    panel_title(ax, "Histograma")


def render_tableau(path=TABLEAU_PNG):
    points = copy_sql("SELECT longitude, latitude, strikes FROM public.lightning_map_points WHERE year = 2018")
    cloud = copy_sql("SELECT longitude, latitude, marks FROM public.lightning_2018_cloud")
    heat = copy_sql("SELECT year, month_num, number_of_strikes FROM public.lightning_month_heatmap")
    daily = copy_sql("SELECT quarter, number_of_strikes FROM public.lightning_daily_quarter ORDER BY quarter")
    bins = copy_sql("SELECT bin_start, bin_label, locations FROM public.lightning_strike_bins")
    plt.rcParams["font.family"] = "Segoe UI"
    figure = plt.figure(figsize=(16, 13), dpi=110)
    figure.patch.set_facecolor(PAGE)
    grid = figure.add_gridspec(3, 2, height_ratios=[1.15, 0.85, 1.05])
    draw_usa(figure.add_subplot(grid[0, 0]), points)
    draw_marks(figure.add_subplot(grid[0, 1]), cloud)
    draw_month_heat(figure.add_subplot(grid[1, :]), heat)
    draw_box(figure.add_subplot(grid[2, 0]), daily)
    draw_bins(figure.add_subplot(grid[2, 1]), bins)
    figure.suptitle(TABLEAU_TITLE, fontsize=18, color=INK, x=0.055, ha="left", fontweight="medium")
    figure.text(
        0.055,
        0.935,
        "Todo Estados Unidos en 2018, el mismo mapa con el color según la cantidad, "
        "el calor de strikes por mes y año, la caja diaria por trimestre y el histograma de 1 a 200.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )
    figure.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.08, wspace=0.18, hspace=0.55)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120, facecolor=figure.get_facecolor())
    plt.close(figure)
    print("figure", path)
    return path


HISTORIA_PNG = OUT / "historia_rayos.png"
HISTORIA_TITLE = "Historia: rayos en Estados Unidos, 2009-2018"
WHERE = (
    ("east_millions", "Costa este", ORANGE),
    ("gap_millions", "Interior este", "#9c755f"),
    ("central_millions", "Centro", BLUE),
    ("west_millions", "Oeste", GREEN),
    ("outside_millions", "Fuera del continente", PURPLE),
)
SHARE_ORDER = (
    ("east_share", "Costa este", ORANGE),
    ("gap_share", "Interior este", "#9c755f"),
    ("central_share", "Centro", BLUE),
    ("west_share", "Oeste", GREEN),
)


def polygon_rings(raw):
    geometry = json.loads(raw)
    if geometry["type"] == "Polygon":
        return geometry["coordinates"][:1]
    return [part[0] for part in geometry["coordinates"]]


def choropleth(ax, frame, column, title, norm, limits):
    polygons = []
    values = []
    for raw, value in zip(frame["polygon"], frame[column]):
        for ring in polygon_rings(raw):
            polygons.append(ring)
            values.append(value)
    array = np.asarray(values, dtype=float)
    array = np.ma.masked_less_equal(array, 0)
    collection = PolyCollection(
        polygons,
        array=array,
        cmap="YlOrRd",
        norm=norm,
        linewidths=0.05,
        edgecolors="none",
    )
    ax.add_collection(collection)
    if limits is None:
        ax.autoscale_view()
    else:
        ax.set_xlim(limits[0], limits[1])
        ax.set_ylim(limits[2], limits[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#f7f4ee")
    ax.tick_params(colors=MUTED, labelsize=6, length=0)
    for spine in ax.spines.values():
        spine.set_color("#ececec")
    colorbar = ax.figure.colorbar(collection, ax=ax, fraction=0.04, pad=0.02)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=6, length=0, colors=MUTED)
    panel_title(ax, title)
    return collection


def strike_norm(counties):
    both = np.concatenate([counties["strikes_2009"].to_numpy(), counties["strikes"].to_numpy()])
    positive = both[both > 0]
    ceiling = max(float(np.percentile(positive, 98)), 2)
    return LogNorm(vmin=1, vmax=ceiling)


def density_norm(counties):
    positive = counties.loc[counties["household_density"] > 0, "household_density"].to_numpy()
    ceiling = max(float(np.percentile(positive, 98)), float(positive.min()) * 2)
    return LogNorm(vmin=max(float(positive.min()), 0.01), vmax=ceiling)


def draw_where(ax, annual):
    for column, name, color in WHERE:
        ax.plot(annual["year"], annual[column], color=color, marker="o", linewidth=2, label=name, zorder=3)
    ax.set_ylim(0, annual["central_millions"].max() * 1.45)
    ax.set_xticks(list(annual["year"]))
    ax.set_ylabel("Millones", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Dónde aumentaron los rayos")
    ax.legend(frameon=False, fontsize=7, labelcolor=INK, loc="upper left", ncol=2)


def draw_share_lines(ax, annual):
    for column, name, color in SHARE_ORDER:
        ax.plot(annual["year"], annual[column] * 100, color=color, marker="o", linewidth=2, label=name, zorder=3)
    ax.set_ylim(0, 60)
    ax.set_xticks(list(annual["year"]))
    ax.set_ylabel("Parte del continente (%)", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Parte regional dentro del continente")
    ax.legend(frameon=False, fontsize=7, labelcolor=INK, loc="upper right")


def draw_quartile_bars(ax, frame, title):
    part = frame.copy()
    part["order"] = part["quartile"].str[:2]
    part = part.sort_values("order")
    positions = np.arange(len(part))
    width = 0.24
    ax.bar(positions - width, part["strike_share"] * 100, width=width, color=ORANGE, label="Rayos", zorder=3)
    ax.bar(positions, part["area_share"] * 100, width=width, color=BLUE, label="Territorio", zorder=3)
    ax.bar(positions + width, part["household_share"] * 100, width=width, color=GREEN, label="Hogares", zorder=3)
    ax.set_xticks(positions)
    ax.set_xticklabels(["Q1\nmenos denso", "Q2", "Q3", "Q4\nmás denso"], fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Parte del total (%)", color=MUTED, fontsize=9)
    style_axis(ax)
    ax.set_title(title, loc="left", fontsize=13, color=INK, pad=34, fontweight="medium")
    ax.legend(
        frameon=False,
        fontsize=8,
        labelcolor=INK,
        loc="lower left",
        bbox_to_anchor=(0, 1.02),
        ncol=3,
        borderaxespad=0,
        handlelength=1.2,
        columnspacing=1.1,
    )


def render_historia(path=HISTORIA_PNG):
    annual = pd.read_csv(OUT / "annual.csv")
    quartiles = pd.read_csv(OUT / "lightning_household_quartile.csv")
    counties = copy_sql(
        "SELECT polygon, strikes, strikes_2009, household_density FROM public.lightning_county_2018"
    )
    tracts = copy_sql(
        "SELECT state, polygon, strikes FROM public.lightning_tract_2018 "
        "WHERE state IN ('Texas', 'Oklahoma', 'Kansas')"
    )
    strikes = strike_norm(counties)
    density = density_norm(counties)
    country = (-128, -66, 23, 50)
    plt.rcParams["font.family"] = "Segoe UI"
    figure = plt.figure(figsize=(16, 22), dpi=100)
    figure.patch.set_facecolor(PAGE)
    grid = figure.add_gridspec(5, 6, height_ratios=[1, 1, 1.25, 1.15, 1.15])
    draw_annual(figure.add_subplot(grid[0, 0:3]), annual)
    draw_where(figure.add_subplot(grid[0, 3:6]), annual)
    draw_share_lines(figure.add_subplot(grid[1, 0:3]), annual)
    centroid = figure.add_subplot(grid[1, 3:6])
    draw_centroid(centroid, annual)
    panel_title(centroid, "Centro de masa de los rayos")
    choropleth(figure.add_subplot(grid[2, 0:2]), counties, "strikes_2009", "Rayos en 2009 sobre el territorio", strikes, country)
    choropleth(figure.add_subplot(grid[2, 2:4]), counties, "strikes", "Territorio: rayos por condado en 2018", strikes, country)
    choropleth(figure.add_subplot(grid[2, 4:6]), counties, "household_density", "Territorio: hogares por km² en 2018", density, country)
    for index, name in enumerate(("Texas", "Oklahoma", "Kansas")):
        part = tracts[tracts["state"] == name]
        axis = figure.add_subplot(grid[3, index * 2 : index * 2 + 2])
        positive = part.loc[part["strikes"] > 0, "strikes"]
        norm = LogNorm(vmin=1, vmax=max(float(np.percentile(positive, 98)), 2))
        choropleth(axis, part, "strikes", f"{name} 2018 sobre el territorio", norm, None)
        axis.set_xlabel(f"{part['strikes'].sum() / 1_000_000:.1f} millones de rayos", color=MUTED, fontsize=8)
    counties_q = quartiles[quartiles["scope"] == "Condados de EE.UU."]
    tracts_q = quartiles[quartiles["scope"] == "Tractos de Texas, Oklahoma y Kansas"]
    draw_quartile_bars(figure.add_subplot(grid[4, 0:3]), counties_q, "Rayos por cuartil de hogares, condados")
    draw_quartile_bars(figure.add_subplot(grid[4, 3:6]), tracts_q, "Rayos por cuartil de hogares, tres estados")
    start = float(annual.iloc[0]["all_millions"])
    end = float(annual.iloc[-1]["all_millions"])
    figure.suptitle(HISTORIA_TITLE, fontsize=18, color=INK, x=0.04, ha="left", fontweight="medium")
    figure.text(
        0.04,
        0.965,
        f"El archivo pasa de {start:.1f} a {end:.1f} millones. "
        "2009 y 2018 comparten la escala de los condados. "
        "Texas, Oklahoma y Kansas se ven por tracto.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )
    figure.subplots_adjust(left=0.05, right=0.98, top=0.94, bottom=0.04, wspace=0.45, hspace=0.62)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=110, facecolor=figure.get_facecolor())
    plt.close(figure)
    print("figure", path, "counties", len(counties), "tracts", len(tracts))
    return path


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tableau":
        render_tableau()
    elif len(sys.argv) > 1 and sys.argv[1] == "historia":
        render_historia()
    else:
        render()

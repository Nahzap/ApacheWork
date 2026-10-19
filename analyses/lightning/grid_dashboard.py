"""Official board for the second exercise: U.S. lightning, 2009-2018.

Reads the summaries already written by the story scripts. Does not reread
the 12 million-row file and does not rewrite the Superset dashboards.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
PNG = OUT / "ejercicio_2_oficial.png"

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


if __name__ == "__main__":
    render()

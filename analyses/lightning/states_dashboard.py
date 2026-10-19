"""Official board for Texas, Oklahoma and Kansas in 2018.

Uses the county table and the tract quartiles already prepared. Does not
reread the 12 million-row file and does not rewrite the Superset dashboards.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.collections import PolyCollection
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
PNG = OUT / "texas_oklahoma_kansas_2018.png"
STATES = ("Texas", "Oklahoma", "Kansas")

INK = "#1c1c1c"
MUTED = "#5e5e5e"
GRID = "#e4e4e4"
PAGE = "#f6f4ef"
BLUE = "#4C78A8"
ORANGE = "#F58518"
PALE = "#f2c39a"
CMAP = LinearSegmentedColormap.from_list("strikes", ["#fff4e8", "#f58518", "#7a2e0e"])


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
    ax.set_title(text, loc="left", fontsize=13, color=INK, pad=8, fontweight="medium")


def rings(raw):
    geometry = json.loads(raw)
    if geometry["type"] == "Polygon":
        return geometry["coordinates"][:1]
    return [polygon[0] for polygon in geometry["coordinates"]]


def draw_state(ax, frame, name):
    part = frame[frame["state"] == name]
    polygons = []
    values = []
    for row in part.itertuples(index=False):
        for ring in rings(row.polygon):
            polygons.append(ring)
            values.append(row.strikes_sum)
    collection = PolyCollection(
        polygons,
        array=pd.Series(values, dtype=float).to_numpy(),
        cmap=CMAP,
        linewidths=0.15,
        edgecolors="#ffffff",
    )
    ax.add_collection(collection)
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#f7f4ee")
    ax.tick_params(colors=MUTED, labelsize=7, length=0)
    for spine in ax.spines.values():
        spine.set_color("#ececec")
    panel_title(ax, f"{name} 2018")
    colorbar = ax.figure.colorbar(collection, ax=ax, fraction=0.046, pad=0.04)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=7, length=0, colors=MUTED)
    millions = part["strikes_sum"].sum() / 1_000_000
    ax.set_xlabel(f"{millions:.1f} million strikes", color=MUTED, fontsize=8)


def draw_cities(ax, cities):
    order = cities.set_index("state").loc[list(STATES)]
    positions = range(len(STATES))
    ax.bar([item - 0.18 for item in positions], order["within_80km"] * 100, width=0.36, color=ORANGE, label="Within 80 km", zorder=3)
    ax.bar([item + 0.18 for item in positions], order["within_150km"] * 100, width=0.36, color=BLUE, label="Within 150 km", zorder=3)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(list(STATES))
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of strikes (%)", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Near a large city")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left")


def draw_tracts(ax, quartiles):
    labels = ["Q1\nleast dense", "Q2", "Q3", "Q4\nmost dense"]
    colors = (ORANGE, BLUE, "#54A24B")
    width = 0.24
    for index, state in enumerate(STATES):
        part = quartiles[quartiles["scope"] == f"{state} tracts"].copy()
        part["order"] = part["quartile"].str[:2]
        part = part.sort_values("order")
        offset = (index - 1) * width
        ax.bar(
            [item + offset for item in range(4)],
            part["strike_share"] * 100,
            width=width,
            color=colors[index],
            label=state,
            zorder=3,
        )
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of strikes (%)", color=MUTED, fontsize=9)
    style_axis(ax)
    panel_title(ax, "Tracts, by households per km²")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper right", ncol=3)


def render(path=PNG):
    counties = pd.read_csv(OUT / "lightning_location_metrics.csv")
    counties = counties[(counties["year_label"] == 2018) & (counties["state"].isin(STATES))].copy()
    quartiles = pd.read_csv(OUT / "lightning_household_quartile.csv")
    payload = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    cities = pd.DataFrame(payload["cities"])

    plt.rcParams["font.family"] = "Segoe UI"
    figure = plt.figure(figsize=(16, 12), dpi=110)
    figure.patch.set_facecolor(PAGE)
    grid = figure.add_gridspec(2, 3, height_ratios=[1.15, 0.9])
    for index, name in enumerate(STATES):
        draw_state(figure.add_subplot(grid[0, index]), counties, name)
    draw_cities(figure.add_subplot(grid[1, 0:2]), cities)
    draw_tracts(figure.add_subplot(grid[1, 2]), quartiles)
    texas = cities.set_index("state").loc["Texas"]
    figure.suptitle(
        "Texas, Oklahoma, and Kansas, 2018",
        fontsize=18,
        color=INK,
        x=0.055,
        ha="left",
        fontweight="medium",
    )
    figure.text(
        0.055,
        0.935,
        "The 2018 strikes fall on the land, not in the dense neighborhoods. "
        f"In Texas, {texas['within_150km'] * 100:.0f}% fall within 150 km of a large city. "
        "In the tracts, the densest quartile keeps under 1% of the strikes in each state.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )
    figure.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.07, wspace=0.28, hspace=0.38)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120, facecolor=figure.get_facecolor())
    plt.close(figure)
    print("figure", path, "counties", len(counties))
    return path


if __name__ == "__main__":
    render()

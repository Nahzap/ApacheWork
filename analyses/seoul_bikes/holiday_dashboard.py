"""Official board for the Seoul holiday comparison.

Two charts, the ones the exercise asks for. Adjacent days keeps the calendar
order. Matching weekdays groups every Monday, then every Tuesday, through
Sunday, and the background color marks that weekday through the last day.
Holiday is orange. No holiday is blue. Each bar is the daily total.
Does not rewrite the Superset dashboard.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "outputs" / "_seoul_holiday_days.csv"
PNG = ROOT / "outputs" / "ejercicio_3_fiel.png"

INK = "#1c1c1c"
MUTED = "#5e5e5e"
GRID = "#e6e6e6"
PAGE = "#f6f4ef"
ORANGE = "#F58518"
BLUE = "#4C78A8"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_ES = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
}
WEEKDAY_COLORS = {
    "Monday": "#5B8FF9",
    "Tuesday": "#5AD8A6",
    "Wednesday": "#F6BD16",
    "Thursday": "#E8684A",
    "Friday": "#6DC8EC",
    "Saturday": "#9270CA",
    "Sunday": "#FF99C3",
}


def style_axis(ax):
    ax.set_facecolor("white")
    ax.tick_params(colors=INK, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 42000)
    ax.set_ylabel("Total rented bikes", color=MUTED, fontsize=9)
    for spine in ax.spines.values():
        spine.set_color("#ececec")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def totals(frame):
    holiday = frame["holiday_total"]
    regular = frame["regular_total"]
    values = holiday.where(holiday.notna(), regular).astype(float)
    colors = [ORANGE if pd.notna(mark) else BLUE for mark in holiday]
    return values.to_numpy(), colors


def draw_adjacent(ax, frame):
    ordered = frame.sort_values("day_key").reset_index(drop=True)
    values, colors = totals(ordered)
    ax.bar(range(len(ordered)), values, color=colors, width=1.0, zorder=3)
    step = 14
    ticks = list(range(0, len(ordered), step))
    ax.set_xticks(ticks)
    ax.set_xticklabels(ordered.loc[ticks, "day_key"], rotation=40, ha="right", fontsize=7)
    ax.set_xlim(-0.5, len(ordered) - 0.5)
    style_axis(ax)
    ax.set_title("Adjacent days", loc="left", fontsize=14, color=INK, pad=8, fontweight="medium")


def draw_matching(ax, frame):
    ordered = frame.sort_values("weekday_day").reset_index(drop=True)
    values, colors = totals(ordered)
    names = ordered["weekday_day"].str.split(" · ").str[1]
    start = 0
    current = names.iloc[0]
    for index, name in enumerate(list(names) + [None]):
        if name == current:
            continue
        ax.axvspan(start - 0.5, index - 0.5, color=WEEKDAY_COLORS[current], alpha=0.28, zorder=0)
        ax.text(
            (start + index - 1) / 2,
            40000,
            WEEKDAY_ES[current],
            ha="center",
            va="top",
            fontsize=9,
            color=INK,
        )
        start = index
        current = name
    ax.bar(range(len(ordered)), values, color=colors, width=1.0, zorder=3)
    step = 14
    groups = []
    for name in WEEKDAYS:
        block = [int(item) for item in ordered.index[names == name]]
        groups.append(block[::step])
    ticks = []
    for group in groups:
        if ticks and group[0] - ticks[-1] < step:
            ticks.pop()
        ticks.extend(group)
    labels = list(ordered.loc[ticks, "weekday_day"])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=60, ha="right", rotation_mode="anchor", fontsize=7)
    ax.set_xlim(-0.5, len(ordered) - 0.5)
    style_axis(ax)
    ax.set_title("Matching weekdays", loc="left", fontsize=14, color=INK, pad=8, fontweight="medium")


def render(path=PNG):
    frame = pd.read_csv(CSV)
    plt.rcParams["font.family"] = "Segoe UI"
    figure, axes = plt.subplots(2, 1, figsize=(16, 12), dpi=110)
    figure.patch.set_facecolor(PAGE)
    draw_adjacent(axes[0], frame)
    draw_matching(axes[1], frame)
    handles = [
        Patch(facecolor=BLUE, label="No holiday"),
        Patch(facecolor=ORANGE, label="Holiday"),
    ]
    figure.legend(handles=handles, frameon=False, loc="upper right", bbox_to_anchor=(0.98, 0.97), labelcolor=INK)
    figure.suptitle(
        "Impact of Holidays on Seoul Bike Rentals in 2017 and 2018.",
        fontsize=16,
        color=INK,
        x=0.06,
        ha="left",
        fontweight="medium",
    )
    figure.text(
        0.06,
        0.935,
        "Functioning Day = Yes. Cada barra es el total del día. Adjacent days sigue el calendario. "
        "Matching weekdays junta los lunes, después los martes, y así hasta el domingo.",
        fontsize=10,
        color=MUTED,
        ha="left",
    )
    figure.subplots_adjust(left=0.07, right=0.98, top=0.90, bottom=0.16, hspace=0.55)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120, facecolor=figure.get_facecolor())
    official = path.with_name("ejercicio_2_oficial.png")
    if official != path:
        try:
            official.write_bytes(path.read_bytes())
            print("figure", official)
        except OSError:
            print("figure", path, "(oficial abierto, no se pudo reemplazar)")
    plt.close(figure)
    print("figure", path)
    return path


if __name__ == "__main__":
    render()

# Lightning in the United States, 2009-2018

The file has 12,875,911 rows: `date`, `number_of_strikes`, `x_coord` (longitude), and `y_coord` (latitude). The native grid is 0.1°. Only four years are complete, January through December: 2009, 2012, 2015, and 2018. The other years in the title are absent and are not drawn as zero.

The source CSV is not redistributed. On this machine it is `D:\Coursera\Course 2\tableau_main_2009_to_2018.csv`. Another path is set with `LIGHTNING_CSV`.

## Three sentences from the video, measured

**“Lightning strikes in the U.S. have increased 50% over the last decade.”**

Across the whole file, 2009 sums to 30.1 million and 2018 sums to 44.6 million: +48%. The video notes 30.1M and 45M, and rounds the increase to 50%. In the continental cut (latitude 24.5 to 49.5, longitude −125 to −66.5) the change is from 29.2M to 39.4M, +35%. 2012 is 28.8M, below 2009. It is not a rise every year.

**“Lightning strikes have moved from the East Coast to the Central Mainlands over the last decade.”**

Inside the continent, the East Coast (longitude ≥ −83) goes from 23.3% to 21.3% and the center (−103 to −90) stays at 42.3%. In millions, the East Coast rises from 6.8 to 8.4 and the center from 12.3 to 16.7. The center of mass moves about 62 km west, from (−91.76, 34.78) to (−92.43, 34.68). Both regions gain strikes. The place change that does show up in the file is outside the cut: south of 24.5° goes from 0.6M to 4.4M.

**“Most number of lightning strikes in 2018 happened in densely populated household areas.”**

The lightning file has no households. It was joined to the 2018 5-year American Community Survey (tables B11001, households, and B01003, population) and the 2018 TIGER boundaries. In the counties, the quartile with the most households per km² holds 79% of households, 13% of the land, and 19% of the strikes that fall inside a county. The rank correlation between households per km² and strikes per km² is −0.01.

In the tracts of Texas, Oklahoma, and Kansas the same quartile holds 27% of households, 0.4% of the land, and 0.5% of the strikes. By state, the strike share in that quartile is Texas 0.6%, Oklahoma 0.6%, and Kansas 0.2%. Assigning each 0.1° cell to tracts splits 16 interior points, because an urban tract is smaller than the cell.

The strikes follow the land. They do not concentrate in the neighborhoods with the most households per km².

## Maps

Longitude comes first in the deck.gl geometry, because that is the map order. The text copied to Google Maps is the reverse: latitude, longitude. A Dallas cell is `32.78, -96.80`. Pasting longitude first makes Google read an impossible latitude and sends the point toward Antarctica.

The basemap is OpenStreetMap through MapLibre. Counties and tracts are drawn on top, at opacity 46, so the place name stays under the color.

## Run order

Each script publishes to Superset. Run them in this order, because the last one leaves the dashboard in the published state:

```powershell
python analyses/lightning/lightning_story.py
python analyses/lightning/lightning_territory.py
python analyses/lightning/lightning_basemap.py
python analyses/lightning/lightning_labels.py
```

`lightning_story.py` rewrites the annual charts. `lightning_territory.py` downloads the ACS and the shapefiles into `outputs/census/` (that folder is not versioned) and builds counties and tracts. `lightning_basemap.py` assigns each 0.1° cell to a county. `lightning_labels.py` sums 2009 by county, puts every map on the same basemap, and removes the grids that covered the names.

## Location Metrics

The second dashboard, `Location Metrics`, comes from `location_metrics.py`. The map uses the territory counties, the same basemap, with names under the color. Each county carries the strike count of its cells. It is one query, and moving the map does not repeat it. **Interactive Filter** chooses the year and moves the three **Metrics for the Year** figures: total, average, and maximum. A click on a place moves only **Location Metrics**. Another click shows every place again. The basemap and the latitude-then-longitude order match the previous dashboard.

```powershell
python analyses/lightning/location_metrics.py
```

## What stays in the repository

| Path | Contents |
| --- | --- |
| `figures/` | Six review figures, drawn with seaborn |
| `outputs/annual.csv` | Totals, regions, and center of mass for the four years |
| `outputs/summary.json` | The same summary as JSON |
| `outputs/household_summary.json` | Household quartiles and the correlation |
| `outputs/lightning_household_quartile.csv` | Long table of those quartiles |
| `data/us-states.json` | State outline used on the first review map |

The cell tables and the polygons are regenerated. They weigh tens of megabytes and are not needed to read the result.

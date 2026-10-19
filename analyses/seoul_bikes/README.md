# Seoul bike rentals, 2018

Maintenance question: on weekdays in 2018, which hour between 8 a.m. and 5 p.m. has the fewest rented bikes?

The source file is not redistributed. On this machine it is `D:\Coursera\Course 2\Seoul bicycle rental dataset - Seoul bicycle rental dataset.csv`. Another path is set with `SEOUL_CSV`.

## Cut

- Year 2018.
- Monday through Friday.
- The maintenance window is 8 a.m. through 5 p.m., inclusive.
- Each hour's average is the mean of `Rented Bike Count` in that cut. Pandas computes the mean. Superset draws the column.

## Result

Between 8 a.m. and 5 p.m., the lowest mean is **10 a.m.**, at 548.5 bikes. At 8 a.m. the mean is 1314.0 and at 5 p.m. it is 1204.0.

10 a.m. is the lowest hour in that window on **171 of 240** days and in **41 of 48** ISO weeks. On 23 days the minimum is 8 a.m.

The 10 a.m. average does not mean every morning is empty. The script also keeps the hour-by-hour, week-by-week, and day-by-day series.

## How to run it

The local Superset described in `deploy/superset.md` has to be up. The script rewrites the Seoul maintenance dashboard.

```powershell
python analyses/seoul_bikes/seoul_detail.py
```

The small tables the script loads stay in `outputs/`.

## Holidays, 2017 and 2018

`seoul_holidays.py` builds a second dashboard and does not touch the maintenance one. It compares each holiday's total with the neighboring regular days and with the same weekday. It uses only days with Functioning Day = Yes.

```powershell
python analyses/seoul_bikes/seoul_holidays.py
```

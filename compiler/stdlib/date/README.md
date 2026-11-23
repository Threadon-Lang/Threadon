# date

Pure-Threadon Gregorian calendar helpers. Dates are proleptic Gregorian
(`YYYY-MM-DD`, years >= 1), and day counts are `Int64` days since
1970-01-01, so dates before the epoch are negative.

```threadon
import date

def main() -> Int32
    print(date.is_leap(2000))                       # True
    print(date.weekday(2024, 1, 1))                 # 0 (Monday)
    print(date.add_days("2024-02-28", 1))           # 2024-02-29
    print(date.days_between("2024-01-01", "2024-01-08"))  # 7
    return 0
```

| Function | Result |
| --- | --- |
| `is_leap(year)` | whether `year` is a Gregorian leap year |
| `days_in_month(year, month)` | 28..31, or `0` for an invalid month |
| `days_from_civil(year, month, day)` | `Int64` days since 1970-01-01 |
| `civil_from_days(z)` | ISO `YYYY-MM-DD` for a day count |
| `weekday(year, month, day)` | `0` = Monday through `6` = Sunday |
| `add_days(date, delta)` | ISO date shifted by `delta` days |
| `days_between(a, b)` | signed `Int64` day count from `a` to `b` |

The civil/date conversions follow Howard Hinnant's algorithms. Threadon's
integer `/` and `%` truncate toward zero; the era calculations bias negative
values by a full era (400 years / 146097 days) to emulate floor division, so
all dates back to year 1 work. `civil_from_days` pads years 1..9999 to four
digits; larger years use more digits.

`add_days` parses strictly `YYYY-MM-DD` (four digit year, two digit month and
day, all digits). An invalid or impossible date returns `""`;
`days_between` treats an invalid endpoint as day 0. `days_from_civil` and
`weekday` assume a valid date; they do not validate their inputs.

Tests: `python3 -m threadon --run-tests compiler/stdlib/date/test.th`.

"""The rent trend for each ZIP code, from the index Zillow publishes for researchers (one row per ZIP, one column
per month, going back years). It gives every ZIP a trend from day one, before this project's own history builds up."""

import csv

SOURCE = "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv"
MONTHS_KEPT = 36


def parse(lines, wanted):
    """{zip: {"latest", "month", "year_change" (percent), "series": [[month, rent], ...]}} for the wanted ZIP codes."""
    reader = csv.reader(lines)
    header = next(reader)
    months = [(index, name[:7]) for index, name in enumerate(header) if name[:2] == "20" and name[4:5] == "-"]
    trends = {}
    for row in reader:
        if len(row) < 3 or row[2].zfill(5) not in wanted:
            continue
        series = []
        for index, month in months:
            try:
                series.append([month, round(float(row[index]))])
            except (ValueError, IndexError):
                continue
        if not series:
            continue
        series = series[-MONTHS_KEPT:]
        month, latest = series[-1]
        before = dict(series).get(f"{int(month[:4]) - 1}{month[4:]}")
        trends[row[2].zfill(5)] = {
            "latest": latest, "month": month,
            "year_change": round((latest / before - 1) * 100, 1) if before else None,
            "series": series,
        }
    return trends


def read(get, wanted):
    return parse(get(SOURCE, timeout=120).decode("utf-8", "replace").splitlines(), wanted)

"""Rows from a public Power BI report.

Some counties publish their crime figures only as a Power BI dashboard "published to web". Such a dashboard
loads its numbers from a public data service, with the key that is in its own link, and the same service
answers a request for the rows behind the charts. Three requests: the dashboard page (which names the data
host), the report's description (which gives the model's number), then the rows, a window at a time.
"""

import base64
import gzip
import json
import re
import time

WINDOW = 30000              # the most rows the service returns at once
GZIP = bytes([31, 139])


def key(view_url):
    """The report's key, which sits base64-encoded in its public link."""
    try:
        token = view_url.split("r=", 1)[1].split("&")[0]
        return json.loads(base64.b64decode(token + "=" * (-len(token) % 4)))["k"]
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError(f"no report key in {view_url}") from error


def api_host(page_html):
    """The data service the dashboard page says it loads from."""
    match = re.search(r"resolvedClusterUri\s*=\s*'([^']+)'", page_html or "")
    if not match:
        raise ValueError("the dashboard page does not name its data host")
    return match.group(1).rstrip("/").replace("-redirect", "-api")


def text(raw):
    if raw[:2] == GZIP:
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", "replace")


def column(alias, name):
    return {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": name}}


def query(model, tables, columns, date_column, start, count=WINDOW, restart=None):
    """A request for `columns` ([(alias, column)]) of `tables` ({alias: table}), for rows whose `date_column`
    is on or after the day `start`. Each distinct combination of values comes back once."""
    window = {"Count": count}
    if restart:
        window["RestartTokens"] = restart
    return {"version": "1.0.0", "cancelQueries": [], "modelId": model, "queries": [{"QueryId": "", "Query": {"Commands": [{
        "SemanticQueryDataShapeCommand": {
            "Query": {
                "Version": 2,
                "From": [{"Name": alias, "Entity": table, "Type": 0} for alias, table in tables.items()],
                "Select": [dict(column(alias, name), Name=f"{tables[alias]}.{name}") for alias, name in columns],
                "Where": [{"Condition": {"Comparison": {"ComparisonKind": 2,                 # greater than or equal
                                                        "Left": column(*date_column),
                                                        "Right": {"Literal": {"Value": f"datetime'{start}T00:00:00'"}}}}}],
            },
            "Binding": {"Primary": {"Groupings": [{"Projections": list(range(len(columns)))}]},
                        "DataReduction": {"DataVolume": 3, "Primary": {"Window": window}}, "Version": 1},
        }}]}}]}


def decode(reply):
    """(rows, restart tokens or None). The reply is compact: a value equal to the one in the row above is left
    out (bitmask "R"), so is a blank one (bitmask "Ø"), and text is a number pointing into a dictionary."""
    try:
        ds = reply["results"][0]["result"]["data"]["dsr"]["DS"][0]
        listed = ds["PH"][0]["DM0"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"not rows: {json.dumps(reply)[:300]}") from error
    dicts, rows, schema, previous = ds.get("ValueDicts") or {}, [], None, None
    for row in listed:
        schema = row.get("S", schema)
        given, repeat, blank, values = iter(row.get("C") or []), row.get("R", 0), row.get("Ø", 0), []
        for i, described in enumerate(schema):
            if repeat & (1 << i):
                values.append(previous[i])
            elif blank & (1 << i):
                values.append(None)
            else:
                value = next(given)
                if "DN" in described and isinstance(value, int):
                    value = dicts[described["DN"]][value]
                values.append(value)
        previous = values
        rows.append(values)
    return rows, ds.get("RT") or None


def rows(get, post, view_url, tables, columns, date_column, start, sleep=time.sleep, max_pages=20):
    """Every row on or after `start`, asking again from where each window ended until none is left."""
    report = key(view_url)
    headers = {"X-PowerBI-ResourceKey": report, "Accept": "application/json"}
    host = api_host(text(get(view_url)))
    described = json.loads(text(get(f"{host}/public/reports/{report}/modelsAndExploration?preferReadOnlySession=true", headers=headers)))
    model = described["models"][0]["id"]
    found, restart = [], None
    for _ in range(max_pages):
        sleep(1)
        body = json.dumps(query(model, tables, columns, date_column, start, restart=restart)).encode()
        got, restart = decode(json.loads(text(post(f"{host}/public/reports/querydata?synchronous=true", body,
                                                   dict(headers, **{"Content-Type": "application/json"})))))
        found += got
        if not restart:
            return found
    raise RuntimeError(f"the report did not end after {max_pages} windows of {WINDOW} rows")

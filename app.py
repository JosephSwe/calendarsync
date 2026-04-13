from flask import Flask, Response
import requests
import re
import time

app = Flask(__name__)

SOURCE_ICS_URL = "https://outlook.office365.com/owa/calendar/33dbc5834955435ebd712deab88f7b57@hemmaplan.com/bca66f2760634c68917a0aabb5c6568b12512357159274592687/calendar.ics"
OUTPUT_TZID = "Europe/Stockholm"
CACHE_TTL_SECONDS = 300  # 5 minuter

session = requests.Session()

_cached_body = None
_cached_at = 0.0

# Vanliga datum/tid-fält i ICS som Google bryr sig om.
DT_FIELD_RE = re.compile(
    r'^(?P<name>DTSTART|DTEND|RECURRENCE-ID|RDATE|EXDATE|DUE|COMPLETED)'
    r'(?P<params>(?:;[^:]+)*)'
    r':(?P<value>.+)$',
    re.IGNORECASE
)

UNFOLD_RE = re.compile(r'\r?\n[ \t]')


def unfold_ics(text: str) -> str:
    # ICS kan ha radbrytningar där nästa rad börjar med mellanslag eller tab.
    return UNFOLD_RE.sub('', text.replace('\r\n', '\n')).replace('\r', '\n')


def fold_ics_line(line: str, limit: int = 75) -> str:
    """
    Faller tillbaka till standard-fällning av ICS-rader.
    Enkelt och stabilt nog för Google/Outlook.
    """
    if len(line) <= limit:
        return line

    parts = [line[:limit]]
    rest = line[limit:]
    while rest:
        parts.append(" " + rest[:limit - 1])
        rest = rest[limit - 1:]
    return "\r\n".join(parts)


def rewrite_datetime_line(line: str) -> str:
    m = DT_FIELD_RE.match(line)
    if not m:
        return line

    name = m.group("name").upper()
    params = m.group("params") or ""
    value = m.group("value").strip()

    # All-day events ska lämnas som de är.
    if "VALUE=DATE" in params.upper():
        return line

    # Ta bort eventuell gammal TZID, men behåll andra parametrar.
    param_items = [p for p in params.split(";") if p]
    kept_params = []
    for p in param_items:
        if p.upper().startswith("TZID="):
            continue
        kept_params.append(p)

    # Sätt vår tidszon på alla datum/tid-fält.
    kept_params.append(f"TZID={OUTPUT_TZID}")
    new_params = "".join(f";{p}" for p in kept_params)

    # Viktigt:
    # Vi konverterar INTE klockslaget. Vi bara märker det som Stockholm-tid.
    # Det är det som brukar fixa "allt blir 2 timmar fel" från Outlook-ICS.
    def fix_token(token: str) -> str:
        token = token.strip()
        if re.fullmatch(r"\d{8}T\d{6}Z", token):
            return token[:-1]  # ta bort Z men behåll samma klockslag
        if re.fullmatch(r"\d{8}T\d{6}", token):
            return token
        return token

    fixed_value = ",".join(fix_token(part) for part in value.split(","))

    return f"{name}{new_params}:{fixed_value}"


def normalize_ics(raw_text: str) -> str:
    text = unfold_ics(raw_text)
    lines = text.split("\n")

    out = []
    saw_calendar = False
    saw_timezone = False

    for line in lines:
        stripped = line.strip("\r")
        if not stripped:
            continue

        upper = stripped.upper()

        if upper.startswith("BEGIN:VCALENDAR"):
            saw_calendar = True
            out.append("BEGIN:VCALENDAR")
            continue

        if upper.startswith("X-WR-TIMEZONE:"):
            out.append(f"X-WR-TIMEZONE:{OUTPUT_TZID}")
            saw_timezone = True
            continue

        # Om det saknas X-WR-TIMEZONE lägger vi in det direkt efter BEGIN:VCALENDAR senare.
        rewritten = rewrite_datetime_line(stripped)
        out.append(rewritten)

    if saw_calendar and not saw_timezone:
        fixed = []
        inserted = False
        for line in out:
            fixed.append(line)
            if not inserted and line.upper() == "BEGIN:VCALENDAR":
                fixed.append(f"X-WR-TIMEZONE:{OUTPUT_TZID}")
                inserted = True
        out = fixed

    # Folda tillbaka raderna enligt ICS-format.
    folded = "\r\n".join(fold_ics_line(line) for line in out) + "\r\n"
    return folded


def fetch_source_ics() -> str:
    global _cached_body, _cached_at

    now = time.time()
    if _cached_body and (now - _cached_at) < CACHE_TTL_SECONDS:
        return _cached_body

    r = session.get(SOURCE_ICS_URL, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (ICS proxy)",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    r.raise_for_status()

    body = r.text
    _cached_body = body
    _cached_at = now
    return body


@app.route("/")
@app.route("/calendar.ics")
def calendar():
    try:
        source = fetch_source_ics()
        fixed = normalize_ics(source)
        return Response(
            fixed,
            mimetype="text/calendar; charset=utf-8",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception as e:
        # Om Outlook ligger nere eller proxy-fetchar misslyckas,
        # levererar vi senaste fungerande versionen om vi har en.
        if _cached_body:
            fixed = normalize_ics(_cached_body)
            return Response(
                fixed,
                mimetype="text/calendar; charset=utf-8",
                headers={
                    "X-Proxy-Warning": "served-cached-copy-after-fetch-failure",
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                },
            )

        return Response(
            f"Failed to fetch ICS: {e}",
            status=502,
            mimetype="text/plain; charset=utf-8",
        )


@app.route("/healthz")
def healthz():
    return {"ok": True}

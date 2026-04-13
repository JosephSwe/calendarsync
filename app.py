from flask import Flask, Response
import requests
from datetime import datetime
import re
from zoneinfo import ZoneInfo

app = Flask(__name__)

OUTLOOK_ICS_URL = "DIN LÄNK HÄR"

def convert_time(dt_str):
    # tar 20260413T090000Z
    dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ")
    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    dt = dt.astimezone(ZoneInfo("Europe/Stockholm"))
    return dt.strftime("%Y%m%dT%H%M%S")

@app.route("/")
def calendar():
    r = requests.get(OUTLOOK_ICS_URL, timeout=20)
    data = r.text

    # hitta alla UTC tider
    matches = re.findall(r"\d{8}T\d{6}Z", data)

    for m in matches:
        fixed = convert_time(m)
        data = data.replace(m, fixed)

    # sätt rätt timezone header
    if "X-WR-TIMEZONE" not in data:
        data = "BEGIN:VCALENDAR\nX-WR-TIMEZONE:Europe/Stockholm\n" + data

    return Response(data, mimetype="text/calendar")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

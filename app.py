from flask import Flask, Response
import requests

app = Flask(__name__)

OUTLOOK_ICS_URL = "https://outlook.office365.com/owa/calendar/33dbc5834955435ebd712deab88f7b57@hemmaplan.com/bca66f2760634c68917a0aabb5c6568b12512357159274592687/calendar.ics"

@app.route("/")
def calendar():
    r = requests.get(OUTLOOK_ICS_URL, timeout=20)
    data = r.text

    # 🔧 Säker fix: se till att timezone finns (utan att förstöra tider)
    if "X-WR-TIMEZONE" not in data:
        data = data.replace(
            "BEGIN:VCALENDAR",
            "BEGIN:VCALENDAR\nX-WR-TIMEZONE:Europe/Stockholm"
        )

    return Response(data, mimetype="text/calendar")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

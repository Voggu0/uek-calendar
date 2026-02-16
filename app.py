import uuid
import time
import requests
from flask import Flask, request, Response, abort
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime
from requests.auth import HTTPBasicAuth

PLAN_URL = "https://planzajec.uek.krakow.pl/index.php?typ=G&id=171401&okres=2"

# token -> {login, password, created_at}
TOKENS = {}
TOKEN_TTL = 60 * 60 * 24 * 30  # 30 dni
CACHE_TTL = 60 * 30           # 30 minut
CACHE = {}                   # token -> (calendar, cached_at)

app = Flask(__name__)

# ---------- POMOCNICZE ----------
def clean_expired_tokens():
    now = time.time()
    for t in list(TOKENS.keys()):
        if now - TOKENS[t]["created_at"] > TOKEN_TTL:
            TOKENS.pop(t, None)
            CACHE.pop(t, None)

def generate_calendar(login, password):
    r = requests.get(
        PLAN_URL,
        auth=HTTPBasicAuth(login, password),
        timeout=10
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    cal = Calendar()

    table = soup.find("table")
    if not table:
        return cal

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 6:
            continue
        try:
            date = cols[0].text.strip()
            hours = cols[1].text.strip().split("-")
            name = cols[2].text.strip()
            lecturer = cols[3].text.strip()
            room = cols[4].text.strip()

            start = datetime.strptime(f"{date} {hours[0]}", "%Y-%m-%d %H:%M")
            end = datetime.strptime(f"{date} {hours[1]}", "%Y-%m-%d %H:%M")

            e = Event()
            e.name = name
            e.begin = start
            e.end = end
            e.location = room
            e.description = lecturer
            cal.events.add(e)
        except:
            continue
    return cal

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        login = request.form.get("login")
        password = request.form.get("password")

        if not login or not password:
            return "Podaj login i hasło.", 400

        # test logowania
        try:
            requests.get(
                PLAN_URL,
                auth=HTTPBasicAuth(login, password),
                timeout=10
            ).raise_for_status()
        except:
            return "Nieprawidłowy login lub hasło.", 403

        token = str(uuid.uuid4())
        TOKENS[token] = {
            "login": login,
            "password": password,
            "created_at": time.time()
        }

        return f"""
        <h3>Gotowe ✅</h3>
        <p>Twój link do kalendarza:</p>
        <code>{request.url_root}uek.ics?token={token}</code>
        <p>Skopiuj i dodaj do Google / Apple / Outlook.</p>
        """

    return """
    <h2>Kalendarz UEK – dla grupy</h2>
    <form method="post">
        Login UEK:<br>
        <input name="login"><br><br>
        Hasło UEK:<br>
        <input name="password" type="password"><br><br>
        <button>Generuj kalendarz</button>
    </form>
    <p>Hasło nie jest zapisywane na dysku.</p>
    """

@app.route("/uek.ics")
def calendar():
    clean_expired_tokens()
    token = request.args.get("token")
    if not token or token not in TOKENS:
        abort(403)

    now = time.time()
    if token in CACHE and now - CACHE[token][1] < CACHE_TTL:
        cal = CACHE[token][0]
    else:
        creds = TOKENS[token]
        cal = generate_calendar(creds["login"], creds["password"])
        CACHE[token] = (cal, now)

    return Response(str(cal), mimetype="text/calendar")

if __name__ == "__main__":
    app.run()

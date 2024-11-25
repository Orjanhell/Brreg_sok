import requests
from flask import Flask, render_template, request
from tabulate import tabulate

# Flask-applikasjon
app = Flask(__name__)

# Base-URLer for API-et
API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"

# Formatering og funksjoner for å hente data
def formater_adresse(adresse_data):
    if isinstance(adresse_data, list):
        return ", ".join(adresse_data)
    elif isinstance(adresse_data, str):
        return adresse_data
    return None

def hent_enhet(orgnummer):
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Feil under henting av enhet: {e}")
        return None

def søk_enheter(søkeord, maks_resultater=100):
    try:
        resultater = []
        params = {"navn": søkeord, "size": maks_resultater, "page": 0}
        response = requests.get(API_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        for enhet in data.get("_embedded", {}).get("enheter", []):
            resultater.append({
                "organisasjonsnummer": enhet["organisasjonsnummer"],
                "navn": enhet["navn"],
                "adresse": enhet.get("forretningsadresse", {})
            })

        return resultater
    except requests.exceptions.RequestException as e:
        print(f"Feil under søk: {e}")
        return []

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        søkeord = request.form["søkeord"]
        if søkeord.isdigit():
            enhet = hent_enhet(søkeord)
            return render_template("index.html", enhet=enhet)
        else:
            resultater = søk_enheter(søkeord)
            return render_template("index.html", resultater=resultater)
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)

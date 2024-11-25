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
    """Formaterer adressefeltet til en lesbar streng."""
    if isinstance(adresse_data, list):  # Hvis adresse er en liste
        return ", ".join(adresse_data)
    elif isinstance(adresse_data, str):  # Hvis adresse er en streng
        return adresse_data
    return "Ikke oppgitt"


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
        søkeord = request.form.get("søkeord", "").strip()
        resultater = []

        if søkeord.isdigit():  # Hvis organisasjonsnummer
            enhet = hent_enhet(søkeord)
            if enhet:
                adresse = enhet.get("forretningsadresse", {})
                enhet["adresse_tekst"] = formater_adresse(adresse.get("adresse", []))
                enhet["postnummer"] = adresse.get("postnummer", "Ikke oppgitt")
                enhet["poststed"] = adresse.get("poststed", "Ikke oppgitt")
                resultater.append(enhet)
        else:  # Hvis firmanavn
            enheter = søk_enheter(søkeord)
            for enhet in enheter:
                adresse = enhet.get("forretningsadresse", {})
                enhet["adresse_tekst"] = formater_adresse(adresse.get("adresse", []))
                enhet["postnummer"] = adresse.get("postnummer", "Ikke oppgitt")
                enhet["poststed"] = adresse.get("poststed", "Ikke oppgitt")
            resultater = enheter

        return render_template("index.html", resultater=resultater, søkeord=søkeord)

    return render_template("index.html", resultater=None)



if __name__ == "__main__":
    app.run(debug=True)

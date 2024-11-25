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
        hovedenhet = None
        underenheter = []

        if søkeord.isdigit():  # Hvis organisasjonsnummer
            hovedenhet = hent_enhet(søkeord)
            if hovedenhet:
                adresse = hovedenhet.get("forretningsadresse", {})
                hovedenhet["adresse_tekst"] = formater_adresse(adresse.get("adresse", []))
                hovedenhet["postnummer"] = adresse.get("postnummer", "Ikke oppgitt")
                hovedenhet["poststed"] = adresse.get("poststed", "Ikke oppgitt")

                # Hent underenheter
                underenheter = hent_underenheter(søkeord)
                for underenhet in underenheter:
                    adresse = underenhet.get("adresse", {})
                    underenhet["adresse_tekst"] = formater_adresse(adresse.get("adresse", []))
                    underenhet["postnummer"] = adresse.get("postnummer", "Ikke oppgitt")
                    underenhet["poststed"] = adresse.get("poststed", "Ikke oppgitt")

        return render_template("index.html", hovedenhet=hovedenhet, underenheter=underenheter, søkeord=søkeord)

    return render_template("index.html", hovedenhet=None, underenheter=None)



if __name__ == "__main__":
    app.run(debug=True)

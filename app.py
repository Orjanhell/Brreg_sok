from flask import Flask, render_template, request
import requests

app = Flask(__name__)

# Base-URLer for API-et
API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"

def formater_adresse(adresse_data):
    """Formaterer adressefeltet for visning."""
    adresse = ", ".join(adresse_data.get("adresse", [])) if "adresse" in adresse_data else None
    postnummer = adresse_data.get("postnummer", None)
    poststed = adresse_data.get("poststed", None)

    deler = [element for element in [adresse, postnummer, poststed] if element]
    return ", ".join(deler) if deler else "Ikke oppgitt"

def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk enhet (hovedenhet)."""
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        data["adresse"] = adresse
        return data
    except requests.exceptions.RequestException:
        return None

def hent_underenhet(orgnummer):
    """Hent detaljer om en spesifikk underenhet."""
    try:
        response = requests.get(f"{API_UNDERENHETER_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("beliggenhetsadresse", {}))
        data["adresse"] = adresse
        return data
    except requests.exceptions.RequestException:
        return None

def hent_underenheter(orgnummer):
    """Hent underenheter for en spesifikk enhet."""
    underenheter = []
    try:
        url = API_UNDERENHETER_URL
        params = {"overordnetEnhet": orgnummer, "size": 100}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        for underenhet in data.get("_embedded", {}).get("underenheter", []):
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            underenheter.append({
                "organisasjonsnummer": underenhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": underenhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse
            })

    except requests.exceptions.RequestException as e:
        print(f"Feil under henting av underenheter: {e}")
    return underenheter

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/", methods=["POST"])
def søk():
    søkeord = request.form["søkeord"]
    if søkeord.isdigit():
        # Prøv å hente som hovedenhet først
        enhet = hent_enhet(søkeord)
        if enhet:
            underenheter = hent_underenheter(søkeord)
            return render_template("index.html", enhet=enhet, underenheter=underenheter)

        # Hvis ikke funnet som hovedenhet, prøv som underenhet
        underenhet = hent_underenhet(søkeord)
        if underenhet:
            hovedenhet = hent_enhet(underenhet.get("overordnetEnhet"))
            return render_template(
                "index.html",
                enhet=hovedenhet,
                underenheter=[underenhet] if hovedenhet else []
            )

        # Ingen treff for organisasjonsnummer
        return render_template("index.html", ingen_treff=True, søkeord=søkeord)

    else:
        # Søk basert på navn
        resultater = []
        try:
            resultater += søk_enheter(søkeord, API_BASE_URL)
            resultater += søk_enheter(søkeord, API_UNDERENHETER_URL)
        except Exception as e:
            print(f"Feil under søk: {e}")
        return render_template("index.html", resultater=resultater)

if __name__ == "__main__":
    app.run(debug=True)

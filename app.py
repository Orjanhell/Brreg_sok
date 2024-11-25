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

    deler = [del for del in [adresse, postnummer, poststed] if del]
    return ", ".join(deler) if deler else "Ikke oppgitt"

def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk enhet."""
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        data["adresse"] = adresse
        return data
    except requests.exceptions.RequestException as e:
        print(f"Feil under henting av enhet: {e}")
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

def søk_enheter(søkeord):
    """Søk etter firma basert på navn."""
    resultater = []
    try:
        params = {"navn": søkeord, "size": 20}
        response = requests.get(API_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        for enhet in data.get("_embedded", {}).get("enheter", []):
            adresse = formater_adresse(enhet.get("forretningsadresse", {}))
            resultater.append({
                "organisasjonsnummer": enhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": enhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse
            })
    except requests.exceptions.RequestException as e:
        print(f"Feil under søk: {e}")
    return resultater

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/", methods=["POST"])
def søk():
    søkeord = request.form["søkeord"]
    if søkeord.isdigit():
        enhet = hent_enhet(søkeord)
        underenheter = hent_underenheter(søkeord)
        print("DEBUG - Underenheter som sendes til HTML:")
        print(underenheter)
        return render_template("index.html", enhet=enhet, underenheter=underenheter)
    else:
        resultater = søk_enheter(søkeord)
        return render_template("index.html", resultater=resultater)

if __name__ == "__main__":
    app.run(debug=True)

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

    deler = [adresse, f"{postnummer} {poststed}".strip() if postnummer or poststed else None]
    return ", ".join(filter(None, deler)) if deler else "Ikke oppgitt"


def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk enhet."""
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

        # Hent hovedenheten hvis tilgjengelig
        hovedenhet_orgnr = data.get("overordnetEnhet")
        hovedenhet = hent_enhet(hovedenhet_orgnr) if hovedenhet_orgnr else None

        return data, hovedenhet
    except requests.exceptions.RequestException:
        return None, None


def hent_underenheter(orgnummer):
    """Hent alle underenheter for en spesifikk enhet."""
    underenheter = []
    try:
        params = {"overordnetEnhet": orgnummer, "size": 100}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()

        for underenhet in data.get("_embedded", {}).get("underenheter", []):
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            underenheter.append({
                "organisasjonsnummer": underenhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": underenhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse
            })

    except requests.exceptions.RequestException:
        pass
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
    except requests.exceptions.RequestException:
        pass
    return resultater


def søk_underenheter(søkeord):
    """Søk etter underenheter basert på navn."""
    resultater = []
    try:
        params = {"navn": søkeord, "size": 20}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()

        for underenhet in data.get("_embedded", {}).get("underenheter", []):
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            resultater.append({
                "organisasjonsnummer": underenhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": underenhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse
            })
    except requests.exceptions.RequestException:
        pass
    return resultater


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/", methods=["POST"])
def søk():
    søkeord = request.form["søkeord"]
    if søkeord.isdigit():  # Hvis søket er et organisasjonsnummer
        enhet = hent_enhet(søkeord)
        if enhet:
            underenheter = hent_underenheter(søkeord)
            return render_template("index.html", enhet=enhet, underenheter=underenheter)
        else:
            underenhet, hovedenhet = hent_underenhet(søkeord)
            if underenhet:
                return render_template("index.html", enhet=hovedenhet, underenheter=[underenhet])
            else:
                return render_template("index.html", feilmelding="Ingen treff funnet for organisasjonsnummeret.")
    else:  # Hvis søket er et navn
        enheter = søk_enheter(søkeord)
        underenheter = søk_underenheter(søkeord)
        alle_resultater = enheter + underenheter

        if alle_resultater:
            return render_template("index.html", resultater=alle_resultater)
        else:
            return render_template("index.html", feilmelding="Ingen treff funnet for navnet.")

if __name__ == "__main__":
    app.run(debug=True)

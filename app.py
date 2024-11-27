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
        params = {"overordnetEnhet": orgnummer, "size": 150}
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
        params = {"navn": søkeord, "size": 150}
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
        params = {"navn": søkeord, "size": 150}
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

def filtrer_relevante_resultater(søkeord, resultater):
    """Filtrer resultater basert på samsvar mellom søkeord og resultatnavn."""
    søkeord_liste = søkeord.lower().split()  # Del opp søkeordet i ord
    relevante_resultater = []

    for resultat in resultater:
        navn = resultat.get("navn", "").lower()
        navn_ord = navn.split()

        # Tell antall ord som matcher mellom søkeord og navnet
        samsvar = sum(1 for ord in søkeord_liste if ord in navn_ord)

        # Definer dynamisk samsvarskrav
        if len(søkeord_liste) >= 4 and samsvar >= 3:  # 3 av 4 eller flere
            relevante_resultater.append(resultat)
        elif len(søkeord_liste) == 3 and samsvar >= 2:  # 2 av 3
            relevante_resultater.append(resultat)
        elif len(søkeord_liste) == 2 and samsvar == 2:  # 2 av 2
            relevante_resultater.append(resultat)
        elif len(søkeord_liste) == 1 and samsvar >= 1:  # 1 av 1
            relevante_resultater.append(resultat)

    return relevante_resultater


def søk_enheter_og_underenheter(søkeord):
    """Kombinerer resultater fra hovedenheter og underenheter basert på navn."""
    hovedenheter = søk_enheter(søkeord)
    underenheter = søk_underenheter(søkeord)

    # Filtrer resultatene basert på relevans
    hovedenheter = filtrer_relevante_resultater(søkeord, hovedenheter)
    underenheter = filtrer_relevante_resultater(søkeord, underenheter)

    return hovedenheter, underenheter


@app.route("/", methods=["GET", "POST"])
def søk():
    if request.method == "POST":
        søkeord = request.form["søkeord"].strip()

        if søkeord:  # Sjekk om søkeordet ikke er tomt
            if søkeord.replace(" ", "").isdigit():  # Hvis søket er et organisasjonsnummer
                søkeord = søkeord.replace(" ", "")
                enhet = hent_enhet(søkeord)
                if enhet:
                    underenheter = hent_underenheter(søkeord)
                    return render_template(
                        "index.html",
                        hovedenheter=[enhet],
                        underenheter=underenheter,
                        søkeord=søkeord,
                    )
                else:
                    underenhet, hovedenhet = hent_underenhet(søkeord)
                    if underenhet:
                        return render_template(
                            "index.html",
                            hovedenheter=[hovedenhet] if hovedenhet else [],
                            underenheter=[underenhet],
                            søkeord=søkeord,
                        )
                    else:
                        return render_template(
                            "index.html",
                            feilmelding="Ingen treff funnet for organisasjonsnummeret.",
                            søkeord=søkeord,
                        )
            else:  # Hvis søket er et navn
                hovedenheter, underenheter = søk_enheter_og_underenheter(søkeord)

                if not hovedenheter and not underenheter:
                    return render_template(
                        "index.html",
                        feilmelding="Ingen treff funnet for navnet.",
                        søkeord=søkeord,
                    )

                return render_template(
                    "index.html",
                    hovedenheter=hovedenheter,
                    underenheter=underenheter,
                    søkeord=søkeord,
                )

        # Hvis søkeord er tomt, bare vis startsiden
        return render_template("index.html")

    # GET-forespørsel: Bare vis startsiden
    return render_template("index.html")


@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)

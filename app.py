from flask import Flask, render_template, request, jsonify
import requests
import aiohttp
import asyncio
import time

app = Flask(__name__)

# Base-URLer for API-et
API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"
PEPPOL_API_URL = "https://directory.peppol.eu/search/1.0/json"

# Cache for EHF-status
EHF_CACHE = {}
CACHE_EXPIRATION = 86400  # 24 timer

def formater_adresse(adresse_data):
    """Formaterer adressefeltet for visning."""
    adresse = ", ".join(adresse_data.get("adresse", [])) if "adresse" in adresse_data else None
    postnummer = adresse_data.get("postnummer", None)
    poststed = adresse_data.get("poststed", None)

    deler = [adresse, f"{postnummer} {poststed}".strip() if postnummer or poststed else None]
    return ", ".join(filter(None, deler)) if deler else "Ikke oppgitt"

def filtrer_relevante_resultater(søkeord, resultater):
    """Filtrer resultater basert på samsvar mellom søkeord og resultatnavn."""
    søkeord_liste = søkeord.lower().split()
    relevante_resultater = []

    for resultat in resultater:
        navn = resultat.get("navn", "").lower()
        navn_ord = navn.split()
        samsvar = sum(1 for ord in søkeord_liste if ord in navn_ord)

        if len(søkeord_liste) >= 4 and samsvar >= 3:
            relevante_resultater.append(resultat)
        elif len(søkeord_liste) == 3 and samsvar >= 2:
            relevante_resultater.append(resultat)
        elif len(søkeord_liste) == 2 and samsvar == 2:
            relevante_resultater.append(resultat)
        elif len(søkeord_liste) == 1 and samsvar >= 1:
            relevante_resultater.append(resultat)

    return relevante_resultater

def sjekk_cache(orgnummer):
    """Sjekker cache for EHF-status."""
    if orgnummer in EHF_CACHE:
        cached = EHF_CACHE[orgnummer]
        if time.time() - cached["timestamp"] < CACHE_EXPIRATION:
            return cached["ehf"]
    return None

async def sjekk_ehf_peppol_async(orgnummer):
    """Sjekker om en enhet støtter EHF via Peppol Directory asynkront."""
    cached_status = sjekk_cache(orgnummer)
    if cached_status is not None:
        return cached_status

    params = {"participant": f"iso6523-actorid-upis::0192:{orgnummer}"}
    try:
        async with aiohttp.ClientSession() as session:
            while True:  # Loop for å håndtere 429-feil
                async with session.get(PEPPOL_API_URL, params=params, timeout=10) as response:
                    if response.status == 429:
                        print(f"Rate limit nådd for {orgnummer}. Venter...")
                        await asyncio.sleep(1)  # Vent før ny forespørsel
                        continue  # Prøv igjen
                    elif response.status == 200:
                        data = await response.json()
                        ehf_status = data.get("total-result-count", 0) > 0
                        EHF_CACHE[orgnummer] = {"ehf": ehf_status, "timestamp": time.time()}
                        return ehf_status
                    else:
                        print(f"HTTP-feil for {orgnummer}: {response.status}")
                        return False
    except aiohttp.ContentTypeError:
        print(f"Uventet MIME-type for {orgnummer}. Kunne ikke dekode JSON.")
        return False
    except Exception as e:
        print(f"Feil ved Peppol Directory-sjekk for {orgnummer}: {e}")
        return False

async def sjekk_ehf_for_flere(orgnummere):
    """Sjekker EHF-støtte for flere organisasjonsnumre asynkront."""
    tasks = [sjekk_ehf_peppol_async(orgnummer) for orgnummer in orgnummere]
    return await asyncio.gather(*tasks)

def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk enhet."""
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        ehf_støtte = asyncio.run(sjekk_ehf_peppol_async(orgnummer))
        data["adresse"] = adresse
        data["ehf"] = ehf_støtte
        return data
    except requests.exceptions.RequestException as e:
        print(f"Feil ved henting av enhet {orgnummer}: {e}")
        return None

def hent_underenheter(orgnummer):
    """Hent alle underenheter for en spesifikk hovedenhet."""
    underenheter = []
    try:
        params = {"overordnetEnhet": orgnummer, "size": 100}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()

        orgnummere = [underenhet.get("organisasjonsnummer", "") for underenhet in data.get("_embedded", {}).get("underenheter", [])]
        ehf_status_liste = asyncio.run(sjekk_ehf_for_flere(orgnummere))

        for underenhet, ehf_støtte in zip(data.get("_embedded", {}).get("underenheter", []), ehf_status_liste):
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            underenheter.append({
                "organisasjonsnummer": underenhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": underenhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
                "ehf": ehf_støtte
            })
    except requests.exceptions.RequestException as e:
        print(f"Feil ved henting av underenheter for {orgnummer}: {e}")
    return underenheter

def søk_enheter_og_underenheter(søkeord):
    """Kombinerer resultater fra hovedenheter og underenheter basert på navn."""
    hovedenheter = søk_enheter(søkeord)
    underenheter = søk_underenheter(søkeord)
    return hovedenheter, underenheter

def søk_enheter(søkeord, maks_resultater=20):
    """Søk etter firma basert på navn."""
    resultater = []
    try:
        params = {"navn": søkeord, "size": maks_resultater}
        response = requests.get(API_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        orgnummere = [enhet.get("organisasjonsnummer", "") for enhet in data.get("_embedded", {}).get("enheter", [])]
        ehf_status_liste = asyncio.run(sjekk_ehf_for_flere(orgnummere))

        for enhet, ehf_støtte in zip(data.get("_embedded", {}).get("enheter", []), ehf_status_liste):
            adresse = formater_adresse(enhet.get("forretningsadresse", {}))
            resultater.append({
                "organisasjonsnummer": enhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": enhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
                "ehf": ehf_støtte
            })

        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except requests.exceptions.RequestException as e:
        print(f"Feil ved søk etter enheter med navn {søkeord}: {e}")
    return resultater

def søk_underenheter(søkeord, maks_resultater=20):
    """Søk etter underenheter basert på navn."""
    resultater = []
    try:
        params = {"navn": søkeord, "size": maks_resultater}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()

        orgnummere = [underenhet.get("organisasjonsnummer", "") for underenhet in data.get("_embedded", {}).get("underenheter", [])]
        ehf_status_liste = asyncio.run(sjekk_ehf_for_flere(orgnummere))

        for underenhet, ehf_støtte in zip(data.get("_embedded", {}).get("underenheter", []), ehf_status_liste):
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            resultater.append({
                "organisasjonsnummer": underenhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": underenhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
                "ehf": ehf_støtte
            })

        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except requests.exceptions.RequestException as e:
        print(f"Feil ved søk etter underenheter med navn {søkeord}: {e}")
    return resultater

@app.route("/", methods=["GET", "POST"])
def søk():
    if request.method == "POST":
        søkeord = request.form.get("søkeord", "").strip()

        if søkeord:
            if søkeord.replace(" ", "").isdigit():
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
                    return render_template(
                        "index.html",
                        feilmelding="Ingen treff funnet for organisasjonsnummeret.",
                        søkeord=søkeord,
                    )
            else:
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

        return render_template("index.html")

    return render_template("index.html")


@app.route("/ehf-status/<orgnummer>")
def ehf_status(orgnummer):
    """Endepunkt for å hente EHF-status for et organisasjonsnummer."""
    ehf_støtte = asyncio.run(sjekk_ehf_peppol_async(orgnummer))
    return jsonify({"ehf": ehf_støtte})


if __name__ == "__main__":
    app.run(debug=True)

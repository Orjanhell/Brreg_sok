from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import requests
import aiohttp
import asyncio
import time
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'din_hemmelige_nøkkel'

API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"
PEPPOL_API_URL = "https://directory.peppol.eu/search/1.0/json"

EHF_CACHE = {}
CACHE_EXPIRATION = 604800  # 7 dager


# Opprett en global semafor for å begrense samtidige peppol-kall
SEM = asyncio.Semaphore(5)

def formater_adresse(adresse_data):
    adresse = ", ".join(adresse_data.get("adresse", [])) if "adresse" in adresse_data else None
    postnummer = adresse_data.get("postnummer", None)
    poststed = adresse_data.get("poststed", None)

    deler = [adresse, f"{postnummer} {poststed}".strip() if postnummer or poststed else None]
    return ", ".join(filter(None, deler)) if deler else "Ikke oppgitt"

def filtrer_relevante_resultater(søkeord, resultater):
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
    if orgnummer in EHF_CACHE:
        cached = EHF_CACHE[orgnummer]
        if time.time() - cached["timestamp"] < CACHE_EXPIRATION:
            return cached["ehf"]
    return None

async def sjekk_ehf_peppol_async(orgnummer):
    cached_status = sjekk_cache(orgnummer)
    if cached_status is not None:
        return cached_status

    params = {"participant": f"iso6523-actorid-upis::0192:{orgnummer}"}
    try:
        async with SEM:
            async with aiohttp.ClientSession() as session:
                while True:
                    async with session.get(PEPPOL_API_URL, params=params, timeout=10) as response:
                        if response.status == 429:
                            await asyncio.sleep(1)
                            continue
                        elif response.status == 200:
                            data = await response.json()
                            ehf_status = data.get("total-result-count", 0) > 0
                            EHF_CACHE[orgnummer] = {"ehf": ehf_status, "timestamp": time.time()}
                            return ehf_status
                        else:
                            return False
    except:
        return False

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
                    return render_template("index.html", hovedenheter=[enhet], underenheter=underenheter, søkeord=søkeord)
                else:
                    enhet = hent_enhet_fra_underenheter(søkeord)
                    if enhet:
                        underenheter = hent_underenheter(søkeord)
                        return render_template("index.html", hovedenheter=[enhet], underenheter=underenheter, søkeord=søkeord)
                    else:
                        return render_template("index.html", feilmelding="Ingen treff funnet for organisasjonsnummeret.", søkeord=søkeord)
            else:
                hovedenheter, underenheter = søk_enheter_og_underenheter(søkeord)
                if not hovedenheter and not underenheter:
                    return render_template("index.html", feilmelding="Ingen treff funnet for navnet.", søkeord=søkeord)
                return render_template("index.html", hovedenheter=hovedenheter, underenheter=underenheter, søkeord=søkeord)
        return render_template("index.html")
    return render_template("index.html")

@app.route("/ehf-status/bulk", methods=["POST"])
def ehf_status_bulk():
    """Henter EHF-status for flere orgnumre samtidig."""
    orgnumre = request.json.get("orgnumre", [])
    # Fjern duplikater
    orgnumre = list(set(orgnumre))

    # Sjekk alle orgnumre parallelt
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [sjekk_ehf_peppol_async(orgnr) for orgnr in orgnumre]
    results = loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()

    # Returner et kart {orgnummer: True/False} tilbake
    status_map = {orgnr: res for orgnr, res in zip(orgnumre, results)}
    return jsonify(status_map)

def hent_enhet(orgnummer):
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        data["adresse"] = adresse
        return data
    except:
        return hent_enhet_fra_underenheter(orgnummer)

def hent_enhet_fra_underenheter(orgnummer):
    try:
        params = {"organisasjonsnummer": orgnummer, "size": 1}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()
        underenheter = data.get("_embedded", {}).get("underenheter", [])
        if underenheter:
            underenhet = underenheter[0]
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            underenhet["adresse"] = adresse
            return underenhet
    except:
        pass
    return None

def hent_underenheter(orgnummer):
    underenheter = []
    try:
        params = {"overordnetEnhet": orgnummer, "size": 100}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()
        for u in data.get("_embedded", {}).get("underenheter", []):
            adresse = formater_adresse(u.get("beliggenhetsadresse", {}))
            underenheter.append({
                "organisasjonsnummer": u.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": u.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
            })
    except:
        pass
    return underenheter

def søk_enheter_og_underenheter(søkeord):
    hovedenheter = søk_enheter(søkeord)
    underenheter = søk_underenheter(søkeord)
    return hovedenheter, underenheter

def søk_enheter(søkeord, maks_resultater=20):
    resultater = []
    try:
        params = {"navn": søkeord, "size": maks_resultater}
        response = requests.get(API_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        for e in data.get("_embedded", {}).get("enheter", []):
            adresse = formater_adresse(e.get("forretningsadresse", {}))
            resultater.append({
                "organisasjonsnummer": e.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": e.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
            })

        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except:
        pass
    return resultater

def søk_underenheter(søkeord, maks_resultater=20):
    resultater = []
    try:
        params = {"navn": søkeord, "size": maks_resultater}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()
        for u in data.get("_embedded", {}).get("underenheter", []):
            adresse = formater_adresse(u.get("beliggenhetsadresse", {}))
            resultater.append({
                "organisasjonsnummer": u.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": u.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
            })
        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except:
        pass
    return resultater

if __name__ == "__main__":
    app.run(debug=True)

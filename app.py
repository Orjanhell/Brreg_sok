from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import requests
import aiohttp
import asyncio
import time
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    print("Warning: dotenv module not found. Ensure environment variables are set manually.")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'din_hemmelige_nøkkel'

API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"
PEPPOL_API_URL = "https://directory.peppol.eu/search/1.0/json"

EHF_CACHE = {}
CACHE_EXPIRATION = 604800  # 7 dager


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
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PEPPOL_API_URL, params=params, timeout=10) as response:
                    if response.status == 429:  # Ratelimiting fra API
                        await asyncio.sleep(2 ** retry_count)
                        retry_count += 1
                        continue
                    elif response.status == 200:
                        data = await response.json()
                        ehf_status = data.get("total-result-count", 0) > 0
                        EHF_CACHE[orgnummer] = {"ehf": ehf_status, "timestamp": time.time()}
                        return ehf_status
                    else:
                        return False
        except Exception as e:
            retry_count += 1

    return False


@app.route("/", methods=["GET", "POST"])
def søk():
    if request.method == "POST":
        søkeord = request.form.get("søkeord", "").strip()
        if not søkeord:
            flash("Søkeordet kan ikke være tomt.", "error")
            return redirect(url_for('søk'))

        searched_as = None  # For å indikere om søket var for hovedenhet eller underenhet

        if søkeord.replace(" ", "").isdigit():
            søkeord = søkeord.replace(" ", "")
            enhet = hent_enhet(søkeord)
            if enhet:
                searched_as = 'main'
                underenheter = hent_underenheter(søkeord)
                return render_template("index.html", hovedenheter=[enhet], underenheter=underenheter, søkeord=søkeord, searched_as=searched_as)
            else:
                underenhet, hovedenhet = hent_enhet_fra_underenheter(søkeord)
                if underenhet and hovedenhet:
                    searched_as = 'subunit'
                    underenheter = hent_underenheter(hovedenhet['organisasjonsnummer'])
                    underenheter = [u for u in underenheter if u['organisasjonsnummer'] != søkeord]
                    underenheter.insert(0, underenhet)
                    return render_template("index.html", hovedenheter=[hovedenhet], underenheter=underenheter, søkeord=søkeord, searched_as=searched_as)
                elif underenhet:
                    searched_as = 'subunit'
                    underenheter = hent_underenheter(søkeord)
                    underenheter.insert(0, underenhet)
                    return render_template("index.html", hovedenheter=[], underenheter=underenheter, søkeord=søkeord, searched_as=searched_as)
                else:
                    flash("Ingen treff funnet for organisasjonsnummeret.", "error")
                    return redirect(url_for('søk'))
        else:
            hovedenheter, underenheter = søk_enheter_og_underenheter(søkeord)
            if not hovedenheter and not underenheter:
                flash("Ingen treff funnet for navnet.", "error")
                return redirect(url_for('søk'))
            return render_template("index.html", hovedenheter=hovedenheter, underenheter=underenheter, søkeord=søkeord, searched_as=searched_as)
    return render_template("index.html")


@app.route("/ehf-status/<orgnummer>", methods=["GET"])
def ehf_status(orgnummer):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    status = loop.run_until_complete(sjekk_ehf_peppol_async(orgnummer))
    loop.close()
    return jsonify({"orgnummer": orgnummer, "ehf": status})


@app.route("/ehf-status-bulk", methods=["POST"])
async def ehf_status_bulk():
    data = request.get_json()  # Fjernet await, siden Flask bruker en synkron versjon
    orgnumre = data.get("orgnumre", [])
    if not orgnumre:
        return jsonify({"error": "Ingen organisasjonsnumre oppgitt"}), 400

    resultater = {}
    tasks = [sjekk_ehf_peppol_async(orgnr) for orgnr in orgnumre]

    try:
        statuses = await asyncio.gather(*tasks)
        resultater = {orgnumre[i]: statuses[i] for i in range(len(orgnumre))}
    except Exception as e:
        print(f"Feil under bulk-statussjekk: {e}")
        return jsonify({"error": "En feil oppstod"}), 500

    return jsonify(resultater)


    return jsonify(resultater)


def hent_enhet(orgnummer):
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        data["adresse"] = adresse
        data["ehf"] = "gul"
        return data
    except:
        return None


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
            underenhet["ehf"] = "gul"

            overordnet_orgnr = underenhet.get("overordnetEnhet")
            if overordnet_orgnr:
                hovedenhet = hent_enhet(overordnet_orgnr)
                if hovedenhet:
                    hovedenhet["ehf"] = "gul"
                    return underenhet, hovedenhet
        return None, None
    except Exception as e:
        print(f"Error in hent_enhet_fra_underenheter: {e}")
        pass
    return None, None


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
                "ehf": "gul"
            })
    except:
        pass
    return underenheter


def søk_enheter_og_underenheter(søkeord):
    hovedenheter = søk_enheter(søkeord)
    underenheter = søk_underenheter(søkeord)
    return hovedenheter, underenheter


def søk_enheter(søkeord, maks_resultater=50):
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
                "ehf": "gul"
            })

        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except:
        pass
    return resultater


def søk_underenheter(søkeord, maks_resultater=50):
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
                "ehf": "gul"
            })
        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except:
        pass
    return resultater


if __name__ == "__main__":
    app.run()

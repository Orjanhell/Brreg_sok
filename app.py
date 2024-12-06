from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import requests
import aiohttp
import asyncio
import time
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

# Last inn miljøvariabler fra .env-fil
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'din_hemmelige_nøkkel'  # Bytt ut med en sikker nøkkel

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
                    # Hvis ikke funnet i hovedenheter, prøv å søke i underenheter
                    enhet = hent_enhet_fra_underenheter(søkeord)
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


def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk enhet eller underenhet uten å hente EHF-status."""
    try:
        # Prøv å hente fra hovedenhets-API-et
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        data["adresse"] = adresse
        return data
    except requests.exceptions.RequestException as e:
        print(f"Feil ved henting av enhet {orgnummer}: {e}")
        # Prøv å hente fra underenhets-API-et
        return hent_enhet_fra_underenheter(orgnummer)


def hent_enhet_fra_underenheter(orgnummer):
    """Hent detaljer om en spesifikk underenhet basert på organisasjonsnummer."""
    try:
        # Søk etter underenheten ved å bruke orgnummer som parameter
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
    except requests.exceptions.RequestException as e:
        print(f"Feil ved henting av underenhet {orgnummer}: {e}")
    return None


def hent_underenheter(orgnummer):
    """Hent alle underenheter for en spesifikk hovedenhet eller underenhet uten å hente EHF-status."""
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
                "adresse": adresse,
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
    """Søk etter firma basert på navn uten å hente EHF-status."""
    resultater = []
    try:
        params = {"navn": søkeord, "size": maks_resultater}
        response = requests.get(API_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        for enhet in data.get("_embedded", {}).get("enheter", []):
            adresse = formater_adresse(enhet.get("forretningsadresse", {}))
            resultater.append({
                "organisasjonsnummer": enhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": enhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
            })

        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except requests.exceptions.RequestException as e:
        print(f"Feil ved søk etter enheter med navn {søkeord}: {e}")
    return resultater


def søk_underenheter(søkeord, maks_resultater=20):
    """Søk etter underenheter basert på navn uten å hente EHF-status."""
    resultater = []
    try:
        params = {"navn": søkeord, "size": maks_resultater}
        response = requests.get(API_UNDERENHETER_URL, params=params)
        response.raise_for_status()
        data = response.json()

        for underenhet in data.get("_embedded", {}).get("underenheter", []):
            adresse = formater_adresse(underenhet.get("beliggenhetsadresse", {}))
            resultater.append({
                "organisasjonsnummer": underenhet.get("organisasjonsnummer", "Ikke oppgitt"),
                "navn": underenhet.get("navn", "Ikke oppgitt"),
                "adresse": adresse,
            })

        resultater = filtrer_relevante_resultater(søkeord, resultater)
        return resultater[:maks_resultater]
    except requests.exceptions.RequestException as e:
        print(f"Feil ved søk etter underenheter med navn {søkeord}: {e}")
    return resultater


@app.route("/send-tilbakemelding", methods=["POST"])
def send_tilbakemelding():
    tilbakemelding = request.form.get("tilbakemelding", "").strip()
    if tilbakemelding:
        # Hent e-postinnstillinger fra miljøvariabler
        sender_email = os.getenv('SENDER_EMAIL')
        receiver_email = os.getenv('RECEIVER_EMAIL')
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_password = os.getenv('SMTP_PASSWORD')

        subject = "Tilbakemelding fra FirmaSøk"
        body = f"Tilbakemelding:\n\n{tilbakemelding}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = receiver_email

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, smtp_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
            flash("Tilbakemelding sendt! Takk for din innsats.", "success")
        except Exception as e:
            print(f"Feil ved sending av tilbakemelding: {e}")
            flash("Noe gikk galt. Vennligst prøv igjen senere.", "error")

    return redirect(url_for("søk"))


if __name__ == "__main__":
    app.run(debug=True)

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import requests
import aiohttp
import asyncio
import time
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
import smtplib

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'din_hemmelige_nøkkel'

API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"
PEPPOL_API_URL = "https://directory.peppol.eu/search/1.0/json"

EHF_CACHE = {}
CACHE_EXPIRATION = 86400  # 24 timer

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
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(PEPPOL_API_URL, params=params, timeout=10) as response:
                    if response.status == 429:
                        print(f"Rate limit nådd for {orgnummer}. Venter...")
                        await asyncio.sleep(1)
                        continue
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
            # Sjekk om søkeordet er et org.nr
            if søkeord.replace(" ", "").isdigit():
                søkeord = søkeord.replace(" ", "")
                # Prøv å hente hovedenhet
                enhet = hent_enhet(søkeord)
                if enhet and "overordnetEnhet" not in enhet:
                    # Fant en hovedenhet
                    underenheter = hent_underenheter(enhet.get("organisasjonsnummer"))
                    # Marker spesifikk enhet (hovedenhet) siden dette er et direkte treff
                    return render_template(
                        "index.html",
                        hovedenheter=[enhet],
                        underenheter=underenheter,
                        spesifikk_enhet=enhet,
                        søkeord=søkeord,
                    )
                else:
                    # Ingen hovedenhet funnet eller entiteten er underenhet (men vi skal ikke vise fallback)
                    return render_template(
                        "index.html",
                        feilmelding="Ingen treff funnet for organisasjonsnummeret.",
                        søkeord=søkeord,
                    )
            else:
                # Søker på navn
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
    try:
        ehf_støtte = asyncio.run(sjekk_ehf_peppol_async(orgnummer))
        return jsonify({"ehf": ehf_støtte})
    except Exception as e:
        print(f"Feil i EHF-status endepunkt for {orgnummer}: {e}")
        return jsonify({"ehf": False}), 500

def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk hovedenhet. Returner None dersom ikke funnet."""
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        data = response.json()
        adresse = formater_adresse(data.get("forretningsadresse", {}))
        data["adresse"] = adresse
        return data
    except requests.exceptions.RequestException as e:
        print(f"Feil ved henting av enhet {orgnummer}: {e}")
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
    except requests.exceptions.RequestException as e:
        print(f"Feil ved henting av underenheter for {orgnummer}: {e}")
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
    except requests.exceptions.RequestException as e:
        print(f"Feil ved søk etter enheter med navn {søkeord}: {e}")
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
    except requests.exceptions.RequestException as e:
        print(f"Feil ved søk etter underenheter med navn {søkeord}: {e}")
    return resultater

@app.route("/send-tilbakemelding", methods=["POST"])
def send_tilbakemelding():
    tilbakemelding = request.form.get("tilbakemelding", "").strip()
    if tilbakemelding:
        sender_email = os.getenv('SENDER_EMAIL') or "din_email@example.com"
        receiver_email = "orjan.helland@senabeikeland.no"
        smtp_server = os.getenv('SMTP_SERVER') or "smtp.example.com"
        smtp_port = int(os.getenv('SMTP_PORT', 465))
        smtp_password = os.getenv('SMTP_PASSWORD') or "ditt_password"

        subject = "Tilbakemelding fra FirmaSøk"
        body = f"Tilbakemelding:\n\n{tilbakemelding}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = receiver_email

        try:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(sender_email, smtp_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
            flash("Tilbakemelding sendt! Takk for din innsats.", "success")
        except smtplib.SMTPException as e_ssl:
            print(f"Feil ved SMTP_SSL sending av tilbakemelding: {e_ssl}")
            try:
                with smtplib.SMTP(smtp_server, 587) as server:
                    server.starttls()
                    server.login(sender_email, smtp_password)
                    server.sendmail(sender_email, receiver_email, msg.as_string())
                flash("Tilbakemelding sendt! Takk for din innsats.", "success")
            except smtplib.SMTPException as e_starttls:
                print(f"Feil ved SMTP STARTTLS sending av tilbakemelding: {e_starttls}")
                flash("Noe gikk galt. Vennligst prøv igjen senere.", "error")
        except Exception as e:
            print(f"Generell feil ved sending av tilbakemelding: {e}")
            flash("Noe gikk galt. Vennligst prøv igjen senere.", "error")

    return redirect(url_for("søk"))

if __name__ == "__main__":
    app.run(debug=True)

import requests
from tabulate import tabulate

# Base-URLer for API-et
API_BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
API_UNDERENHETER_URL = "https://data.brreg.no/enhetsregisteret/api/underenheter"

def formater_adresse(adresse_data):
    """Formaterer adressefeltet for visning"""
    if isinstance(adresse_data, list):  # Hvis adresse er en liste
        adresse = ", ".join(adresse_data)
    elif isinstance(adresse_data, str):  # Hvis adresse er en streng
        adresse = adresse_data
    else:
        adresse = None
    return adresse

def hent_enhet(orgnummer):
    """Hent detaljer om en spesifikk enhet"""
    try:
        response = requests.get(f"{API_BASE_URL}/{orgnummer}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            return None  # Ikke funnet, kan være en underenhet
        else:
            print(f"Feil under henting av enhet: {e}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Feil under henting av enhet: {e}")
        return None


def hent_underenheter(orgnummer):
    """Hent alle underenheter for en spesifikk enhet, inkludert paginering."""
    try:
        underenheter = []
        sett_med_orgnr = set()  # For å unngå duplikater
        page = 0
        while True:
            params = {"overordnetEnhet": orgnummer, "size": 100, "page": page}
            response = requests.get(API_UNDERENHETER_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Hent relevante underenheter
            nye_underenheter = data.get("_embedded", {}).get("underenheter", [])
            for underenhet in nye_underenheter:
                orgnr = underenhet["organisasjonsnummer"]
                if orgnr not in sett_med_orgnr:  # Legg til bare hvis ikke allerede i settet
                    sett_med_orgnr.add(orgnr)
                    underenheter.append({
                        "organisasjonsnummer": orgnr,
                        "navn": underenhet["navn"],
                        "adresse": underenhet.get("beliggenhetsadresse", {})
                    })

            # Sjekk om det er flere sider
            if page >= data.get("page", {}).get("totalPages", 1) - 1:
                break

            page += 1

        return underenheter

    except requests.exceptions.RequestException as e:
        print(f"Feil under henting av underenheter: {e}")
        return []

def hent_hovedenhet_fra_underenhet(orgnummer):
    """Hent hovedenhet fra en underenhet basert på overordnetEnhet."""
    try:
        response = requests.get(f"{API_UNDERENHETER_URL}/{orgnummer}")
        response.raise_for_status()
        underenhet = response.json()

        # Sjekk om det finnes en overordnet enhet
        hovedenhet_orgnr = underenhet.get("overordnetEnhet")
        if hovedenhet_orgnr:
            hovedenhet = hent_enhet(hovedenhet_orgnr)
            return underenhet, hovedenhet
        else:
            return underenhet, None

    except requests.exceptions.RequestException as e:
        print(f"Feil under henting av underenhet: {e}")
        return None, None

def vis_hovedenhet_og_underenheter(hovedenhet, underenheter):
    """Viser hovedenheten og underenhetene i en trestruktur, samt antall enheter."""
    tabell_data = []

    # Legg til hovedenheten først
    adresse = hovedenhet.get("forretningsadresse", {})
    adresse_tekst = ", ".join(
        filter(None, [
            formater_adresse(adresse.get("adresse")),
            adresse.get("postnummer"),
            adresse.get("poststed")
        ])
    )
    tabell_data.append([
        hovedenhet["organisasjonsnummer"],
        f"[HOVEDENHET] {hovedenhet['navn']}",
        adresse_tekst if adresse_tekst else "Ikke oppgitt"
    ])

    # Legg til underenhetene
    for underenhet in underenheter:
        adresse = underenhet.get("adresse", {})
        adresse_tekst = ", ".join(
            filter(None, [
                formater_adresse(adresse.get("adresse")),
                adresse.get("postnummer"),
                adresse.get("poststed")
            ])
        )

        # Unngå å legge til helt tomme rader
        if underenhet["navn"] and adresse_tekst:
            tabell_data.append([
                underenhet["organisasjonsnummer"],
                f"  └── {underenhet['navn']}",
                adresse_tekst if adresse_tekst else "Ikke oppgitt"
            ])

    # Skriv ut tabellen
    print("\nHovedenhet og underenheter:")
    print(tabulate(tabell_data, headers=["Organisasjonsnummer", "Navn", "Adresse"], tablefmt="grid"))

    # Vis totalt antall enheter
    totalt_antall = len(tabell_data)  # Antall unike rader i tabellen
    print(f"\nTotalt antall enheter funnet: {totalt_antall}")

def vis_underenhet_og_hovedenhet(underenhet, hovedenhet):
    """Viser underenhet og dens hovedenhet i en tabell."""
    tabell_data = []

    # Legg til underenheten
    adresse = underenhet.get("beliggenhetsadresse", {})
    adresse_tekst = ", ".join(
        filter(None, [
            formater_adresse(adresse.get("adresse")),
            adresse.get("postnummer"),
            adresse.get("poststed")
        ])
    )
    tabell_data.append([
        underenhet["organisasjonsnummer"],
        f"[UNDERENHET] {underenhet['navn']}",
        adresse_tekst if adresse_tekst else "Ikke oppgitt"
    ])

    # Legg til hovedenheten, hvis den finnes
    if hovedenhet:
        adresse = hovedenhet.get("forretningsadresse", {})
        adresse_tekst = ", ".join(
            filter(None, [
                formater_adresse(adresse.get("adresse")),
                adresse.get("postnummer"),
                adresse.get("poststed")
            ])
        )
        tabell_data.append([
            hovedenhet["organisasjonsnummer"],
            f"[HOVEDENHET] {hovedenhet['navn']}",
            adresse_tekst if adresse_tekst else "Ikke oppgitt"
        ])

    # Skriv ut tabellen
    print("\nUnderenhet og hovedenhet:")
    print(tabulate(tabell_data, headers=["Organisasjonsnummer", "Navn", "Adresse"], tablefmt="grid"))

def vis_resultater_tabell(resultater):
    """Viser en liste over firmaresultater som en tabell"""
    if not resultater:
        print("\nIngen treff funnet. Prøv igjen.")
        return

    # Lag en liste over rader for tabellen
    tabell_data = []
    for firma in resultater:
        adresse = firma.get("adresse", {})
        adresse_tekst = ", ".join(
            filter(None, [
                formater_adresse(adresse.get("adresse")),
                adresse.get("postnummer"),
                adresse.get("poststed")
            ])
        )
        tabell_data.append([
            firma["organisasjonsnummer"],
            firma["navn"],
            adresse_tekst if adresse_tekst else "Ikke oppgitt"
        ])

    # Skriv ut tabellen
    print("\nSøkeresultater:")
    print(tabulate(tabell_data, headers=["Organisasjonsnummer", "Navn", "Adresse"], tablefmt="grid"))

def main():
    """Hovedprogram for å søke"""
    print("Velkommen til FirmaSøk!")
    while True:
        søkeord = input("Angi firmanavn eller organisasjonsnummer (eller 'exit' for å avslutte): ")

        if søkeord.lower() == "exit":
            print("Avslutter FirmaSøk. Ha en fin dag!")
            break

        if søkeord.isdigit():  # Hvis søket er et organisasjonsnummer
            enhet = hent_enhet(søkeord)
            if enhet:
                underenheter = hent_underenheter(søkeord)
                vis_hovedenhet_og_underenheter(enhet, underenheter)
            else:
                underenhet, hovedenhet = hent_hovedenhet_fra_underenhet(søkeord)
                if underenhet:
                    # Vis underenhet og hovedenhet i tabellform
                    vis_underenhet_og_hovedenhet(underenhet, hovedenhet)
                else:
                    print("\nIngen treff funnet. Prøv igjen.")
        else:  # Søk på firmanavn
            resultater = søk_enheter(søkeord)
            vis_resultater_tabell(resultater)

        print("\nGjør et nytt søk eller skriv 'exit' for å avslutte.")

if __name__ == "__main__":
    main()

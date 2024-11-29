async function oppdaterEHFStatus(orgnummer, statusElement) {
    const cacheKey = `ehfStatus_${orgnummer}`;
    const cachedStatus = sessionStorage.getItem(cacheKey);

    if (cachedStatus !== null) {
        settStatus(statusElement, cachedStatus);
        return;
    }

    try {
        const response = await fetch(`/ehf-status/${orgnummer}`);
        const data = await response.json();

        const status = data.ehf ? 'grønn' : 'rød';
        sessionStorage.setItem(cacheKey, status);
        settStatus(statusElement, status);
    } catch (error) {
        console.error(`Feil ved oppdatering av EHF-status for ${orgnummer}:`, error);
        // Behold "gul" eller håndter feilen på en passende måte
    }
}

function settStatus(element, status) {
    element.classList.remove('grønn', 'gul', 'rød');
    element.classList.add(status);
    if (status !== 'gul') {
        element.classList.remove('spinner');
    }
}

function begrensAntallForespørsler(tasks, maxSimultaneous) {
    let index = 0;
    let aktive = 0;

    return new Promise((resolve) => {
        const resultater = [];

        function neste() {
            if (index >= tasks.length && aktive === 0) {
                resolve(resultater);
                return;
            }

            while (aktive < maxSimultaneous && index < tasks.length) {
                aktive++;
                tasks[index]()
                    .then((resultat) => {
                        resultater.push(resultat);
                    })
                    .catch((error) => {
                        console.error(error);
                    })
                    .finally(() => {
                        aktive--;
                        neste();
                    });
                index++;
            }
        }

        neste();
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const ehfStatusElementer = document.querySelectorAll('.ehf-status');
    const tasks = Array.from(ehfStatusElementer).map((element) => {
        const orgnummer = element.dataset.orgnummer;
        // Legg til spinner-klasse
        element.classList.add('spinner');
        return () => oppdaterEHFStatus(orgnummer, element);
    });

    begrensAntallForespørsler(tasks, 5); // Maks 5 samtidige forespørsler
});

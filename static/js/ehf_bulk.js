document.addEventListener('DOMContentLoaded', () => {
    const ehfStatusElementer = document.querySelectorAll('.ehf-status');
    if (ehfStatusElementer.length === 0) return;

    const orgnumre = Array.from(ehfStatusElementer).map(el => el.dataset.orgnummer);
    const cache = {};

    // Sjekk sessionStorage for cache
    orgnumre.forEach(orgnr => {
        const cachedStatus = sessionStorage.getItem(`ehfStatus_${orgnr}`);
        if (cachedStatus) {
            cache[orgnr] = cachedStatus;
        }
    });

    // Filtrer ut orgnumre som ikke er i cache
    const orgnumreToFetch = orgnumre.filter(o => !cache[o]);

    if (orgnumreToFetch.length === 0) {
        // Alt er cachet
        ehfStatusElementer.forEach(el => {
            const orgnr = el.dataset.orgnummer;
            settStatus(el, cache[orgnr]);
        });
        return;
    }

    // Send én samlet forespørsel
    fetch('/ehf-status/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orgnumre: orgnumreToFetch })
    })
    .then(res => res.json())
    .then(data => {
        // data = { orgnr: true/false }
        ehfStatusElementer.forEach(el => {
            const orgnr = el.dataset.orgnummer;
            let status;
            if (cache[orgnr]) {
                // Allerede cachet
                status = cache[orgnr];
            } else {
                const ehfRes = data[orgnr];
                status = ehfRes ? 'grønn' : 'rød';
                sessionStorage.setItem(`ehfStatus_${orgnr}`, status);
            }
            settStatus(el, status);
        });
    })
    .catch(error => {
        console.error("Feil ved innhenting av EHF-status:", error);
        ehfStatusElementer.forEach(el => settStatus(el, 'rød'));
    });
});

function settStatus(element, status) {
    element.classList.remove('grønn', 'gul', 'rød', 'spinner');
    element.classList.add(status);
}

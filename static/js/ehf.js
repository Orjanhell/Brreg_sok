/* ---------- EHF-status oppdatering ---------- */
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
        settStatus(statusElement, 'rød'); // Sett til 'rød' ved feil
    }
}

function settStatus(element, status) {
    element.classList.remove('grønn', 'gul', 'rød', 'spinner');
    element.classList.add(status);
    if (status !== 'gul') {
        element.classList.remove('spinner');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const ehfStatusElementer = document.querySelectorAll('.ehf-status');
    ehfStatusElementer.forEach((element) => {
        const orgnummer = element.dataset.orgnummer;
        // Legg til spinner-klasse
        element.classList.add('spinner');
        oppdaterEHFStatus(orgnummer, element);
    });
});

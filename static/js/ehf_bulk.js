document.addEventListener("DOMContentLoaded", () => {
    const ehfStatusElementer = document.querySelectorAll(".ehf-status");

    if (ehfStatusElementer.length === 0) return;

    const orgnumre = Array.from(ehfStatusElementer).map(el => el.dataset.orgnummer);

    oppdaterAlleStatus(orgnumre, ehfStatusElementer);
});

function oppdaterAlleStatus(orgnumre, elementer) {
    const url = `/ehf-status-bulk`;

    // Vis spinner på alle elementer før data lastes inn
    elementer.forEach(el => oppdaterStatus(el, "spinner"));

    // Send batch-forespørsel
    fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orgnumre }),
    })
        .then(res => res.json())
        .then(data => {
            Object.entries(data).forEach(([orgnummer, status]) => {
                const element = document.querySelector(`.ehf-status[data-orgnummer="${orgnummer}"]`);
                if (element) oppdaterStatus(element, status ? "grønn" : "rød");
            });
        })
        .catch(error => {
            console.error("Feil ved oppdatering av EHF-status:", error);
            // Oppdater alle elementer til feilstatus hvis forespørselen mislykkes
            elementer.forEach(el => oppdaterStatus(el, "rød"));
        });
}

function oppdaterStatus(element, status) {
    element.classList.remove("grønn", "gul", "rød", "spinner");
    if (status === "grønn") {
        element.classList.add("grønn");
        element.innerHTML = "✅";
    } else if (status === "rød") {
        element.classList.add("rød");
        element.innerHTML = "❌";
    } else if (status === "spinner") {
        element.classList.add("spinner");
        element.innerHTML = "⏳";
    }
}

function sortTable(tableId, columnIndex) {
    const table = document.getElementById(tableId);
    const rows = Array.from(table.rows).slice(1); // Exclude header row
    let ascending = true;

    // Check if the table was previously sorted by this column
    if (table.getAttribute("data-sort-column") == columnIndex) {
        ascending = table.getAttribute("data-sort-order") !== "asc";
    }

    // Sort rows based on the content of the specified column
    rows.sort((rowA, rowB) => {
        const cellA = rowA.cells[columnIndex].textContent.trim();
        const cellB = rowB.cells[columnIndex].textContent.trim();

        // Numeric sorting for numbers, alphabetical for text
        if (!isNaN(cellA) && !isNaN(cellB)) {
            return ascending ? cellA - cellB : cellB - cellA;
        }

        return ascending
            ? cellA.localeCompare(cellB)
            : cellB.localeCompare(cellA);
    });

    // Append sorted rows back to the table
    rows.forEach(row => table.tBodies[0].appendChild(row));

    // Update sorting state on the table
    table.setAttribute("data-sort-column", columnIndex);
    table.setAttribute("data-sort-order", ascending ? "asc" : "desc");
}
function søkMedOrgNummer(orgNummer) {
    const søkefelt = document.querySelector('input[name="søkeord"]');
    søkefelt.value = orgNummer; // Kopierer orgnummer til søkefeltet

    // Simulerer et søk ved å sende skjemaet automatisk
    søkefelt.closest('form').submit();
}

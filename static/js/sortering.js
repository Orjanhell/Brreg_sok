function sortTable(tableId, columnIndex) {
    const table = document.getElementById(tableId);
    const rows = Array.from(table.tBodies[0].rows);
    let ascending = true;

    if (table.getAttribute("data-sort-column") == columnIndex) {
        ascending = table.getAttribute("data-sort-order") !== "asc";
    }

    rows.sort((rowA, rowB) => {
        const cellA = rowA.cells[columnIndex].textContent.trim();
        const cellB = rowB.cells[columnIndex].textContent.trim();

        if (!isNaN(cellA) && !isNaN(cellB)) {
            return ascending ? cellA - cellB : cellB - cellA;
        }

        return ascending
            ? cellA.localeCompare(cellB)
            : cellB.localeCompare(cellA);
    });

    rows.forEach((row) => table.tBodies[0].appendChild(row));

    // Oppdater sorteringsindikatorer
    const headers = table.querySelectorAll('th');
    headers.forEach((header, idx) => {
        header.classList.remove('sorted-asc', 'sorted-desc');
        if (idx === columnIndex) {
            header.classList.add(ascending ? 'sorted-asc' : 'sorted-desc');
        }
    });

    table.setAttribute("data-sort-column", columnIndex);
    table.setAttribute("data-sort-order", ascending ? "asc" : "desc");
}

document.addEventListener('DOMContentLoaded', () => {
    const tables = document.querySelectorAll('table');
    tables.forEach((table) => {
        const headers = table.querySelectorAll('th');
        headers.forEach((header, index) => {
            header.addEventListener('click', () => {
                sortTable(table.id, index);
            });
        });
    });
});

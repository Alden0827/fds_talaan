document.addEventListener('DOMContentLoaded', () => {
    /**
     * Configuration for each table that needs score calculation.
     * id: The ID of the table element.
     * dataStartCol: The 1-based index of the first column containing score inputs.
     */
    const tableConfigs = [
        { id: 'katatasan-table', dataStartCol: 4 },
        { id: 'edukasyon-table', dataStartCol: 3 },
        { id: 'kalusugan-table', dataStartCol: 3 },
        { id: 'nutrisyon-table', dataStartCol: 3 },
        { id: 'pamilya-table', dataStartCol: 3 },
        { id: 'kabuhayan-table', dataStartCol: 3 }
    ];

    tableConfigs.forEach(config => {
        const table = document.getElementById(config.id);
        if (!table) {
            console.warn(`Table with id "${config.id}" not found.`);
            return;
        }

        const tbody = table.querySelector('tbody');
        const tfoot = table.querySelector('tfoot');

        if (!tbody || !tfoot) {
            console.warn(`Table "${config.id}" is missing a tbody or tfoot.`);
            return;
        }

        const totalInputs = tfoot.querySelectorAll('input[disabled]');

        /**
         * Updates the total scores for the table.
         * It iterates through each of the 6 score columns, sums up the values,
         * and displays the total in the corresponding footer input.
         */
        const updateTotals = () => {
            // There are 6 score columns (Baseline, Unang Pagsusuri, etc.)
            for (let i = 0; i < 6; i++) {
                let total = 0;
                const currentColumnIndex = config.dataStartCol + i;

                // Select all inputs in the current column of the tbody
                const inputs = tbody.querySelectorAll(`tr > td:nth-child(${currentColumnIndex}) input[type="text"]`);

                inputs.forEach(input => {
                    // Treat N/A or empty as 0 for calculation
                    const value = parseFloat(input.value);
                    if (!isNaN(value)) {
                        total += value;
                    }
                });

                // Update the corresponding total input in the footer
                if (totalInputs[i]) {
                    totalInputs[i].value = total;
                }
            }
        };

        // Add a single event listener to the table body for efficiency
        tbody.addEventListener('input', (event) => {
            // Recalculate totals only if an input field was changed
            if (event.target.tagName === 'INPUT' && event.target.type === 'text') {
                updateTotals();
            }
        });

        // Perform an initial calculation when the page loads
        updateTotals();
    });
});

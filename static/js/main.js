// main.js — students will add JavaScript here as features are built

document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide) {
        lucide.createIcons();
    }
    initDateFilterPresets();
    initExpenseAddedAlert();
    initExpenseDeletedAlert();
    initDeleteConfirm();
});

function initExpenseAddedAlert() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("added") !== "1") return;

    alert("Expense added successfully!");

    params.delete("added");
    const query = params.toString();
    const newUrl = window.location.pathname + (query ? `?${query}` : "");
    window.history.replaceState({}, "", newUrl);
}

function initExpenseDeletedAlert() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("deleted") !== "1") return;

    alert("Expense deleted successfully!");

    params.delete("deleted");
    const query = params.toString();
    const newUrl = window.location.pathname + (query ? `?${query}` : "");
    window.history.replaceState({}, "", newUrl);
}

function initDeleteConfirm() {
    document.querySelectorAll("[data-confirm-delete]").forEach((link) => {
        link.addEventListener("click", (event) => {
            if (!confirm("Delete this expense?")) {
                event.preventDefault();
            }
        });
    });
}

function initDateFilterPresets() {
    const form = document.getElementById("date-filter-form");
    if (!form) return;

    const startInput = document.getElementById("start_date");
    const endInput = document.getElementById("end_date");
    const pills = form.querySelectorAll(".filter-pill");

    function toISO(d) {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    function presetRange(preset) {
        const today = new Date();
        if (preset === "month") {
            return { start: toISO(new Date(today.getFullYear(), today.getMonth(), 1)), end: toISO(today) };
        }
        if (preset === "3months") {
            return { start: toISO(new Date(today.getFullYear(), today.getMonth() - 3, today.getDate())), end: toISO(today) };
        }
        if (preset === "6months") {
            return { start: toISO(new Date(today.getFullYear(), today.getMonth() - 6, today.getDate())), end: toISO(today) };
        }
        return { start: "", end: "" };
    }

    function highlightActivePill() {
        const current = { start: startInput.value, end: endInput.value };
        let matched = "all";
        pills.forEach((pill) => {
            const range = presetRange(pill.dataset.preset);
            if (range.start === current.start && range.end === current.end) {
                matched = pill.dataset.preset;
            }
        });
        pills.forEach((pill) => {
            pill.classList.toggle("filter-pill-active", pill.dataset.preset === matched);
        });
    }

    pills.forEach((pill) => {
        pill.addEventListener("click", () => {
            const range = presetRange(pill.dataset.preset);
            startInput.value = range.start;
            endInput.value = range.end;
            form.submit();
        });
    });

    highlightActivePill();
}

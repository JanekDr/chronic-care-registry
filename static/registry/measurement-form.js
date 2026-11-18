"use strict";

(() => {
  const kind = document.getElementById("id_kind");
  const unit = document.getElementById("measurement-unit");
  const units = JSON.parse(document.getElementById("measurement-units").textContent);
  const updateUnit = () => { unit.textContent = units[kind.value] || "Wybierz rodzaj"; };
  kind.addEventListener("change", updateUnit);
  updateUnit();
})();

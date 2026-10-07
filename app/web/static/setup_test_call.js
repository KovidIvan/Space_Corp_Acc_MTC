"use strict";

const testCallButton = document.getElementById("test-call");
if (testCallButton) {
	const status = document.getElementById("test-call-status");
	testCallButton.addEventListener("click", () => {
		status.textContent = "Открываем локальный симулятор тестового звонка…";
		window.location.assign("/call");
	});
}

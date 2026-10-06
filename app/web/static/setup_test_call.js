"use strict";

const testCallButton = document.getElementById("test-call");
if (testCallButton) {
	const status = document.getElementById("test-call-status");
	testCallButton.addEventListener("click", () => {
		status.textContent = "Проверяем согласие и доступность голосового сценария…";
		testCallButton.disabled = true;
		const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
		const socket = new WebSocket(`${protocol}//${window.location.host}/ws/call`);
		socket.addEventListener("open", () => {
			status.textContent = "Согласие подтверждено, но голосовой сценарий пока не подключён.";
			socket.close();
			testCallButton.disabled = false;
		});
		socket.addEventListener("close", (event) => {
			if (event.code === 1008) status.textContent = "Звонок отклонён: сначала требуется согласие.";
			if (event.code === 1013) status.textContent = "Согласие подтверждено, но голосовой сценарий пока не подключён.";
			testCallButton.disabled = false;
		});
		socket.addEventListener("error", () => {
			status.textContent = "Не удалось подключиться к голосовому сценарию.";
			testCallButton.disabled = false;
		});
	});
}

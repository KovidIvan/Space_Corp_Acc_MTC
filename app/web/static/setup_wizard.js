"use strict";

const form = document.getElementById("setup-wizard");
if (form) {
	const steps = Array.from(form.querySelectorAll(".wizard-step"));
	const backButton = document.getElementById("wizard-back");
	const nextButton = document.getElementById("wizard-next");
	const finishButton = document.getElementById("wizard-finish");
	const stepLabel = document.getElementById("wizard-step-label");
	const progress = document.getElementById("wizard-progress");
	const timer = document.getElementById("wizard-timer");
	const message = document.getElementById("wizard-message");
	const telegramLinkButton = document.getElementById("telegram-link-button");
	const telegramLinkUrl = document.getElementById("telegram-link-url");
	const telegramLinkStatus = document.getElementById("telegram-link-status");
	const initialSeconds = Number(form.dataset.elapsed || 0);
	const timerStartedAt = Date.now();
	let currentStep = 0;
	let telegramLinkPoll;

	const elapsedSeconds = () => initialSeconds + Math.floor((Date.now() - timerStartedAt) / 1000);
	const renderTimer = () => {
		const seconds = elapsedSeconds();
		timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
	};

	function showStep(index) {
		currentStep = index;
		steps.forEach((step, stepIndex) => { step.hidden = stepIndex !== index; });
		stepLabel.textContent = `Шаг ${index + 1} из ${steps.length}`;
		progress.value = index + 1;
		backButton.hidden = index === 0;
		nextButton.hidden = index === steps.length - 1;
		finishButton.hidden = index !== steps.length - 1;
		message.hidden = true;
		if (telegramLinkPoll) window.clearInterval(telegramLinkPoll);
		if (index === 3 && telegramLinkStatus && !telegramLinkButton.hidden) {
			telegramLinkPoll = window.setInterval(refreshTelegramLinkStatus, 3000);
		}
	}

	async function refreshTelegramLinkStatus() {
		try {
			const response = await fetch("/api/wizard/telegram-link", { cache: "no-store" });
			if (!response.ok) return;
			const result = await response.json();
			telegramLinkStatus.textContent = result.linked ? "Telegram подключён." : "Telegram пока не подключён.";
			if (result.linked) {
				telegramLinkButton.hidden = true;
				telegramLinkUrl.hidden = true;
				window.clearInterval(telegramLinkPoll);
			}
		} catch {
			telegramLinkStatus.textContent = "Не удалось проверить состояние Telegram.";
		}
	}

	function validateCurrentStep() {
		const fields = Array.from(steps[currentStep].querySelectorAll("input, select, textarea"));
		for (const field of fields) {
			if (field.type === "checkbox" && field.name === "working_days") continue;
			if (!field.checkValidity()) {
				field.reportValidity();
				return false;
			}
		}
		if (currentStep === 2 && !form.querySelectorAll('[name="working_days"]:checked').length) {
			message.textContent = "Выберите хотя бы один рабочий день.";
			message.hidden = false;
			return false;
		}
		return true;
	}

	function readConfig() {
		const value = (name) => form.elements.namedItem(name).value.trim();
		const vipNumbers = value("vip_numbers").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
		const savedVipHashes = value("saved_vip_hashes").split(",").filter(Boolean);
		const days = Array.from(form.querySelectorAll('[name="working_days"]:checked')).map((item) => Number(item.value));
		const owner = { name: value("owner_name"), company: value("owner_company") };
		if (value("owner_role")) owner.role = value("owner_role");
		const routing = [];
		if (vipNumbers.length) {
			routing.push({ id: "vip-handoff", priority: 10, action: "handoff", when: { is_vip: true } });
		}
		routing.push({ id: "default-message", priority: 100, action: "take_message" });
		return {
			version: 1,
			owner,
			template: value("template"),
			greeting: value("greeting"),
			disclosure: value("disclosure"),
			closing: value("closing"),
			routing,
			handoff_number: value("handoff_number"),
			vip_numbers: [...savedVipHashes, ...vipNumbers],
			working_hours: {
				tz: value("timezone"),
				days,
				start: value("work_start"),
				end: value("work_end"),
			},
			retention_days: 30,
			store_audio: false,
			notice_detail: "minimal",
		};
	}

	nextButton.addEventListener("click", () => {
		if (validateCurrentStep()) showStep(Math.min(currentStep + 1, steps.length - 1));
	});
	backButton.addEventListener("click", () => showStep(Math.max(currentStep - 1, 0)));
	if (telegramLinkButton) {
		telegramLinkButton.addEventListener("click", async () => {
			telegramLinkButton.disabled = true;
			telegramLinkStatus.textContent = "Создаём защищённую ссылку…";
			try {
				const response = await fetch("/api/wizard/telegram-link", { method: "POST", cache: "no-store" });
				const result = await response.json();
				if (!response.ok) throw new Error();
				telegramLinkUrl.href = result.url;
				telegramLinkUrl.hidden = false;
				telegramLinkStatus.textContent = "Ссылка создана и действует 10 минут.";
			} catch {
				telegramLinkStatus.textContent = "Не удалось создать ссылку. Проверьте настройки Telegram и повторите попытку.";
			} finally {
				telegramLinkButton.disabled = false;
			}
		});
	}
	form.addEventListener("submit", async (event) => {
		event.preventDefault();
		if (!validateCurrentStep()) return;
		finishButton.disabled = true;
		message.hidden = true;
		try {
			const response = await fetch("/api/wizard/complete", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ agent_config: readConfig(), consent_accepted: document.getElementById("consent-accepted").checked }),
			});
			const result = await response.json();
			if (!response.ok) {
				message.textContent = typeof result.detail === "string" ? result.detail : "Проверьте поля настройки и принятие согласия.";
				message.hidden = false;
				finishButton.disabled = false;
				return;
			}
			window.location.assign(result.redirect_url);
		} catch {
			message.textContent = "Не удалось сохранить настройки. Проверьте соединение с локальным приложением.";
			message.hidden = false;
			finishButton.disabled = false;
		}
	});

	showStep(0);
	renderTimer();
	window.setInterval(renderTimer, 1000);
}

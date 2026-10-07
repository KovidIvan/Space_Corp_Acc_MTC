"use strict";

const form = document.getElementById("settings-editor");
if (form) {
	const configElement = document.getElementById("editor-config");
	const config = JSON.parse(configElement.textContent);
	const faqList = document.getElementById("faq-list");
	const routingList = document.getElementById("routing-list");
	const vipList = document.getElementById("vip-list");
	const message = document.getElementById("editor-message");
	const saveButton = document.getElementById("save-settings");
	const intentOptions = [
		["client", "клиент"], ["partner", "партнёр"], ["vendor_sales", "продажи"],
		["spam", "спам"], ["job_candidate", "кандидат"], ["other", "другое"], ["unclear", "не определено"],
	];
	const urgencyOptions = [["low", "низкая"], ["normal", "обычная"], ["high", "высокая"]];
	const actionOptions = [
		["answer_faq", "ответить по FAQ"], ["take_message", "принять сообщение"],
		["offer_chat", "предложить чат"], ["handoff", "передать менеджеру"], ["decline", "вежливо отказать"],
	];
	const booleanOptions = [["", "Не учитывать"], ["true", "Да"], ["false", "Нет"]];

	function addFaqItem(item = {}) {
		const card = document.createElement("article");
		card.className = "editor-card faq-item";
		const heading = document.createElement("div");
		heading.className = "editor-card-heading";
		const title = document.createElement("h3");
		title.textContent = "Вопрос и ответ";
		const removeButton = document.createElement("button");
		removeButton.className = "button button-quiet editor-remove";
		removeButton.type = "button";
		removeButton.textContent = "Удалить";
		removeButton.addEventListener("click", () => card.remove());
		heading.append(title, removeButton);

		const fields = document.createElement("div");
		fields.className = "form-stack";
		const definitions = [
			["id", "Идентификатор", "text"],
			["question", "Вопрос", "text"],
			["answer", "Ответ ассистента", "textarea"],
		];
		for (const [name, labelText, type] of definitions) {
			const fieldLabel = document.createElement("label");
			const fieldId = `faq-${name}-${crypto.randomUUID()}`;
			fieldLabel.htmlFor = fieldId;
			fieldLabel.textContent = labelText;
			const field = document.createElement(type === "textarea" ? "textarea" : "input");
			field.id = fieldId;
			field.name = name;
			field.required = true;
			field.maxLength = name === "id" ? 100 : 2000;
			if (type === "textarea") field.rows = 3;
			else field.type = type;
			field.value = item[name] || "";
			fields.append(fieldLabel, field);
		}
		card.append(heading, fields);
		faqList.append(card);
	}

	function createField(parent, name, labelText, type, value = "", attributes = {}) {
		const label = document.createElement("label");
		const id = `editor-${name}-${crypto.randomUUID()}`;
		label.htmlFor = id;
		label.textContent = labelText;
		const field = document.createElement(type === "select" ? "select" : "input");
		field.id = id;
		field.name = name;
		if (type !== "select") field.type = type;
		for (const [attribute, attributeValue] of Object.entries(attributes)) {
			if (attribute !== "options") field[attribute] = attributeValue;
		}
		if (type === "select") {
			for (const [optionValue, optionLabel] of attributes.options) {
				const option = document.createElement("option");
				option.value = optionValue;
				option.textContent = optionLabel;
				field.append(option);
			}
		}
		field.value = value ?? "";
		if (parent.classList.contains("inline-fields")) {
			const wrapper = document.createElement("div");
			wrapper.className = "field";
			wrapper.append(label, field);
			parent.append(wrapper);
		} else {
			parent.append(label, field);
		}
		return field;
	}

	function addRoutingRule(rule = {}) {
		const card = document.createElement("article");
		card.className = "editor-card routing-item";
		const heading = document.createElement("div");
		heading.className = "editor-card-heading";
		const title = document.createElement("h3");
		title.textContent = "Правило маршрутизации";
		const removeButton = document.createElement("button");
		removeButton.className = "button button-quiet editor-remove";
		removeButton.type = "button";
		removeButton.textContent = "Удалить";
		removeButton.addEventListener("click", () => card.remove());
		heading.append(title, removeButton);

		const fields = document.createElement("div");
		fields.className = "form-stack";
		const ruleFields = document.createElement("div");
		ruleFields.className = "inline-fields";
		createField(ruleFields, "rule-id", "Идентификатор", "text", rule.id || "", { required: true, maxLength: 100 });
		createField(ruleFields, "priority", "Приоритет (меньше — раньше)", "number", rule.priority ?? 100, { required: true, min: 0, step: 1 });
		createField(ruleFields, "action", "Действие", "select", rule.action || "take_message", { required: true, options: actionOptions });
		fields.append(heading, ruleFields);
		const conditionsLabel = document.createElement("p");
		conditionsLabel.className = "muted";
		conditionsLabel.textContent = "Условия можно не заполнять. Типы: " + intentOptions.map(([value, label]) => `${label} (${value})`).join(", ") + "; срочность: низкая (low), обычная (normal), высокая (high).";
		fields.append(conditionsLabel);
		const conditions = document.createElement("div");
		conditions.className = "inline-fields";
		const when = rule.when || {};
		createField(conditions, "intent", "Типы обращений через запятую", "text", (when.intent || []).join(", "), { maxLength: 200 });
		createField(conditions, "urgency", "Уровни срочности через запятую", "text", (when.urgency || []).join(", "), { maxLength: 100 });
		for (const [name, label] of [["is_vip", "VIP"], ["outside_hours", "Вне рабочих часов"], ["wants_human", "Просьба о менеджере"], ["wants_chat", "Просьба о чате"]]) {
			const value = Object.hasOwn(when, name) ? String(when[name]) : "";
			createField(conditions, name, label, "select", value, { options: booleanOptions });
		}
		fields.append(conditions);
		card.append(fields);
		routingList.append(card);
	}

	function addVipHash(hash, index) {
		const row = document.createElement("div");
		row.className = "vip-item";
		row.dataset.vipHash = hash;
		const label = document.createElement("span");
		label.textContent = `Сохранённый VIP-контакт ${index + 1}`;
		const removeButton = document.createElement("button");
		removeButton.className = "button button-quiet editor-remove";
		removeButton.type = "button";
		removeButton.textContent = "Удалить";
		removeButton.addEventListener("click", () => row.remove());
		row.append(label, removeButton);
		vipList.append(row);
	}

	form.elements.namedItem("greeting").value = config.greeting || "";
	form.elements.namedItem("disclosure").value = config.disclosure || "";
	form.elements.namedItem("closing").value = config.closing || "";
	for (const item of config.faq || []) addFaqItem(item);
	for (const rule of config.routing || []) addRoutingRule(rule);
	for (const [index, hash] of (config.vip_numbers || []).entries()) addVipHash(hash, index);
	form.elements.namedItem("handoff_number").value = config.handoff_number || "";
	const hours = config.working_hours || {};
	form.elements.namedItem("timezone").value = hours.tz || "Europe/Minsk";
	form.elements.namedItem("work_start").value = hours.start || "09:00";
	form.elements.namedItem("work_end").value = hours.end || "18:00";
	for (const day of hours.days || [1, 2, 3, 4, 5]) {
		const checkbox = form.querySelector(`[name="working_days"][value="${day}"]`);
		if (checkbox) checkbox.checked = true;
	}

	document.getElementById("add-faq").addEventListener("click", () => addFaqItem());
	document.getElementById("add-routing-rule").addEventListener("click", () => addRoutingRule());
	form.addEventListener("submit", async (event) => {
		event.preventDefault();
		if (!form.reportValidity()) return;
		if (!routingList.querySelectorAll(".routing-item").length) {
			message.textContent = "Добавьте хотя бы одно правило маршрутизации.";
			message.classList.add("notice-error");
			message.hidden = false;
			return;
		}
		saveButton.disabled = true;
		message.hidden = true;
		const routing = Array.from(routingList.querySelectorAll(".routing-item"), (card) => {
			const read = (name) => card.querySelector(`[name="${name}"]`).value.trim();
			const when = {};
			for (const name of ["intent", "urgency"]) {
				const values = read(name).split(",").map((value) => value.trim()).filter(Boolean);
				if (values.length) when[name] = values;
			}
			for (const name of ["is_vip", "outside_hours", "wants_human", "wants_chat"]) {
				if (read(name)) when[name] = read(name) === "true";
			}
			const result = { id: read("rule-id"), priority: Number(read("priority")), action: read("action") };
			if (Object.keys(when).length) result.when = when;
			return result;
		}).sort((left, right) => left.priority - right.priority);
		const ruleIds = routing.map((rule) => rule.id);
		if (new Set(ruleIds).size !== ruleIds.length) {
			message.textContent = "Идентификаторы правил должны быть уникальными.";
			message.classList.add("notice-error");
			message.hidden = false;
			saveButton.disabled = false;
			return;
		}
		const days = Array.from(form.querySelectorAll('[name="working_days"]:checked'), (field) => Number(field.value));
		if (!days.length) {
			message.textContent = "Выберите хотя бы один рабочий день.";
			message.classList.add("notice-error");
			message.hidden = false;
			saveButton.disabled = false;
			return;
		}
		const updatedConfig = {
			...config,
			greeting: form.elements.namedItem("greeting").value.trim(),
			disclosure: form.elements.namedItem("disclosure").value.trim(),
			closing: form.elements.namedItem("closing").value.trim(),
			faq: Array.from(faqList.querySelectorAll(".faq-item"), (card) => ({
				id: card.querySelector('[name="id"]').value.trim(),
				question: card.querySelector('[name="question"]').value.trim(),
				answer: card.querySelector('[name="answer"]').value.trim(),
			})),
			routing,
			handoff_number: form.elements.namedItem("handoff_number").value.trim(),
			vip_numbers: [
				...Array.from(vipList.querySelectorAll(".vip-item"), (item) => item.dataset.vipHash),
				...form.elements.namedItem("vip_numbers").value.split(/\r?\n/).map((number) => number.trim()).filter(Boolean),
			],
			working_hours: {
				tz: form.elements.namedItem("timezone").value.trim(),
				days,
				start: form.elements.namedItem("work_start").value,
				end: form.elements.namedItem("work_end").value,
			},
		};
		try {
			const response = await fetch("/api/config", {
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(updatedConfig),
			});
			const result = await response.json();
			if (!response.ok) {
				message.textContent = typeof result.detail === "string" ? result.detail : "Проверьте поля сценария.";
				message.classList.add("notice-error");
				message.hidden = false;
				return;
			}
			window.location.reload();
		} catch {
			message.textContent = "Не удалось сохранить изменения. Проверьте соединение с локальным приложением.";
			message.classList.add("notice-error");
			message.hidden = false;
		} finally {
			saveButton.disabled = false;
		}
	});
}

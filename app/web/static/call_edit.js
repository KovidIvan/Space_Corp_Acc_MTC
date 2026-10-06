(() => {
	const form = document.getElementById("call-edit-form");
	if (!form) return;

	const message = document.getElementById("edit-message");
	const transcript = JSON.parse(document.getElementById("transcript-data").textContent);

	form.addEventListener("submit", async (event) => {
		event.preventDefault();
		const payload = {
			summary: form.elements.summary.value,
			intent: form.elements.intent.value,
			urgency: form.elements.urgency.value,
			action: form.elements.action.value,
		};
		const updatedTranscript = transcript.map((segment, index) => {
			const text = form.elements[`segment-${index}`]?.value;
			if (text !== undefined && text !== segment.text) {
				return { ...segment, text, words: null };
			}
			return segment;
		});
		if (updatedTranscript.some((segment, index) => segment !== transcript[index])) {
			payload.transcript = updatedTranscript;
		}

		message.textContent = "Сохранение…";
		try {
			const response = await fetch(`/api/calls/${encodeURIComponent(form.dataset.callId)}`, {
				method: "PATCH",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(payload),
			});
			if (!response.ok) {
				const result = await response.json().catch(() => ({}));
				throw new Error(result.detail || "Не удалось сохранить изменения.");
			}
			message.textContent = "Изменения сохранены.";
			window.location.reload();
		} catch (error) {
			message.textContent = error.message || "Ошибка сохранения.";
		}
	});
})();

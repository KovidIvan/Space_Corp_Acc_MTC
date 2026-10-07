// caller.js — Web Audio API & WebSocket client for /ws/call (v1 protocol)

let socket = null;
let audioContext = null;
let micStream = null;
let processorNode = null;
let isCallActive = false;
let nextPlayTime = 0;
let pendingPcmSamples = new Int16Array(0);

const btnCall = document.getElementById("btn-call");
const btnHangup = document.getElementById("btn-hangup");
const btnTest = document.getElementById("btn-test");
const callerNumberInput = document.getElementById("caller-number");
const connDot = document.getElementById("conn-dot");
const connStatus = document.getElementById("conn-status");
const stateBadge = document.getElementById("state-badge");
const transcriptBox = document.getElementById("transcript");
const alertHandoff = document.getElementById("alert-handoff");
const handoffText = document.getElementById("handoff-text");
const alertChatOffer = document.getElementById("alert-chatoffer");
const chatOfferText = document.getElementById("chatoffer-text");

const STATE_NAMES = {
  GREET: "Приветствие и уведомление",
  ASK_NAME_COMPANY: "Уточнение имени и компании",
  ASK_REASON: "Уточнение цели звонка",
  ROUTE: "Маршрутизация",
  FAQ_ANSWER: "Ответ на вопрос (FAQ)",
  TAKE_MESSAGE: "Принятие сообщения",
  OFFER_CHAT: "Предложение перейти в чат",
  HANDOFF: "Переключение на руководителя",
  DECLINE: "Вежливый отказ",
  CLOSE: "Завершение разговора",
};

function appendMessage(who, text) {
  if (transcriptBox.children.length === 1 && transcriptBox.children[0].textContent.includes("Нажмите")) {
    transcriptBox.innerHTML = "";
  }
  const div = document.createElement("div");
  div.className = `msg ${who === "agent" ? "msg-agent" : "msg-caller"}`;

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = who === "agent" ? "🤖 Ассистент" : "👤 Вы (Звонящий)";

  const content = document.createElement("div");
  content.textContent = text;

  div.appendChild(meta);
  div.appendChild(content);
  transcriptBox.appendChild(div);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

function updateConnectionStatus(status, stateClass = "") {
  connStatus.textContent = status;
  connDot.className = `status-dot ${stateClass}`;
}

async function startCall() {
  const number = callerNumberInput.value.trim() || "+375291234567";
  btnCall.disabled = true;
  callerNumberInput.disabled = true;
  transcriptBox.innerHTML = "";
  alertHandoff.classList.remove("show");
  alertChatOffer.classList.remove("show");

  updateConnectionStatus("Соединение...", "speaking");

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/call`;

  socket = new WebSocket(wsUrl);
  socket.binaryType = "arraybuffer";

  socket.onopen = async () => {
    updateConnectionStatus("В разговоре", "active");
    btnHangup.disabled = false;
    btnTest.disabled = false;
    isCallActive = true;

    // 1. Send start handshake
    socket.send(JSON.stringify({
      type: "start",
      caller_number: number,
      protocol: 1,
    }));

    // 2. Initialize microphone capture
    try {
      await initMicrophone();
    } catch (err) {
      console.warn("Microphone not available or permission denied:", err);
      appendMessage("agent", "Внимание: микрофон недоступен. Вы можете нажать «Тест S1», чтобы протестировать сценарий.");
    }
  };

  socket.onmessage = async (event) => {
    if (typeof event.data === "string") {
      try {
        const msg = JSON.parse(event.data);
        handleControlMessage(msg);
      } catch (e) {
        console.error("Malformed JSON frame:", e);
      }
    } else if (event.data instanceof ArrayBuffer) {
      // Play incoming PCM16 audio from assistant
      playAudioChunk(event.data);
    }
  };

  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
    updateConnectionStatus("Ошибка соединения");
  };

  socket.onclose = (event) => {
    console.log("WebSocket closed:", event.code, event.reason);
    cleanupCall();
    updateConnectionStatus(`Звонок завершен (${event.reason || "код " + event.code})`);
  };
}

function handleControlMessage(msg) {
  switch (msg.type) {
    case "state":
      stateBadge.textContent = `Состояние: ${STATE_NAMES[msg.state] || msg.state}`;
      break;

    case "transcript":
      appendMessage(msg.who, msg.text);
      break;

    case "playback":
      if (msg.action === "start") {
        connDot.classList.add("speaking");
      } else {
        connDot.classList.remove("speaking");
      }
      break;

    case "handoff":
      handoffText.textContent = `Звонок переводится на номер руководителя: ${msg.number} (причина: ${msg.reason})`;
      alertHandoff.classList.add("show");
      break;

    case "chat_offer":
      chatOfferText.textContent = "Внешний чат недоступен в локальном режиме.";
      alertChatOffer.classList.add("show");
      break;

    case "end":
      stateBadge.textContent = "Состояние: Завершен";
      cleanupCall();
      updateConnectionStatus(`Звонок завершен (причина: ${msg.reason})`);
      break;

    case "error":
      alert(`Ошибка: ${msg.message}`);
      cleanupCall();
      updateConnectionStatus(`Ошибка: ${msg.code}`);
      break;
  }
}

async function initMicrophone() {
  audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  if (audioContext.sampleRate !== 16000) {
    await audioContext.close();
    audioContext = null;
    throw new Error("16 kHz audio is required");
  }
  nextPlayTime = audioContext.currentTime;

  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: 16000,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const source = audioContext.createMediaStreamSource(micStream);
  // Buffer callbacks are repacked into 320-sample (20 ms) wire frames.
  processorNode = audioContext.createScriptProcessor(512, 1, 1);

  processorNode.onaudioprocess = (event) => {
    if (!isCallActive || !socket || socket.readyState !== WebSocket.OPEN) return;
    const input = event.inputBuffer.getChannelData(0);

    // Convert Float32Array to Int16 PCM little-endian
    const pcm16 = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    const merged = new Int16Array(pendingPcmSamples.length + pcm16.length);
    merged.set(pendingPcmSamples);
    merged.set(pcm16, pendingPcmSamples.length);
    let offset = 0;
    while (offset + 320 <= merged.length) {
      socket.send(merged.slice(offset, offset + 320).buffer);
      offset += 320;
    }
    pendingPcmSamples = merged.slice(offset);
  };

  source.connect(processorNode);
  processorNode.connect(audioContext.destination);
}

function playAudioChunk(arrayBuffer) {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  }

  const int16View = new Int16Array(arrayBuffer);
  if (int16View.length === 0) return;

  const float32 = new Float32Array(int16View.length);
  for (let i = 0; i < int16View.length; i++) {
    float32[i] = int16View[i] / 32768.0;
  }

  const audioBuffer = audioContext.createBuffer(1, float32.length, 16000);
  audioBuffer.getChannelData(0).set(float32);

  const sourceNode = audioContext.createBufferSource();
  sourceNode.buffer = audioBuffer;
  sourceNode.connect(audioContext.destination);

  const now = audioContext.currentTime;
  if (nextPlayTime < now) {
    nextPlayTime = now;
  }
  sourceNode.start(nextPlayTime);
  nextPlayTime += audioBuffer.duration;
}

function hangupCall() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "end" }));
  }
  cleanupCall();
  updateConnectionStatus("Звонок завершен");
}

function sendTestAudio() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      type: "test_audio",
      fixture: "s1_urgent_client",
    }));
  }
}

function cleanupCall() {
  isCallActive = false;
  pendingPcmSamples = new Int16Array(0);
  btnCall.disabled = false;
  btnHangup.disabled = true;
  btnTest.disabled = true;
  callerNumberInput.disabled = false;
  connDot.className = "status-dot";

  if (processorNode) {
    processorNode.disconnect();
    processorNode = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
  if (audioContext && audioContext.state !== "closed") {
    audioContext.close();
    audioContext = null;
  }
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    socket.close();
    socket = null;
  }
}

btnCall.addEventListener("click", startCall);
btnHangup.addEventListener("click", hangupCall);
btnTest.addEventListener("click", sendTestAudio);

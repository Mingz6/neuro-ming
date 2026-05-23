const form = document.getElementById("chat-form");
const input = document.getElementById("user-input");
const messages = document.getElementById("messages");
const typing = document.getElementById("typing");
const clearBtn = document.getElementById("clear-btn");
const muteBtn = document.getElementById("mute-btn");
const micBtn = document.getElementById("mic-btn");
const voiceStatus = document.getElementById("voice-status");

const sessionId = crypto.randomUUID();
let muted = localStorage.getItem("neuro-ming-muted") === "true";

// --- Mute toggle ---
function updateMuteBtn() {
    muteBtn.textContent = muted ? "🔇" : "🔊";
    muteBtn.title = muted ? "Unmute voice" : "Mute voice";
}
updateMuteBtn();

muteBtn.addEventListener("click", () => {
    muted = !muted;
    localStorage.setItem("neuro-ming-muted", muted);
    updateMuteBtn();
});

// --- Audio playback ---
function playAudio(base64Data) {
    if (!base64Data || muted) return;
    try {
        const audio = new Audio("data:audio/mpeg;base64," + base64Data);
        audio.play().catch(() => {});
    } catch {
        // audio playback failed
    }
}

// --- Message rendering ---
function addMessage(role, text, audioData) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    div.appendChild(bubble);

    if (role === "bot" && audioData) {
        const replayBtn = document.createElement("button");
        replayBtn.className = "replay-btn";
        replayBtn.textContent = "🔊";
        replayBtn.title = "Replay";
        replayBtn.addEventListener("click", () => playAudio(audioData));
        div.appendChild(replayBtn);
    }

    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function setTyping(show) {
    typing.classList.toggle("hidden", !show);
    if (show) messages.scrollTop = messages.scrollHeight;
}

// --- Text chat (existing) ---
form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    addMessage("user", text);
    input.value = "";
    input.disabled = true;
    setTyping(true);

    try {
        const res = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                session_id: sessionId,
                tts_enabled: !muted,
            }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        addMessage("bot", data.response, data.audio);
        playAudio(data.audio);
    } catch {
        addMessage("bot", "meow... something broke. Try again? 😿");
    } finally {
        setTyping(false);
        input.disabled = false;
        input.focus();
    }
});

clearBtn.addEventListener("click", async () => {
    if (!confirm("Clear the conversation?")) return;
    await fetch("/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
    });
    while (messages.children.length > 1) {
        messages.removeChild(messages.lastChild);
    }
});

input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event("submit"));
    }
});

// =============================================================================
// VOICE: Push-to-talk via WebSocket
// =============================================================================

let voiceWs = null;
let mediaRecorder = null;
let recording = false;
let audioChunks = []; // TTS response chunks from server

function setVoiceStatus(text) {
    if (!text) {
        voiceStatus.classList.add("hidden");
        voiceStatus.textContent = "";
    } else {
        voiceStatus.classList.remove("hidden");
        voiceStatus.textContent = text;
    }
}

function getWsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws/voice`;
}

function connectVoiceWs() {
    if (voiceWs && voiceWs.readyState <= WebSocket.OPEN) return;

    voiceWs = new WebSocket(getWsUrl());
    voiceWs.binaryType = "arraybuffer";

    voiceWs.onopen = () => {
        voiceWs.send(JSON.stringify({ type: "config", session_id: sessionId }));
    };

    voiceWs.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
            // Binary = TTS audio chunk
            audioChunks.push(event.data);
        } else {
            // Text = JSON control message
            try {
                const data = JSON.parse(event.data);
                handleVoiceMessage(data);
            } catch {}
        }
    };

    voiceWs.onclose = () => {
        voiceWs = null;
    };

    voiceWs.onerror = () => {
        voiceWs = null;
    };
}

function handleVoiceMessage(data) {
    switch (data.type) {
        case "transcript":
            if (data.final) {
                addMessage("user", data.text);
            }
            setVoiceStatus("Thinking...");
            break;

        case "response":
            addMessage("bot", data.text);
            setVoiceStatus("Speaking...");
            break;

        case "audio_end":
            playResponseAudio();
            setVoiceStatus("");
            micBtn.classList.remove("recording", "processing");
            break;

        case "error":
            setVoiceStatus("");
            micBtn.classList.remove("recording", "processing");
            if (data.message) {
                addMessage("bot", `meow... ${data.message} 😿`);
            }
            break;
    }
}

function playResponseAudio() {
    if (muted || audioChunks.length === 0) {
        audioChunks = [];
        return;
    }

    // Combine all chunks into a single blob
    const blob = new Blob(audioChunks, { type: "audio/mpeg" });
    audioChunks = [];
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.play().catch(() => URL.revokeObjectURL(url));
}

async function startRecording() {
    if (recording) return;

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, sampleRate: 16000 }
        });

        connectVoiceWs();

        // Wait for WebSocket connection
        if (voiceWs.readyState !== WebSocket.OPEN) {
            await new Promise((resolve, reject) => {
                const orig = voiceWs.onopen;
                voiceWs.onopen = () => { if (orig) orig(); resolve(); };
                setTimeout(() => reject(new Error("WS connect timeout")), 3000);
            });
        }

        mediaRecorder = new MediaRecorder(stream, {
            mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : "audio/webm"
        });

        audioChunks = [];
        recording = true;
        micBtn.classList.add("recording");
        setVoiceStatus("Listening...");

        voiceWs.send(JSON.stringify({ type: "start", session_id: sessionId }));

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0 && voiceWs && voiceWs.readyState === WebSocket.OPEN) {
                voiceWs.send(e.data);
            }
        };

        // Send data every 250ms for near-real-time streaming
        mediaRecorder.start(250);
    } catch (err) {
        recording = false;
        micBtn.classList.remove("recording");
        setVoiceStatus("");
        console.error("Mic access denied or error:", err);
        addMessage("bot", "meow... I can't access your microphone. Check permissions? 🎙️");
    }
}

function stopRecording() {
    if (!recording || !mediaRecorder) return;

    recording = false;
    micBtn.classList.remove("recording");
    micBtn.classList.add("processing");
    setVoiceStatus("Processing...");

    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());

    // Signal end of audio
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
        voiceWs.send(JSON.stringify({ type: "stop" }));
    }

    mediaRecorder = null;
}

// --- Mic button: click to toggle ---
micBtn.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startRecording();
});
micBtn.addEventListener("mouseup", () => stopRecording());
micBtn.addEventListener("mouseleave", () => { if (recording) stopRecording(); });

// Touch support (mobile)
micBtn.addEventListener("touchstart", (e) => {
    e.preventDefault();
    startRecording();
});
micBtn.addEventListener("touchend", () => stopRecording());

// --- Space bar: hold to talk ---
let spaceHeld = false;
document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !spaceHeld && document.activeElement !== input) {
        e.preventDefault();
        spaceHeld = true;
        startRecording();
    }
});
document.addEventListener("keyup", (e) => {
    if (e.code === "Space" && spaceHeld) {
        e.preventDefault();
        spaceHeld = false;
        stopRecording();
    }
});

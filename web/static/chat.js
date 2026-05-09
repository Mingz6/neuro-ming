const form = document.getElementById("chat-form");
const input = document.getElementById("user-input");
const messages = document.getElementById("messages");
const typing = document.getElementById("typing");
const clearBtn = document.getElementById("clear-btn");
const muteBtn = document.getElementById("mute-btn");

const sessionId = crypto.randomUUID();
let muted = localStorage.getItem("neuro-ming-muted") === "true";

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

function playAudio(base64Data) {
    if (!base64Data || muted) return;
    try {
        const audio = new Audio("data:audio/mpeg;base64," + base64Data);
        audio.play().catch(() => {});
    } catch {
        // audio playback failed — just show text
    }
}

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

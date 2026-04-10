const form = document.getElementById("chat-form");
const input = document.getElementById("user-input");
const messages = document.getElementById("messages");
const typing = document.getElementById("typing");
const clearBtn = document.getElementById("clear-btn");

const sessionId = crypto.randomUUID();

function addMessage(role, text) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    div.appendChild(bubble);
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
            body: JSON.stringify({ message: text, session_id: sessionId }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        addMessage("bot", data.response);
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
    // Remove all messages except the greeting
    while (messages.children.length > 1) {
        messages.removeChild(messages.lastChild);
    }
});

// Allow Enter to submit
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event("submit"));
    }
});

const state = {
  messages: [],
  pipelineStages: [],
  sidebarOpen: true,
  requestInFlight: false,
};

const chatLog = document.getElementById("chatLog");
const emptyState = document.getElementById("emptyState");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const statusText = document.getElementById("statusText");
const pipelineStages = document.getElementById("pipelineStages");
const historyList = document.getElementById("historyList");
const historyCount = document.getElementById("historyCount");
const newSessionButton = document.getElementById("newSessionButton");
const endSessionButton = document.getElementById("endSessionButton");
const sidebar = document.getElementById("sidebar");
const openSidebarButton = document.getElementById("openSidebarButton");
const closeSidebarButton = document.getElementById("closeSidebarButton");
const intentPill = document.getElementById("intentPill");
const modelPill = document.getElementById("modelPill");

const stageOrder = ["intake", "preprocess", "intent", "routing", "knowledge", "semantic", "generation"];
let activeUtterance = null;
let activeSpeechButton = null;

function setStatus(text, loading = false) {
  statusText.textContent = text;
  statusText.classList.toggle("loading", loading);
}

function setActiveModel(intent = "idle", model = "waiting") {
  intentPill.textContent = `Intent: ${intent}`;
  modelPill.textContent = `Model: ${model}`;
}

function autoResizeTextarea() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 180)}px`;
}

function stopSpeaking() {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  if (activeSpeechButton) {
    activeSpeechButton.textContent = "Speak";
  }
  activeUtterance = null;
  activeSpeechButton = null;
}

async function copyMessage(content, button) {
  try {
    await navigator.clipboard.writeText(content);
    const originalLabel = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => {
      button.textContent = originalLabel;
    }, 1200);
    setStatus("Response copied to clipboard.");
  } catch (error) {
    setStatus("Clipboard access failed.");
  }
}

function speakMessage(content, button) {
  if (!("speechSynthesis" in window)) {
    setStatus("Speech playback is not supported in this browser.");
    return;
  }

  if (activeUtterance) {
    stopSpeaking();
    button.textContent = "Speak";
    setStatus("Speech playback stopped.");
    return;
  }

  const utterance = new SpeechSynthesisUtterance(content);
  activeUtterance = utterance;
  activeSpeechButton = button;
  button.textContent = "Stop";
  utterance.onend = () => {
    activeUtterance = null;
    activeSpeechButton = null;
    button.textContent = "Speak";
    setStatus("Speech playback finished.");
  };
  utterance.onerror = () => {
    activeUtterance = null;
    activeSpeechButton = null;
    button.textContent = "Speak";
    setStatus("Speech playback failed.");
  };
  window.speechSynthesis.speak(utterance);
  setStatus("Reading the response aloud...");
}

function createMessageElement(role, content) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const body = document.createElement("div");
  body.className = "bubble-content";
  body.textContent = content;
  bubble.appendChild(body);

  if (role === "assistant") {
    const actions = document.createElement("div");
    actions.className = "message-actions";

    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "message-action-button";
    copyButton.textContent = "Copy";
    copyButton.addEventListener("click", () => copyMessage(content, copyButton));

    const speakButton = document.createElement("button");
    speakButton.type = "button";
    speakButton.className = "message-action-button";
    speakButton.textContent = "Speak";
    speakButton.addEventListener("click", () => speakMessage(content, speakButton));

    actions.appendChild(copyButton);
    actions.appendChild(speakButton);
    bubble.appendChild(actions);
  }

  wrapper.appendChild(bubble);
  return wrapper;
}

function renderMessages() {
  chatLog.querySelectorAll(".message").forEach((node) => node.remove());

  if (state.messages.length === 0) {
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");

  state.messages.forEach((message) => {
    chatLog.appendChild(createMessageElement(message.role, message.content));
  });

  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderPipeline() {
  pipelineStages.innerHTML = "";

  if (state.pipelineStages.length === 0) {
    pipelineStages.innerHTML = `
      <article class="pipeline-stage">
        <div class="pipeline-stage-status">Waiting</div>
        <h4>Pipeline idle</h4>
        <p>Submit a prompt to watch each NLP stage update in sequence.</p>
      </article>
    `;
    return;
  }

  state.pipelineStages.forEach((stage) => {
    const card = document.createElement("article");
    card.className = `pipeline-stage is-${stage.status}`;
    card.innerHTML = `
      <div class="pipeline-stage-status">${stage.status}</div>
      <h4>${stage.label}</h4>
      <p>${stage.detail}</p>
    `;
    pipelineStages.appendChild(card);
  });
}

function resetPipeline() {
  state.pipelineStages = [];
  renderPipeline();
  setActiveModel();
}

function upsertStage(stage) {
  const existingIndex = state.pipelineStages.findIndex((entry) => entry.id === stage.id);
  if (existingIndex >= 0) {
    state.pipelineStages[existingIndex] = stage;
  } else {
    state.pipelineStages.push(stage);
  }

  state.pipelineStages.sort(
    (left, right) => stageOrder.indexOf(left.id) - stageOrder.indexOf(right.id),
  );
  renderPipeline();
}

function updateSidebarVisibility() {
  sidebar.classList.toggle("hidden", !state.sidebarOpen);
  openSidebarButton.classList.toggle("hidden", state.sidebarOpen);
}

function formatTimestamp(value) {
  const parsed = new Date(value.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

async function loadHistory() {
  try {
    const response = await fetch("/sessions");
    if (!response.ok) {
      throw new Error("Failed to load sessions.");
    }

    const sessions = await response.json();
    historyCount.textContent = sessions.length;
    historyList.innerHTML = "";

    if (sessions.length === 0) {
      historyList.innerHTML = `
        <div class="history-item">
          <div class="history-item-title">No saved sessions yet</div>
          <div class="history-item-time">End a session to store it here.</div>
        </div>
      `;
      return;
    }

    sessions.forEach((session) => {
      const card = document.createElement("article");
      card.className = "history-item";

      const openButton = document.createElement("button");
      openButton.type = "button";
      openButton.className = "history-open-button";
      const title = document.createElement("div");
      title.className = "history-item-title";
      title.textContent = session.title;

      const time = document.createElement("div");
      time.className = "history-item-time";
      time.textContent = formatTimestamp(session.created_at);

      openButton.appendChild(title);
      openButton.appendChild(time);
      openButton.addEventListener("click", () => loadSession(session.id));

      const exportRow = document.createElement("div");
      exportRow.className = "history-export-row";

      const formatSelect = document.createElement("select");
      formatSelect.className = "history-format-select";
      formatSelect.innerHTML = `
        <option value="pdf">PDF</option>
        <option value="docx">DOCX</option>
      `;

      const downloadButton = document.createElement("button");
      downloadButton.type = "button";
      downloadButton.className = "history-download-button";
      downloadButton.textContent = "Download";
      downloadButton.addEventListener("click", () => {
        downloadSessionExport(session.id, formatSelect.value);
      });

      exportRow.appendChild(formatSelect);
      exportRow.appendChild(downloadButton);
      card.appendChild(openButton);
      card.appendChild(exportRow);
      historyList.appendChild(card);
    });
  } catch (error) {
    historyList.innerHTML = `
      <div class="history-item">
        <div class="history-item-title">History unavailable</div>
        <div class="history-item-time">${error.message}</div>
      </div>
    `;
  }
}

async function downloadSessionExport(sessionId, format) {
  try {
    setStatus(`Preparing ${format.toUpperCase()} download...`, true);
    const response = await fetch(`/sessions/${sessionId}/export?format=${encodeURIComponent(format)}`);
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || "Failed to export this session.");
    }

    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const fallbackName = `chat-session.${format}`;
    const contentDisposition = response.headers.get("Content-Disposition") || "";
    const match = contentDisposition.match(/filename="([^"]+)"/i);

    link.href = downloadUrl;
    link.download = match ? match[1] : fallbackName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
    setStatus(`Downloaded session as ${format.toUpperCase()}.`);
  } catch (error) {
    setStatus(error.message);
  }
}

async function loadSession(sessionId) {
  try {
    const response = await fetch(`/sessions/${sessionId}`);
    if (!response.ok) {
      throw new Error("Could not load this session.");
    }

    const session = await response.json();
    state.messages = session.messages;
    renderMessages();
    setStatus(`Loaded saved session: ${session.title}`);
  } catch (error) {
    setStatus(error.message);
  }
}

function resetSession() {
  stopSpeaking();
  state.messages = [];
  renderMessages();
  resetPipeline();
  setStatus("New unsaved session started.");
}

async function sendMessage(message) {
  if (state.requestInFlight) {
    return;
  }

  state.requestInFlight = true;
  resetPipeline();
  setStatus("Processing query through the NLP pipeline...", true);

  state.messages.push({ role: "user", content: message });
  renderMessages();

  try {
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error("Failed to open the streaming chat pipeline.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let assistantResponse = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      lines.forEach((line) => {
        if (!line.trim()) {
          return;
        }

        const event = JSON.parse(line);

        if (event.type === "stage") {
          upsertStage(event.stage);

          if (event.stage.id === "intent") {
            setActiveModel(event.stage.meta.intent, modelPill.textContent.replace("Model: ", ""));
          }

          if (event.stage.id === "routing") {
            setActiveModel(intentPill.textContent.replace("Intent: ", ""), event.stage.meta.model);
          }

          setStatus(`${event.stage.label}...`, event.stage.status === "running");
        }

        if (event.type === "final") {
          assistantResponse = event.response;
          setActiveModel(event.intent, event.model);
          setStatus(`Response generated with ${event.model}. Session not yet saved.`);
        }

        if (event.type === "error") {
          throw new Error(event.detail || "The streaming pipeline failed.");
        }
      });
    }

    if (!assistantResponse) {
      throw new Error("The assistant did not return any content.");
    }

    state.messages.push({ role: "assistant", content: assistantResponse });
    renderMessages();
  } catch (error) {
    state.messages.push({
      role: "assistant",
      content: `Error: ${error.message}`,
    });
    renderMessages();
    setStatus("The request did not complete.");
  } finally {
    stopSpeaking();
    state.requestInFlight = false;
  }
}

async function endSession() {
  if (state.messages.length === 0) {
    setStatus("There is no active chat to save.");
    return;
  }

  try {
    setStatus("Saving session...", true);

    const response = await fetch("/sessions/end", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ messages: state.messages }),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || "Failed to save the session.");
    }

    const session = await response.json();
    await loadHistory();
    resetSession();
    setStatus(`Session saved as "${session.title}".`);
  } catch (error) {
    setStatus(error.message);
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();
  if (!message) {
    return;
  }

  messageInput.value = "";
  autoResizeTextarea();
  await sendMessage(message);
});

messageInput.addEventListener("input", autoResizeTextarea);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

newSessionButton.addEventListener("click", resetSession);
endSessionButton.addEventListener("click", endSession);

closeSidebarButton.addEventListener("click", () => {
  state.sidebarOpen = false;
  updateSidebarVisibility();
});

openSidebarButton.addEventListener("click", () => {
  state.sidebarOpen = true;
  updateSidebarVisibility();
});

updateSidebarVisibility();
loadHistory();
renderMessages();
renderPipeline();
setActiveModel();
autoResizeTextarea();

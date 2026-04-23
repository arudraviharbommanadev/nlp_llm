const state = {
  messages: [],
  pipelineStages: [],
  sidebarOpen: true,
  requestInFlight: false,
  currentSessionId: null,
  orchestratorRuns: [],
  activeTrace: null,
};

const chatLog = document.getElementById("chatLog");
const emptyState = document.getElementById("emptyState");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const statusText = document.getElementById("statusText");
const pipelineStages = document.getElementById("pipelineStages");
const historyList = document.getElementById("historyList");
const historyCount = document.getElementById("historyCount");
const historyTabButton = document.getElementById("historyTabButton");
const personalizeTabButton = document.getElementById("personalizeTabButton");
const historyPanel = document.getElementById("historyPanel");
const personalizePanel = document.getElementById("personalizePanel");
const themeButtons = document.querySelectorAll("[data-theme-option]");
const fontSelect = document.getElementById("fontSelect");
const newSessionButton = document.getElementById("newSessionButton");
const endSessionButton = document.getElementById("endSessionButton");
const sidebar = document.getElementById("sidebar");
const openSidebarButton = document.getElementById("openSidebarButton");
const closeSidebarButton = document.getElementById("closeSidebarButton");
const intentPill = document.getElementById("intentPill");
const modelPill = document.getElementById("modelPill");
const ragPill = document.getElementById("ragPill");
const queryTypeBadge = document.getElementById("queryTypeBadge");
const secondaryIntentList = document.getElementById("secondaryIntentList");
const taskList = document.getElementById("taskList");

const stageOrder = ["intake", "preprocess", "orchestration", "routing", "retrieval", "task_execution", "aggregation", "final_response"];
const THEME_STORAGE_KEY = "study_theme";
const FONT_STORAGE_KEY = "study_font";
let activeUtterance = null;
let activeSpeechButton = null;

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  themeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.themeOption === theme);
  });
}

function applyFont(font) {
  document.documentElement.dataset.font = font;
  localStorage.setItem(FONT_STORAGE_KEY, font);
  if (fontSelect) {
    fontSelect.value = font;
  }
}

function initializePersonalization() {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "blue";
  const savedFont = localStorage.getItem(FONT_STORAGE_KEY) || "aptos";
  applyTheme(savedTheme);
  applyFont(savedFont);
}

function setSidebarView(view) {
  const showHistory = view === "history";
  historyTabButton.classList.toggle("is-active", showHistory);
  personalizeTabButton.classList.toggle("is-active", !showHistory);
  historyPanel.classList.toggle("hidden", !showHistory);
  personalizePanel.classList.toggle("hidden", showHistory);
}

function setStatus(text, loading = false) {
  statusText.textContent = text;
  statusText.classList.toggle("loading", loading);
}

function setActiveModel(intent = "idle", model = "waiting", ragMode = "none") {
  intentPill.textContent = `Intent: ${intent}`;
  modelPill.textContent = `Model: ${model}`;
  ragPill.textContent = `RAG: ${ragMode}`;
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

function createMessageElement(message) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${message.role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const body = document.createElement("div");
  body.className = "bubble-content";
  body.textContent = message.content;
  bubble.appendChild(body);

  if (message.role === "assistant") {
    const meta = document.createElement("div");
    meta.className = "bubble-meta";
    meta.textContent = `${message.task_type || "answer"} • ${message.model_used || "local model"}`;
    bubble.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "message-actions";

    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "message-action-button";
    copyButton.textContent = "Copy";
    copyButton.addEventListener("click", () => copyMessage(message.content, copyButton));

    const speakButton = document.createElement("button");
    speakButton.type = "button";
    speakButton.className = "message-action-button";
    speakButton.textContent = "Speak";
    speakButton.addEventListener("click", () => speakMessage(message.content, speakButton));

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
    chatLog.appendChild(createMessageElement(message));
  });

  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderPipeline() {
  pipelineStages.innerHTML = "";

  if (state.pipelineStages.length === 0) {
    const pipelinePanel = document.querySelector(".pipeline-panel");
    if (pipelinePanel) {
      pipelinePanel.classList.add("hidden");
    }
    return;
  }

  const pipelinePanel = document.querySelector(".pipeline-panel");
  if (pipelinePanel) {
    pipelinePanel.classList.remove("hidden");
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

function renderTrace(trace = null) {
  state.activeTrace = trace;
  if (!trace) {
    queryTypeBadge.textContent = "idle";
    secondaryIntentList.innerHTML = `<span class="trace-chip muted">None</span>`;
    taskList.innerHTML = `
      <article class="task-card">
        <div class="task-card-top">
          <strong>No tasks</strong>
          <span class="task-priority">P0</span>
        </div>
        <p>Tasks will appear here.</p>
      </article>
    `;
    setActiveModel();
    return;
  }

  queryTypeBadge.textContent = trace.query_type || "simple";
  setActiveModel(
    trace.primary_intent || "idle",
    trace.final_aggregation_model || "waiting",
    trace.rag_mode || "none",
  );

  secondaryIntentList.innerHTML = "";
  const secondaryIntents = trace.secondary_intents || [];
  if (secondaryIntents.length === 0) {
    secondaryIntentList.innerHTML = `<span class="trace-chip muted">None</span>`;
  } else {
    secondaryIntents.forEach((intent) => {
      const chip = document.createElement("span");
      chip.className = "trace-chip";
      chip.textContent = intent;
      secondaryIntentList.appendChild(chip);
    });
  }

  taskList.innerHTML = "";
  (trace.tasks || []).forEach((task) => {
    const card = document.createElement("article");
    card.className = "task-card";
    const dependsOn = task.depends_on && task.depends_on.length
      ? `Depends on: ${task.depends_on.join(", ")}`
      : "Ready immediately";
    card.innerHTML = `
      <div class="task-card-top">
        <strong>${task.task_type}</strong>
        <span class="task-priority">P${task.priority}</span>
      </div>
      <div class="task-card-meta">${task.model}</div>
      <p>${task.query}</p>
      <div class="task-card-foot">${dependsOn}</div>
    `;
    taskList.appendChild(card);
  });
}

function resetPipeline() {
  state.pipelineStages = [];
  renderPipeline();
}

function resetSession() {
  stopSpeaking();
  state.messages = [];
  state.currentSessionId = null;
  state.orchestratorRuns = [];
  renderMessages();
  resetPipeline();
  renderTrace(null);
  setStatus("New session.");
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
  openSidebarButton.setAttribute("aria-label", "Open menu");
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
          <div class="history-item-title">No saved sessions</div>
          <div class="history-item-time">Saved chats appear here.</div>
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

      const metaRow = document.createElement("div");
      metaRow.className = "history-item-tags";
      metaRow.innerHTML = `
        <span>${session.primary_intent || "study"}</span>
        <span>${session.last_model_used || "local"}</span>
        <span>${session.needs_rag ? "rag" : "no-rag"}</span>
      `;

      const time = document.createElement("div");
      time.className = "history-item-time";
      time.textContent = formatTimestamp(session.created_at);

      openButton.appendChild(title);
      openButton.appendChild(metaRow);
      openButton.appendChild(time);
      openButton.addEventListener("click", () => loadSession(session.id));

      const actionRow = document.createElement("div");
      actionRow.className = "history-action-row";

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

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "history-delete-button";
      deleteButton.textContent = "Delete";
      deleteButton.addEventListener("click", () => deleteSavedSession(session.id, session.title));

      actionRow.appendChild(formatSelect);
      actionRow.appendChild(downloadButton);
      actionRow.appendChild(deleteButton);
      card.appendChild(openButton);
      card.appendChild(actionRow);
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
    state.currentSessionId = session.id;
    state.messages = session.messages;
    state.orchestratorRuns = session.orchestrator_runs || [];
    renderMessages();
    renderTrace(state.orchestratorRuns.at(-1) || session.messages.at(-1)?.orchestrator || null);
    resetPipeline();
    setStatus(`Loaded saved session: ${session.title}`);
  } catch (error) {
    setStatus(error.message);
  }
}

async function deleteSavedSession(sessionId, title) {
  const confirmed = window.confirm(`Delete the saved chat "${title}"? This cannot be undone.`);
  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(`/sessions/${sessionId}`, { method: "DELETE" });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || "Failed to delete the session.");
    }

    if (state.currentSessionId === sessionId) {
      resetSession();
      setStatus(`Deleted "${title}".`);
    } else {
      setStatus(`Deleted "${title}".`);
    }
    await loadHistory();
  } catch (error) {
    setStatus(error.message);
  }
}

async function sendMessage(message) {
  if (state.requestInFlight) {
    return;
  }

  state.requestInFlight = true;
  resetPipeline();
  setStatus("Processing...", true);

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
    let assistantPayload = null;

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

          if (event.stage.id === "orchestration") {
            setActiveModel(
              event.stage.meta.intent,
              modelPill.textContent.replace("Model: ", ""),
              event.stage.meta.rag_mode || "none",
            );
          }

          if (event.stage.id === "routing") {
            setActiveModel(
              intentPill.textContent.replace("Intent: ", ""),
              event.stage.meta.model,
              ragPill.textContent.replace("RAG: ", ""),
            );
          }

          setStatus(`${event.stage.label}...`, event.stage.status === "running");
        }

        if (event.type === "final") {
          assistantPayload = event;
          renderTrace(event.orchestrator);
          state.orchestratorRuns.push(event.orchestrator);
          setStatus(`Ready. Model: ${event.model}.`);
        }

        if (event.type === "error") {
          throw new Error(event.detail || "The streaming pipeline failed.");
        }
      });
    }

    if (!assistantPayload) {
      throw new Error("The assistant did not return any content.");
    }

    state.messages.push({
      role: "assistant",
      content: assistantPayload.response,
      model_used: assistantPayload.model,
      task_type: assistantPayload.intent,
      orchestrator: assistantPayload.orchestrator,
    });
    renderMessages();
  } catch (error) {
    state.messages.push({
      role: "assistant",
      content: `Error: ${error.message}`,
      model_used: "system",
      task_type: "error",
    });
    renderMessages();
    setStatus("Request failed.");
  } finally {
    stopSpeaking();
    state.requestInFlight = false;
  }
}

async function endSession() {
  if (state.messages.length === 0) {
    setStatus("Nothing to save.");
    return;
  }

  try {
    setStatus("Saving...", true);

    const response = await fetch("/sessions/end", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messages: state.messages,
        orchestrator_runs: state.orchestratorRuns,
      }),
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
historyTabButton.addEventListener("click", () => setSidebarView("history"));
personalizeTabButton.addEventListener("click", () => setSidebarView("personalize"));

themeButtons.forEach((button) => {
  button.addEventListener("click", () => applyTheme(button.dataset.themeOption));
});

fontSelect.addEventListener("change", (event) => {
  applyFont(event.target.value);
});

closeSidebarButton.addEventListener("click", () => {
  state.sidebarOpen = false;
  updateSidebarVisibility();
});

openSidebarButton.addEventListener("click", () => {
  state.sidebarOpen = true;
  updateSidebarVisibility();
});

updateSidebarVisibility();
initializePersonalization();
setSidebarView("history");
loadHistory();
renderMessages();
renderPipeline();
renderTrace(null);
autoResizeTextarea();

const transcript = document.querySelector("#transcript");
const analyzeButton = document.querySelector("#analyze");
const confirmButton = document.querySelector("#confirm");
const result = document.querySelector("#result");
const message = document.querySelector("#message");
const tasks = document.querySelector("#tasks");
const memories = document.querySelector("#memories");
const conversationId = document.querySelector("#conversationId");
let currentAnalysis = null;

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "请求失败");
  return body;
}

analyzeButton.addEventListener("click", async () => {
  if (!transcript.value.trim()) return;
  message.textContent = "正在分析……";
  analyzeButton.disabled = true;
  confirmButton.disabled = true;
  try {
    currentAnalysis = await request("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        transcript: transcript.value,
        conversation_id: conversationId.value || "default",
      }),
    });
    result.textContent = JSON.stringify(currentAnalysis, null, 2);
    confirmButton.disabled = !currentAnalysis.has_task;
    message.textContent = currentAnalysis.has_task
      ? "请审阅结果，确认后才会保存。"
      : "未识别到需要保存的任务。";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    analyzeButton.disabled = false;
  }
});

confirmButton.addEventListener("click", async () => {
  message.textContent = "正在保存……";
  confirmButton.disabled = true;
  try {
    await request("/api/tasks/confirm", {
      method: "POST",
      body: JSON.stringify({
        transcript: transcript.value,
        conversation_id: conversationId.value || "default",
        analysis: currentAnalysis,
      }),
    });
    message.textContent = "任务已保存。";
    await loadTasks();
    await loadMemories();
  } catch (error) {
    message.textContent = error.message;
    confirmButton.disabled = false;
  }
});

async function loadTasks() {
  try {
    const rows = await request("/api/tasks");
    tasks.innerHTML = rows.length ? rows.map((task) => `
      <article class="task">
        <h3>${escapeHtml(task.title)}</h3>
        <div class="meta">${task.status} · ${task.priority} · 风险 ${task.risk_level}</div>
        <p>${escapeHtml(task.customer_intent)}</p>
        <p><strong>建议回复：</strong>${escapeHtml(task.suggested_reply)}</p>
      </article>`).join("") : "暂无任务";
  } catch (error) {
    tasks.textContent = error.message;
  }
}

async function loadMemories() {
  try {
    const id = encodeURIComponent(conversationId.value || "default");
    const rows = await request(`/api/memories?conversation_id=${id}`);
    memories.innerHTML = rows.length ? rows.map((memory) => `
      <article class="task memory">
        <h3>${escapeHtml(memory.summary)}</h3>
        <div class="meta">${memory.status}${memory.resume_at ? ` · 恢复时间 ${escapeHtml(memory.resume_at)}` : ""}</div>
        <button class="complete-memory" data-id="${memory.id}">标记完成</button>
      </article>`).join("") : "当前会话暂无未完成记忆";
  } catch (error) {
    memories.textContent = error.message;
  }
}

memories.addEventListener("click", async (event) => {
  const button = event.target.closest(".complete-memory");
  if (!button) return;
  button.disabled = true;
  try {
    await request(`/api/memories/${button.dataset.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "completed" }),
    });
    await loadMemories();
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false;
  }
});

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

document.querySelector("#refresh").addEventListener("click", loadTasks);
conversationId.addEventListener("change", loadMemories);
loadTasks();
loadMemories();

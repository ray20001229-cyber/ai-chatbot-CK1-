const $ = (selector) => document.querySelector(selector);
const transcript = $("#transcript");
const conversationId = $("#conversationId");
const customerSelect = $("#customerSelect");
const message = $("#message");
let currentAnalysis = null;
let customerRows = [];
let conversationRows = [];
let activeConversation = null;
let chatSocket = null;

async function request(url, options = {}) {
  const headers = options.body instanceof FormData
    ? {} : { "Content-Type": "application/json" };
  const response = await fetch(url, {
    headers,
    ...options,
  });
  if (response.status === 204) return null;
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "请求失败");
  return body;
}

async function loadConversations() {
  conversationRows = await request("/api/conversations");
  $("#conversationList").innerHTML = conversationRows.length
    ? conversationRows.map((row) => `
      <button class="conversation-row ${activeConversation?.id === row.id ? "active" : ""}"
        data-id="${row.id}">
        <strong>${escapeHtml(row.subject || row.external_id)}</strong>
        <div class="meta">${escapeHtml(row.channel)} · ${escapeHtml(row.status)}
          · ${row.handoff_status === "bot" ? "机器人" : "人工"}
        </div>
      </button>`).join("")
    : `<p class="hint" style="padding:12px">暂无会话</p>`;
}

async function selectConversation(id) {
  activeConversation = conversationRows.find((row) => row.id === id);
  if (!activeConversation) return;
  $("#chatTitle").textContent =
    `${activeConversation.subject || activeConversation.external_id} · ${activeConversation.channel}`;
  $("#automationControls").hidden = false;
  $("#automationEnabled").checked = activeConversation.automation_enabled;
  $("#handoffStatus").value = activeConversation.handoff_status;
  $("#handoffReason").textContent = activeConversation.handoff_reason || "";
  $("#conversationSummary").hidden = !activeConversation.memory_summary;
  $("#summaryText").textContent =
    activeConversation.memory_summary || "尚未生成摘要";
  await Promise.all([loadChatMessages(), loadChatAttachments()]);
  connectChatSocket();
  await loadConversations();
}

async function loadChatMessages() {
  if (!activeConversation) return;
  const rows = await request(
    `/api/conversations/${activeConversation.id}/messages`
  );
  $("#chatMessages").innerHTML = rows.map(renderMessage).join("");
  $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
}

function renderMessage(row) {
  return `<div class="bubble ${row.sender_type}">
    <div class="meta">${escapeHtml(row.sender_name || row.sender_type)} · ${formatTime(row.received_at)}</div>
    <div>${escapeHtml(row.content)}</div>
  </div>`;
}

async function loadChatAttachments() {
  if (!activeConversation) return;
  const rows = await request(
    `/api/conversations/${activeConversation.id}/attachments`
  );
  $("#chatAttachments").innerHTML = rows.length
    ? `<strong>附件：</strong>` + rows.map((row) =>
      `<a class="attachment-link" href="/api/attachments/${row.id}/download">
        ${escapeHtml(row.original_name)} (${Math.ceil(row.size_bytes / 1024)}KB)
      </a>`).join("")
    : "";
}

function connectChatSocket() {
  if (chatSocket) chatSocket.close();
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  chatSocket = new WebSocket(
    `${protocol}://${location.host}/api/ws/conversations/${activeConversation.id}`
  );
  chatSocket.onmessage = (event) => {
    const row = JSON.parse(event.data);
    if (row.type === "error") {
      message.textContent = row.detail;
      return;
    }
    $("#chatMessages").insertAdjacentHTML("beforeend", renderMessage(row));
    $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
  };
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString("zh-CN") : "未设置";
}

async function loadDashboard() {
  const data = await request("/api/dashboard");
  const metrics = [
    ["任务总数", data.total_tasks],
    ["待处理", data.pending_tasks],
    ["办理中", data.in_progress_tasks],
    ["已逾期", data.overdue_tasks],
    ["高风险", data.high_risk_tasks],
    ["有效提醒", data.active_reminders],
    ["延期记忆", data.deferred_memories],
    ["客户数量", data.customers],
  ];
  $("#dashboard").innerHTML = metrics.map(([label, value]) =>
    `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`
  ).join("");
}

async function loadReminders() {
  const rows = await request("/api/reminders");
  $("#reminders").innerHTML = rows.length ? rows.map((row) => `
    <article class="item reminder">
      <h3>${escapeHtml(row.title)}</h3>
      <div class="meta">${escapeHtml(row.source_type)} · ${formatTime(row.remind_at)}</div>
      <p>${escapeHtml(row.message)}</p>
      <button class="dismiss-reminder small" data-id="${row.id}">忽略提醒</button>
    </article>`).join("") : "暂无到期提醒";
}

async function loadCustomers() {
  customerRows = await request("/api/customers");
  $("#customers").innerHTML = customerRows.length ? customerRows.map((row) => `
    <article class="item">
      <h3>${escapeHtml(row.name)} <span class="badge">${escapeHtml(row.external_id)}</span></h3>
      <div class="meta">${escapeHtml(row.phone || "无电话")} · ${escapeHtml(row.email || "无邮箱")}</div>
      <p>${escapeHtml(row.notes || "")}</p>
      <div class="item-actions">
        <button class="edit-customer small" data-id="${row.id}">编辑</button>
        <button class="delete-customer danger small" data-id="${row.id}">删除</button>
      </div>
    </article>`).join("") : "暂无客户资料";
  const selected = customerSelect.value;
  customerSelect.innerHTML = `<option value="">不关联客户</option>` +
    customerRows.map((row) =>
      `<option value="${row.id}">${escapeHtml(row.name)} (${escapeHtml(row.external_id)})</option>`
    ).join("");
  customerSelect.value = selected;
}

async function loadTasks() {
  const filter = $("#taskFilter").value;
  const rows = await request(`/api/tasks${filter ? `?task_status=${filter}` : ""}`);
  $("#tasks").innerHTML = rows.length ? rows.map((task) => `
    <article class="item">
      <h3>${escapeHtml(task.title)}</h3>
      <div class="meta">
        ${task.status} · ${task.priority} · 风险 ${task.risk_level} ·
        截止 ${formatTime(task.due_at)}
      </div>
      <p>${escapeHtml(task.customer_intent)}</p>
      <p><strong>建议回复：</strong>${escapeHtml(task.suggested_reply)}</p>
      <div class="item-actions">
        <button class="edit-task small" data-id="${task.id}">编辑</button>
        <button class="complete-task small" data-id="${task.id}">标记完成</button>
        <button class="delete-task danger small" data-id="${task.id}">删除</button>
      </div>
    </article>`).join("") : "暂无任务";
}

async function loadMemories() {
  const id = encodeURIComponent(conversationId.value || "default");
  const rows = await request(`/api/memories?conversation_id=${id}`);
  $("#memories").innerHTML = rows.length ? rows.map((memory) => `
    <article class="item memory">
      <h3>${escapeHtml(memory.summary)}</h3>
      <div class="meta">${memory.status} · 恢复时间 ${formatTime(memory.resume_at)}</div>
      <button class="complete-memory small" data-id="${memory.id}">标记完成</button>
    </article>`).join("") : "当前会话暂无未完成记忆";
}

async function loadCalendar() {
  const rows = await request("/api/calendar/events");
  $("#calendarEvents").innerHTML = rows.length ? rows.map((event) => `
    <article class="item calendar-event">
      <h3>${escapeHtml(event.title)}</h3>
      <div class="meta">
        ${escapeHtml(event.source_type)} · ${formatTime(event.starts_at)}
        ${event.ends_at ? ` 至 ${formatTime(event.ends_at)}` : ""}
        ${event.time_basis ? ` · ${escapeHtml(event.time_basis)}` : ""}
      </div>
      <p>${escapeHtml(event.description || "")}</p>
      ${event.time_reason ? `<p><strong>时间依据：</strong>${escapeHtml(event.time_reason)}</p>` : ""}
      ${event.source_type === "manual" ? `
        <div class="item-actions">
          <button class="edit-calendar small" data-id="${event.id}">编辑</button>
          <button class="delete-calendar danger small" data-id="${event.id}">删除</button>
        </div>` : ""}
    </article>`).join("") : "暂无日历事件";
}

async function refreshAll() {
  try {
    await Promise.all([
      loadDashboard(), loadReminders(), loadCustomers(), loadTasks(), loadMemories(),
      loadCalendar(),
      loadConversations(),
    ]);
  } catch (error) {
    message.textContent = error.message;
  }
}

$("#conversationForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const created = await request("/api/conversations", {
      method: "POST",
      body: JSON.stringify({
        channel: $("#conversationChannel").value,
        external_id: $("#conversationExternalId").value,
        subject: $("#conversationSubject").value || null,
        customer_id: customerSelect.value || null,
      }),
    });
    event.target.reset();
    await loadConversations();
    await selectConversation(created.id);
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#conversationList").addEventListener("click", (event) => {
  const row = event.target.closest(".conversation-row");
  if (row) selectConversation(row.dataset.id);
});

$("#saveAutomation").addEventListener("click", async () => {
  if (!activeConversation) return;
  try {
    const updated = await request(
      `/api/conversations/${activeConversation.id}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          automation_enabled: $("#automationEnabled").checked,
          handoff_status: $("#handoffStatus").value,
          handoff_reason: $("#handoffStatus").value === "bot"
            ? null : (activeConversation.handoff_reason || "客服手动设置"),
        }),
      },
    );
    activeConversation = updated;
    message.textContent = "自动回复与转人工设置已保存。";
    await loadConversations();
    await selectConversation(updated.id);
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeConversation) {
    message.textContent = "请先选择会话。";
    return;
  }
  const content = $("#chatContent").value.trim();
  const file = $("#chatAttachment").files[0];
  try {
    if (content) {
      const payload = {
        sender_type: $("#chatSenderType").value,
        sender_name: $("#chatSenderName").value || null,
        content,
      };
      if (chatSocket?.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify(payload));
      } else {
        await request(`/api/conversations/${activeConversation.id}/messages`, {
          method: "POST", body: JSON.stringify(payload),
        });
        await loadChatMessages();
      }
      $("#chatContent").value = "";
    }
    if (file) {
      const form = new FormData();
      form.append("upload", file);
      await request(
        `/api/conversations/${activeConversation.id}/attachments`,
        { method: "POST", body: form },
      );
      $("#chatAttachment").value = "";
      await loadChatAttachments();
    }
    await loadConversations();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#analyze").addEventListener("click", async () => {
  if (!transcript.value.trim()) return;
  message.textContent = "正在分析……";
  $("#analyze").disabled = true;
  $("#confirm").disabled = true;
  try {
    currentAnalysis = await request("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        transcript: transcript.value,
        conversation_id: conversationId.value || "default",
      }),
    });
    $("#result").textContent = JSON.stringify(currentAnalysis, null, 2);
    $("#confirm").disabled = !currentAnalysis.has_task;
    message.textContent = currentAnalysis.has_task
      ? "请审阅结果，确认后才会保存。"
      : "未识别到需要保存的任务。";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    $("#analyze").disabled = false;
  }
});

$("#confirm").addEventListener("click", async () => {
  try {
    await request("/api/tasks/confirm", {
      method: "POST",
      body: JSON.stringify({
        transcript: transcript.value,
        conversation_id: conversationId.value || "default",
        customer_id: customerSelect.value || null,
        analysis: currentAnalysis,
      }),
    });
    message.textContent = "任务和相关记忆已保存。";
    $("#confirm").disabled = true;
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#customerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/api/customers", {
      method: "POST",
      body: JSON.stringify({
        external_id: $("#customerExternalId").value,
        name: $("#customerName").value,
        phone: $("#customerPhone").value || null,
        email: $("#customerEmail").value || null,
        notes: $("#customerNotes").value || null,
      }),
    });
    event.target.reset();
    await Promise.all([loadCustomers(), loadDashboard()]);
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#calendarForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/api/calendar/events", {
      method: "POST",
      body: JSON.stringify({
        title: $("#calendarTitle").value,
        starts_at: new Date($("#calendarStart").value).toISOString(),
        ends_at: $("#calendarEnd").value
          ? new Date($("#calendarEnd").value).toISOString() : null,
        customer_id: customerSelect.value || null,
      }),
    });
    event.target.reset();
    await loadCalendar();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#calendarEvents").addEventListener("click", async (event) => {
  const id = event.target.dataset.id;
  if (!id) return;
  try {
    if (event.target.classList.contains("edit-calendar")) {
      const title = prompt("新的事件标题");
      if (!title) return;
      await request(`/api/calendar/events/${id}`, {
        method: "PATCH", body: JSON.stringify({ title }),
      });
    }
    if (event.target.classList.contains("delete-calendar")) {
      if (!confirm("确定删除该日历事件吗？")) return;
      await request(`/api/calendar/events/${id}`, { method: "DELETE" });
    }
    await loadCalendar();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#customers").addEventListener("click", async (event) => {
  const id = event.target.dataset.id;
  if (!id) return;
  const customer = customerRows.find((row) => row.id === id);
  try {
    if (event.target.classList.contains("edit-customer")) {
      const name = prompt("客户姓名", customer.name);
      if (name === null) return;
      const notes = prompt("客户备注", customer.notes || "");
      if (notes === null) return;
      await request(`/api/customers/${id}`, {
        method: "PATCH", body: JSON.stringify({ name, notes }),
      });
    }
    if (event.target.classList.contains("delete-customer")) {
      if (!confirm("确定删除该客户资料吗？关联任务会保留。")) return;
      await request(`/api/customers/${id}`, { method: "DELETE" });
    }
    await Promise.all([loadCustomers(), loadDashboard()]);
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#tasks").addEventListener("click", async (event) => {
  const id = event.target.dataset.id;
  if (!id) return;
  try {
    if (event.target.classList.contains("complete-task")) {
      await request(`/api/tasks/${id}`, {
        method: "PATCH", body: JSON.stringify({ status: "completed" }),
      });
    }
    if (event.target.classList.contains("edit-task")) {
      const title = prompt("新的任务标题");
      if (!title) return;
      const priority = prompt("优先级：low / medium / high / urgent", "medium");
      if (!priority) return;
      const due = prompt("截止时间（ISO 8601，留空表示无截止时间）", "");
      await request(`/api/tasks/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title, priority, due_at: due || null,
        }),
      });
    }
    if (event.target.classList.contains("delete-task")) {
      if (!confirm("确定删除该任务吗？此操作无法从页面恢复。")) return;
      await request(`/api/tasks/${id}`, { method: "DELETE" });
    }
    await Promise.all([loadTasks(), loadDashboard(), loadReminders(), loadCalendar()]);
  } catch (error) {
    message.textContent = error.message;
  }
});

$("#memories").addEventListener("click", async (event) => {
  const id = event.target.dataset.id;
  if (!id || !event.target.classList.contains("complete-memory")) return;
  await request(`/api/memories/${id}`, {
    method: "PATCH", body: JSON.stringify({ status: "completed" }),
  });
  await Promise.all([loadMemories(), loadDashboard(), loadReminders(), loadCalendar()]);
});

$("#reminders").addEventListener("click", async (event) => {
  const id = event.target.dataset.id;
  if (!id || !event.target.classList.contains("dismiss-reminder")) return;
  await request(`/api/reminders/${id}/dismiss`, { method: "PATCH" });
  await Promise.all([loadReminders(), loadDashboard()]);
});

$("#scanReminders").addEventListener("click", async () => {
  const result = await request("/api/reminders/scan", { method: "POST" });
  message.textContent = `扫描完成，新增 ${result.created} 条提醒。`;
  await Promise.all([loadReminders(), loadDashboard()]);
});

$("#refreshAll").addEventListener("click", refreshAll);
$("#taskFilter").addEventListener("change", loadTasks);
conversationId.addEventListener("change", loadMemories);
setInterval(() => Promise.all([loadReminders(), loadDashboard()]), 30000);
refreshAll();

const STATUS_COLORS = {
  "潛在客戶": "#6366f1",
  "洽談中": "#d97706",
  "已成交": "#16a34a",
  "暫停": "#64748b",
  "流失": "#dc2626",
};

const state = {
  meta: { statuses: [], contact_methods: [], summary: {} },
  customers: [],
  selectedId: null,
  editingId: null,
};

const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function badge(status) {
  return `<span class="badge" style="--c:${STATUS_COLORS[status] || "#64748b"}">${esc(status)}</span>`;
}

function today() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "發生錯誤");
  return data;
}

// ---------- 載入資料 ----------

async function loadMeta() {
  state.meta = await api("GET", "/api/meta");
  renderSummary();
}

// 目前的搜尋／篩選／排序條件（列表與 CSV 匯出共用）
function customerQuery() {
  const params = new URLSearchParams();
  const q = $("#search").value.trim();
  const status = $("#filter-status").value;
  if (q) params.set("q", q);
  if (status) params.set("status", status);
  const sort = $("#sort-field").value;
  if (sort) {
    params.set("sort", sort);
    params.set("order", $("#sort-order").dataset.order);
  }
  return params;
}

async function loadCustomers() {
  state.customers = await api("GET", "/api/customers?" + customerQuery());
  renderList();
}

async function refresh() {
  await Promise.all([loadMeta(), loadCustomers()]);
  if (state.selectedId) await showDetail(state.selectedId);
}

// ---------- 畫面 ----------

function renderSummary() {
  const current = $("#filter-status").value;
  const total = Object.values(state.meta.summary).reduce((a, b) => a + b, 0);
  const cards = [["", "全部客戶", total, "#2563eb"]].concat(
    state.meta.statuses.map((s) => [s, s, state.meta.summary[s] || 0, STATUS_COLORS[s]])
  );
  $("#summary").innerHTML = cards.map(([value, label, n, color]) => `
    <div class="card ${value === current ? "active" : ""}" data-status="${esc(value)}" style="--c:${color}">
      <div class="n">${n}</div><div class="label">${esc(label)}</div>
    </div>`).join("");
}

function renderList() {
  const rows = state.customers.map((c) => `
    <tr data-id="${c.id}" class="${c.id === state.selectedId ? "selected" : ""}">
      <td><strong>${esc(c.name)}</strong><div class="sub">${esc(c.company)}</div></td>
      <td>${esc(c.phone)}<div class="sub">${esc(c.email)}</div></td>
      <td>${badge(c.status)}</td>
      <td>${esc(c.last_contact || "—")}<div class="sub">${c.interaction_count} 筆紀錄</div></td>
    </tr>`);
  $("#customer-rows").innerHTML = rows.join("");
  $("#empty").hidden = state.customers.length > 0;
}

async function showDetail(id) {
  let customer, interactions;
  try {
    [customer, interactions] = await Promise.all([
      api("GET", `/api/customers/${id}`),
      api("GET", `/api/customers/${id}/interactions`),
    ]);
  } catch {
    state.selectedId = null;
    $("#detail").innerHTML = `<p class="empty">請從左側選擇一位客戶</p>`;
    return;
  }
  state.selectedId = id;
  renderList();

  const statusOpts = state.meta.statuses.map((s) =>
    `<option ${s === customer.status ? "selected" : ""}>${esc(s)}</option>`).join("");
  const methodOpts = state.meta.contact_methods.map((m) => `<option>${esc(m)}</option>`).join("");
  const info = [
    ["公司", customer.company], ["Email", customer.email], ["電話", customer.phone],
    ["地址", customer.address], ["備註", customer.notes],
    ["建立", customer.created_at.replace("T", " ")],
    ["更新", customer.updated_at.replace("T", " ")],
  ].filter(([, v]) => v).map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");

  const timeline = interactions.length
    ? interactions.map((i) => `
        <li>
          <div class="meta">
            <span>${esc(i.contact_date)} · ${esc(i.method)}</span>
            <button class="link" data-del-interaction="${i.id}" title="刪除">✕</button>
          </div>
          <div class="content">${esc(i.content)}</div>
        </li>`).join("")
    : `<p class="empty">尚無聯絡紀錄</p>`;

  $("#detail").innerHTML = `
    <div class="detail-head">
      <div><h2>${esc(customer.name)}</h2>${badge(customer.status)}</div>
      <div class="btns">
        <button id="btn-edit">編輯</button>
        <button id="btn-delete" class="danger">刪除</button>
      </div>
    </div>
    <dl class="info">${info}</dl>
    <label class="sub">快速變更狀態
      <select id="quick-status">${statusOpts}</select>
    </label>

    <h3>新增聯絡紀錄</h3>
    <form class="interaction-form" id="interaction-form">
      <div class="row">
        <input type="date" name="contact_date" value="${today()}" required>
        <select name="method">${methodOpts}</select>
      </div>
      <textarea name="content" rows="3" placeholder="聯絡內容…" required></textarea>
      <p class="error" id="interaction-error"></p>
      <button type="submit" class="primary">新增紀錄</button>
    </form>

    <h3>聯絡紀錄（${interactions.length}）</h3>
    <ul class="timeline">${timeline}</ul>`;
}

// ---------- 客戶表單 ----------

function openCustomerDialog(customer) {
  const form = $("#customer-form");
  form.reset();
  $("#form-error").textContent = "";
  state.editingId = customer ? customer.id : null;
  $("#dialog-title").textContent = customer ? "編輯客戶" : "新增客戶";
  form.status.innerHTML = state.meta.statuses.map((s) => `<option>${esc(s)}</option>`).join("");
  if (customer) {
    for (const f of ["name", "company", "email", "phone", "address", "status", "notes"]) {
      form[f].value = customer[f] ?? "";
    }
  }
  $("#customer-dialog").showModal();
  form.name.focus();
}

$("#customer-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  try {
    const saved = state.editingId
      ? await api("PUT", `/api/customers/${state.editingId}`, data)
      : await api("POST", "/api/customers", data);
    $("#customer-dialog").close();
    state.selectedId = saved.id;
    await refresh();
  } catch (err) {
    $("#form-error").textContent = err.message;
  }
});

$("#btn-cancel").addEventListener("click", () => $("#customer-dialog").close());
$("#btn-new").addEventListener("click", () => openCustomerDialog(null));

$("#btn-export").addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = "/api/customers/export.csv?" + customerQuery();
  link.download = "";
  link.click();
});

// ---------- 列表與篩選 ----------

let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadCustomers, 250);
});

$("#filter-status").addEventListener("change", () => {
  renderSummary();
  loadCustomers();
});

function renderSortOrder() {
  const btn = $("#sort-order");
  btn.disabled = !$("#sort-field").value;
  btn.textContent = btn.dataset.order === "asc" ? "↑ 升冪" : "↓ 降冪";
}

$("#sort-field").addEventListener("change", () => {
  renderSortOrder();
  loadCustomers();
});

$("#sort-order").addEventListener("click", (e) => {
  const btn = e.currentTarget;
  btn.dataset.order = btn.dataset.order === "asc" ? "desc" : "asc";
  renderSortOrder();
  loadCustomers();
});

$("#summary").addEventListener("click", (e) => {
  const card = e.target.closest(".card");
  if (!card) return;
  $("#filter-status").value = card.dataset.status;
  renderSummary();
  loadCustomers();
});

$("#customer-rows").addEventListener("click", (e) => {
  const row = e.target.closest("tr");
  if (row) showDetail(Number(row.dataset.id));
});

// ---------- 詳細資料面板 ----------

$("#detail").addEventListener("click", async (e) => {
  const id = state.selectedId;
  if (e.target.id === "btn-edit") {
    openCustomerDialog(await api("GET", `/api/customers/${id}`));
  } else if (e.target.id === "btn-delete") {
    const c = state.customers.find((x) => x.id === id);
    if (!confirm(`確定要刪除「${c ? c.name : "此客戶"}」？相關聯絡紀錄也會一併刪除。`)) return;
    await api("DELETE", `/api/customers/${id}`);
    state.selectedId = null;
    $("#detail").innerHTML = `<p class="empty">請從左側選擇一位客戶</p>`;
    await refresh();
  } else if (e.target.dataset.delInteraction) {
    if (!confirm("確定要刪除這筆聯絡紀錄？")) return;
    await api("DELETE", `/api/interactions/${e.target.dataset.delInteraction}`);
    await refresh();
  }
});

$("#detail").addEventListener("change", async (e) => {
  if (e.target.id !== "quick-status") return;
  await api("PUT", `/api/customers/${state.selectedId}`, { status: e.target.value });
  await refresh();
});

$("#detail").addEventListener("submit", async (e) => {
  if (e.target.id !== "interaction-form") return;
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  try {
    await api("POST", `/api/customers/${state.selectedId}/interactions`, data);
    await refresh();
  } catch (err) {
    $("#interaction-error").textContent = err.message;
  }
});

// ---------- 初始化 ----------

(async function init() {
  await loadMeta();
  $("#filter-status").innerHTML += state.meta.statuses
    .map((s) => `<option>${esc(s)}</option>`).join("");
  await loadCustomers();
})();

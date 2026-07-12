import { fetchClass, fetchEnrollment, sendChat, escapeHtml, drawRadar } from "/static/js/api.js";

const classId = document.body.dataset.classId;
const radarRef = {};
const state = { classData: null, studentId: null, moduleId: null, enrollment: null };

// DOM要素をキャッシュ（ページ読み込み後に確実に取得）
const loginScreen = document.getElementById("login-screen");
const cockpitScreen = document.getElementById("cockpit-screen");
const studentList = document.getElementById("login-student-list");

init();

async function init() {
  state.classData = await fetchClass(classId);
  document.getElementById("class-name").textContent = state.classData.class_name;
  showLoginScreen(state.classData.roster || []);
}

// ---------- ログイン画面の表示 ----------
function showLoginScreen(roster) {
  loginScreen.classList.add("active"); // クラスを明示的に付与
  loginScreen.classList.remove("hidden");
  cockpitScreen.classList.add("hidden");

  if (roster.length === 0) {
    studentList.innerHTML = `<li class="empty-row">生徒が登録されていません。</li>`;
    return;
  }
  
  studentList.innerHTML = roster
    .map((s) => `<li class="login-row" data-id="${s.student_id}">${s.display_name}</li>`)
    .join("");

  // イベント委譲でクリックを確実に拾う
  studentList.addEventListener("click", (e) => {
    const row = e.target.closest(".login-row");
    if (row) enterCockpit(row.dataset.id, row.textContent);
  }, { once: true }); // 1回クリックされたら外す
}

// ---------- コクピットへの遷移 ----------
async function enterCockpit(studentId, displayName) {
  state.studentId = studentId;
  state.enrollment = await fetchEnrollment(classId, studentId);

  const modules = state.classData.modules || [];
  state.moduleId = modules.length > 0 ? modules[0].module_id : null;

  loginScreen.classList.remove("active", "hidden");
  loginScreen.classList.add("hidden");
  cockpitScreen.classList.remove("hidden");
  
  document.getElementById("student-display-name").textContent = displayName;
  renderAll();
}

// ---------- 共通描画管理 ----------
function renderAll() {
  renderModuleList();
  renderChat();
  renderStatus();
}

// ---------- 章リスト（イベント委譲で最適化） ----------
const moduleListContainer = document.getElementById("module-list");
moduleListContainer.addEventListener("click", (e) => {
  const row = e.target.closest(".module-row");
  if (!row) return;
  state.moduleId = row.dataset.moduleId;
  renderAll();
});

function renderModuleList() {
  const modules = state.classData.modules || []; // 宣言はここだけ
  if (modules.length === 0) {
    moduleListContainer.innerHTML = `<li class="empty-row">章がありません。</li>`;
    return;
  }
  
  moduleListContainer.innerHTML = modules
    .map((m, idx) => {
      const progress = (state.enrollment?.modules || {})[m.module_id];
      const passed = progress?.is_passed;
      return `
      <li class="module-row ${m.module_id === state.moduleId ? "active" : ""}" data-module-id="${m.module_id}">
        <span class="module-number">${String(idx + 1).padStart(2, "0")}</span>
        <span>${m.title}</span>
        ${passed ? '<span class="module-passed-dot">🟢</span>' : ""}
      </li>`;
    })
    .join("");
}

function currentModuleInfo() {
  return (state.classData.modules || []).find((m) => m.module_id === state.moduleId);
}

// ---------- チャット ----------
function renderChat() {
  const modInfo = currentModuleInfo();
  document.getElementById("module-goal").textContent = modInfo ? `目標: ${modInfo.target_goal}` : "";

  const progress = (state.enrollment?.modules || {})[state.moduleId] || {};
  const history = progress.chat_history || [];
  const win = document.getElementById("chat-window");

  if (history.length === 0) {
    win.innerHTML = `<div class="chat-bubble assistant">こんにちは。「${modInfo?.title || ""}」について、自分の言葉で説明してもらえますか？</div>`;
  } else {
    win.innerHTML = history
      .map((m) => `<div class="chat-bubble ${m.role === "user" ? "user" : "assistant"}">${escapeHtml(m.content)}</div>`)
      .join("");
  }
  win.scrollTop = win.scrollHeight;

  const input = document.getElementById("chat-input");
  input.disabled = !!progress.is_passed;
  input.placeholder = progress.is_passed ? "この章は合格済みです" : "自分の言葉で説明してみよう...";
}

// ---------- 能力査定 ----------
function renderStatus() {
  const modInfo = currentModuleInfo();
  const progress = (state.enrollment?.modules || {})[state.moduleId] || {};
  const status = progress.current_status || { knowledge_level: 1, thinking_level: 1, application_level: 1 };
  const criteria = modInfo?.passing_criteria || { knowledge_level: 4, thinking_level: 4, application_level: 3 };

  const badge = document.getElementById("status-badge");
  if (progress.is_passed) {
    badge.className = "status-badge passed";
    badge.textContent = "🟢 合格済み。次の章に進みましょう。";
  } else {
    badge.className = "status-badge progress";
    badge.textContent = "🟡 対話面接中です。";
  }

  const gaugeList = document.getElementById("gauge-list");
  const axes = [
    ["知識 Knowledge", status.knowledge_level, criteria.knowledge_level],
    ["思考 Thinking", status.thinking_level, criteria.thinking_level],
    ["応用 Application", status.application_level, criteria.application_level],
  ];
  gaugeList.innerHTML = axes
    .map(([label, val, target]) => `
    <div>
      <div class="gauge-label"><span>${label}</span><span>Lv.${val} / ${target}</span></div>
      <div class="gauge-track"><div class="gauge-fill" style="width:${Math.min((val / 5) * 100, 100)}%"></div></div>
    </div>`).join("");

  drawRadar(document.getElementById("student-radar"), radarRef,
    [status.knowledge_level, status.thinking_level, status.application_level],
    [criteria.knowledge_level, criteria.thinking_level, criteria.application_level]
  );
}

document.getElementById("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message || !state.moduleId || !state.studentId) return;
  input.value = "";
  input.disabled = true;

  const modules = (state.enrollment.modules ||= {});
  modules[state.moduleId] ||= { chat_history: [], current_status: { knowledge_level: 1, thinking_level: 1, application_level: 1 } };
  modules[state.moduleId].chat_history.push({ role: "user", content: message });
  renderChat();

  const toast = document.getElementById("toast");
  try {
    const result = await sendChat(classId, state.studentId, state.moduleId, message);
    modules[state.moduleId].chat_history = result.chat_history;
    modules[state.moduleId].current_status = result.current_status;
    modules[state.moduleId].is_passed = result.is_passed;
    renderAll();
    if (result.is_passed_now) celebrate();
  } catch (err) {
    showToast(toast, err.message);
  } finally {
    input.disabled = !!modules[state.moduleId]?.is_passed;
  }
});

function showToast(toast, message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3500);
}

function celebrate() {
  const layer = document.getElementById("confetti-layer");
  layer.innerHTML = "";
  for (let i = 0; i < 24; i++) {
    const piece = document.createElement("span");
    piece.className = "confetti-piece";
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.animationDelay = `${Math.random() * 0.4}s`;
    layer.appendChild(piece);
  }
  setTimeout(() => (layer.innerHTML = ""), 2200);
}
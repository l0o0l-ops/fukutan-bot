import {
  fetchClass,
  fetchEnrollment,
  sendChat,
  escapeHtml,
  drawRadar,
} from "/static/js/api.js";

const classId = document.body.dataset.classId;
const radarRef = {};
const state = {
  classData: null,
  studentId: null,
  moduleId: null,
  enrollment: null,
};

init();

async function init() {
  state.classData = await fetchClass(classId);
  document.getElementById("class-name").textContent =
    state.classData.class_name;

  const roster = state.classData.roster || [];
  if (roster.length === 0) {
    showLoginScreen(roster);
    return;
  }
  showLoginScreen(roster);
}

// ---------- ログイン画面（「あなたは誰ですか？」） ----------
function showLoginScreen(roster) {
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("cockpit-screen").classList.add("hidden");

  const list = document.getElementById("login-student-list");
  if (roster.length === 0) {
    list.innerHTML = `<li class="empty-row">このクラスにはまだ生徒が登録されていません。先生に追加を依頼してください。</li>`;
    return;
  }
  list.innerHTML = roster
    .map(
      (s) =>
        `<li class="login-row" data-id="${s.student_id}">${s.display_name}</li>`,
    )
    .join("");

  list.querySelectorAll(".login-row").forEach((row) => {
    row.addEventListener("click", () =>
      enterCockpit(row.dataset.id, row.textContent),
    );
  });
}

async function enterCockpit(studentId, displayName) {
  state.studentId = studentId;
  state.enrollment = await fetchEnrollment(classId, studentId);

  const modules = state.classData.modules || [];
  state.moduleId = modules.length > 0 ? modules[0].module_id : null;

  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("cockpit-screen").classList.remove("hidden");
  document.getElementById("cockpit-screen").classList.add("active");  
  document.getElementById("student-display-name").textContent = displayName;

  renderModuleList();
  renderChat();
  renderStatus();
}

const switchBtn = document.getElementById("switch-student-btn");
if (switchBtn) {
  switchBtn.addEventListener("click", () => {
    state.studentId = null;
    showLoginScreen(state.classData.roster || []);
  });
}

// ---------- 章リスト ----------
function renderModuleList() {
  const list = document.getElementById("module-list");
  const modules = state.classData.modules || [];
  if (modules.length === 0) {
    list.innerHTML = `<li class="empty-row">章がまだありません。先生に追加を依頼してください。</li>`;
    return;
  }
  list.innerHTML = modules
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

  list.querySelectorAll(".module-row").forEach((row) => {
    row.addEventListener("click", () => {
      state.moduleId = row.dataset.moduleId;
      renderModuleList();
      renderChat();
      renderStatus();
    });
  });
}

function currentModuleInfo() {
  return (state.classData.modules || []).find(
    (m) => m.module_id === state.moduleId,
  );
}

// ---------- チャット ----------
function renderChat() {
  const modInfo = currentModuleInfo();
  document.getElementById("module-goal").textContent = modInfo
    ? `目標: ${modInfo.target_goal}`
    : "";

  const progress = (state.enrollment?.modules || {})[state.moduleId] || {};
  const history = progress.chat_history || [];
  const win = document.getElementById("chat-window");

  if (history.length === 0) {
    win.innerHTML = `<div class="chat-bubble assistant">こんにちは。「${modInfo?.title || ""}」について、自分の言葉で説明してもらえますか？</div>`;
  } else {
    win.innerHTML = history
      .map(
        (m) =>
          `<div class="chat-bubble ${m.role === "user" ? "user" : "assistant"}">${escapeHtml(m.content)}</div>`,
      )
      .join("");
  }
  win.scrollTop = win.scrollHeight;

  const input = document.getElementById("chat-input");
  input.disabled = !!progress.is_passed;
  input.placeholder = progress.is_passed
    ? "この章は合格済みです"
    : "自分の言葉で説明してみよう...";
}

function renderStatus() {
  const modInfo = currentModuleInfo();
  const progress = (state.enrollment?.modules || {})[state.moduleId] || {};
  const status = progress.current_status || {
    knowledge_level: 1,
    thinking_level: 1,
    application_level: 1,
  };
  const criteria = modInfo?.passing_criteria || {
    knowledge_level: 4,
    thinking_level: 4,
    application_level: 3,
  };

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
    .map(
      ([label, val, target]) => `
    <div>
      <div class="gauge-label"><span>${label}</span><span>Lv.${val} / ${target}</span></div>
      <div class="gauge-track"><div class="gauge-fill" style="width:${Math.min((val / 5) * 100, 100)}%"></div></div>
    </div>`,
    )
    .join("");

  drawRadar(
    document.getElementById("student-radar"),
    radarRef,
    [status.knowledge_level, status.thinking_level, status.application_level],
    [
      criteria.knowledge_level,
      criteria.thinking_level,
      criteria.application_level,
    ],
  );
}

const chatForm = document.getElementById("chat-form");
if (chatForm) {
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const message = input.value.trim();
    if (!message || !state.moduleId || !state.studentId) return;
    input.value = "";
    input.disabled = true;

    const modules = (state.enrollment.modules ||= {});
    modules[state.moduleId] ||= {
      chat_history: [],
      current_status: {
        knowledge_level: 1,
        thinking_level: 1,
        application_level: 1,
      },
    };
    modules[state.moduleId].chat_history.push({
      role: "user",
      content: message,
    });
    renderChat();

    const toast = document.getElementById("toast");
    try {
      const result = await sendChat(
        classId,
        state.studentId,
        state.moduleId,
        message,
      );
      modules[state.moduleId].chat_history = result.chat_history;
      modules[state.moduleId].current_status = result.current_status;
      modules[state.moduleId].is_passed = result.is_passed;
      modules[state.moduleId].growth_report = result.growth_report;
      modules[state.moduleId].action_plan = result.action_plan;
      renderChat();
      renderStatus();
      if (result.is_passed_now) {
        document.getElementById("status-badge").textContent =
          "🎉 合格！おめでとうございます。次の章に進めます。";
        celebrate();
      }
    } catch (err) {
      showToast(toast, err.message);
    } finally {
      input.disabled = !!modules[state.moduleId]?.is_passed;
    }
  });
}

function showToast(toast, message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3500);
}

function celebrate() {
  const layer = document.getElementById("confetti-layer");
  layer.innerHTML = "";
  const colors = ["#d98e33", "#f3d9ab", "#4f9d69", "#12182b"];
  for (let i = 0; i < 24; i++) {
    const piece = document.createElement("span");
    piece.className = "confetti-piece";
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.background = colors[i % colors.length];
    piece.style.animationDelay = `${Math.random() * 0.4}s`;
    layer.appendChild(piece);
  }
  setTimeout(() => (layer.innerHTML = ""), 2200);
}

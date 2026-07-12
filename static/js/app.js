// URLパラメータからクラスIDを動的に取得して本番APIと通信する心臓部
const urlParams = new URLSearchParams(window.location.search);
const classId = urlParams.get('class_id') || 'class_001';
document.body.dataset.classId = classId;

// API通信ヘルパー群
async function fetchClass(cId) { return (await fetch(`/api/classes/${cId}`)).json(); }
async function fetchEnrollment(cId, sId) { return (await fetch(`/api/classes/${cId}/students/${sId}/enrollment`)).json(); }
async function sendChat(cId, sId, mId, msg) {
    const body = new URLSearchParams({ class_id: cId, student_id: sId, module_id: mId, message: msg });
    return (await fetch("/api/chat", { method: "POST", body })).json();
}

if (classId) { initClassPage(classId); }

async function initClassPage(classId) {
  const state = { classData: null, activeModuleId: null, activeStudentId: null, enrollment: null, studentRadar: null };

  async function loadClassData() {
    state.classData = await fetchClass(classId);
    document.getElementById("class-name").textContent = `[ ${state.classData.class_name} ]`;
  }

  function renderStudentSelect() {
    const select = document.getElementById("student-select");
    const roster = state.classData.roster || [];
    if (roster.length === 0) {
      document.getElementById("student-empty").classList.remove("hidden");
      document.getElementById("student-body").classList.add("hidden");
      return;
    }
    document.getElementById("student-empty").classList.add("hidden");
    document.getElementById("student-body").classList.remove("hidden");

    select.innerHTML = roster.map((s) => `<option value="${s.student_id}">${s.display_name}</option>`).join("");
    select.onchange = () => switchStudent(select.value);
    if (!state.activeStudentId) state.activeStudentId = roster[0].student_id;
    select.value = state.activeStudentId;
  }

  async function switchStudent(studentId) {
    state.activeStudentId = studentId;
    state.enrollment = await fetchEnrollment(classId, studentId);
    const modules = state.classData.modules || [];
    if (modules.length > 0 && !state.activeModuleId) state.activeModuleId = modules[0].module_id;
    renderModuleList();
    renderChat();
    renderStatus();
  }

  function renderModuleList() {
    const list = document.getElementById("module-list");
    const modules = state.classData.modules || [];
    if (modules.length === 0) {
      list.innerHTML = `<li style="padding:20px; color:var(--text-muted)">章がありません。教授画面から作成してください。</li>`;
      return;
    }
    list.innerHTML = modules.map((m, idx) => {
        const progress = (state.enrollment?.modules || {})[m.module_id] || {};
        return `<li class="module-row ${m.module_id === state.activeModuleId ? 'active' : ''}" data-module-id="${m.module_id}">
          <span>${String(idx+1).padStart(2,'0')}. ${m.title}</span>
          ${progress.is_passed ? '<span>🟢</span>' : ''}
        </li>`;
    }).join("");

    list.querySelectorAll(".module-row").forEach(row => {
      row.addEventListener("click", () => {
        state.activeModuleId = row.dataset.moduleId;
        renderModuleList(); renderChat(); renderStatus();
      });
    });
  }

  function renderChat() {
    const modInfo = (state.classData.modules || []).find(m => m.module_id === state.activeModuleId);
    document.getElementById("module-goal").textContent = modInfo ? `🎯 目標: ${modInfo.target_goal}` : "";
    const progress = (state.enrollment?.modules || {})[state.activeModuleId] || {};
    const history = progress.chat_history || [];
    const window_ = document.getElementById("chat-window");

    if (history.length === 0) {
      window_.innerHTML = `<div class="chat-bubble assistant">こんにちは！「${modInfo?.title || ''}」について君自身の言葉で説明できるかな？</div>`;
    } else {
      window_.innerHTML = history.map(m => `<div class="chat-bubble ${m.role === 'user' ? 'user' : 'assistant'}">${m.content}</div>`).join("");
    }
    window_.scrollTop = window_.scrollHeight;
    
    const input = document.getElementById("chat-input");
    input.disabled = !!progress.is_passed;
    input.placeholder = progress.is_passed ? "🟢 この章はクリア条件を満たしました！" : "自分の言葉で説明してみよう...";
  }

  function renderStatus() {
    const modInfo = (state.classData.modules || []).find(m => m.module_id === state.activeModuleId);
    const progress = (state.enrollment?.modules || {})[state.activeModuleId] || {};
    const status = progress.current_status || { knowledge_level: 1, thinking_level: 1, application_level: 1 };
    const criteria = modInfo?.passing_criteria || { knowledge_level: 4, thinking_level: 4, application_level: 3 };

    const badge = document.getElementById("status-badge");
    if (progress.is_passed) {
      badge.className = "status-badge passed"; badge.textContent = "🟢 合格済み。次の章へ進めます！";
    } else {
      badge.className = "status-badge progress"; badge.textContent = "🟡 AI審査員によるリアルタイム能力対話中";
    }

    const axes = [["知識 Knowledge", status.knowledge_level, criteria.knowledge_level], ["思考 Thinking", status.thinking_level, criteria.thinking_level], ["応用 Application", status.application_level, criteria.application_level]];
    document.getElementById("gauge-list").innerHTML = axes.map(([label, val, target]) => `
      <div>
        <div class="gauge-label"><span>${label}</span><span>Lv.${val} / ${target}</span></div>
        <div class="gauge-track"><div class="gauge-fill" style="width:${(val/5)*100}%"></div></div>
      </div>`).join("");

    drawRadar("student-radar", "studentRadar", state, [status.knowledge_level, status.thinking_level, status.application_level], [criteria.knowledge_level, criteria.thinking_level, criteria.application_level]);
  }

  document.getElementById("chat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const msg = input.value.trim();
    if (!msg || !state.activeModuleId || !state.activeStudentId) return;
    input.value = ""; input.disabled = true;

    try {
      const result = await sendChat(classId, state.activeStudentId, state.activeModuleId, msg);
      state.enrollment.modules[state.activeModuleId] = result;
      renderChat(); renderStatus();
      if (result.is_passed_now) { alert("🎉 おめでとうございます！章の合格基準をクリアしました！"); }
    } catch (err) { alert(err.message); }
    finally { input.disabled = !!state.enrollment.modules[state.activeModuleId]?.is_passed; }
  });

  function drawRadar(canvasId, stateKey, state, current, target) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (state[stateKey]) {
      state[stateKey].data.datasets[0].data = current;
      state[stateKey].data.datasets[1].data = target;
      state[stateKey].update(); return;
    }
    Chart.defaults.font.family = "'Space Grotesk', sans-serif";
    Chart.defaults.color = '#9ca3af';
    state[stateKey] = new Chart(canvas.getContext("2d"), {
      type: "radar",
      data: {
        labels: ["知識", "思考", "応用"],
        datasets: [
          { label: "現在地", data: current, borderColor: "#f59e0b", backgroundColor: "rgba(245, 158, 11, 0.25)", borderWidth: 2 },
          { label: "合格目標", data: target, borderColor: "#2a2d36", backgroundColor: "transparent", borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { r: { min: 0, max: 5, ticks: { stepSize: 1, display: false }, grid: { color: '#2a2d36' }, angleLines: { color: '#2a2d36' } } }
      }
    });
  }

  await loadClassData(); renderStudentSelect();
  if (state.classData.roster?.length > 0) { await switchStudent(state.classData.roster[0].student_id); }
}
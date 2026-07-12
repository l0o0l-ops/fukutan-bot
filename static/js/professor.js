import {
  fetchClass,
  addStudent,
  deleteStudent,
  deleteModule,
  uploadPdfModule,
  fetchProfessorView,
  drawRadar,
} from "/static/js/api.js";

const classId = document.body.dataset.classId;
const radarRef = {};
const state = { classData: null, professorStudentId: null };

init();

async function init() {
  await loadClassData();
  await renderAll();
}

async function loadClassData() {
  state.classData = await fetchClass(classId);
  document.getElementById("class-name").textContent = state.classData.class_name;
}

// ---------- 生徒追加・削除 ----------
document.getElementById("add-student-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("new-student-name");
  if (!input.value.trim()) return;
  await addStudent(classId, input.value.trim());
  input.value = "";
  await loadClassData();
  await renderAll();
});

// ---------- PDFアップロード ----------
document.getElementById("pdf-upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById("pdf-input");
  const statusEl = document.getElementById("pdf-status");
  const submitBtn = document.getElementById("pdf-submit-btn");
  if (!fileInput.files[0]) return;

  statusEl.textContent = "";
  submitBtn.disabled = true;
  submitBtn.classList.add("is-loading");
  submitBtn.textContent = "AIが解析中...";
  try {
    const newModule = await uploadPdfModule(classId, fileInput.files[0]);
    await loadClassData();
    await renderAll();
    e.target.reset();
    statusEl.style.color = "var(--good)";
    statusEl.textContent = `「${newModule.title}」を追加しました。`;
  } catch (err) {
    statusEl.style.color = "#c0392b";
    statusEl.textContent = err.message;
  } finally {
    submitBtn.disabled = false;
    submitBtn.classList.remove("is-loading");
    submitBtn.textContent = "PDFからAIに章を設計させる";
  }
});

// ---------- メイン描画 ----------
async function renderAll() {
  const data = await fetchProfessorView(classId);
  const modules = data.modules || [];
  const students = data.students || [];

  renderStudentList(students);
  renderModuleManageList(modules);
  renderModuleSelect(modules);

  if (!state.professorStudentId && students.length > 0) state.professorStudentId = students[0].student_id;
  renderReport(data);
}

function renderStudentList(students) {
  const list = document.getElementById("professor-student-list");
  if (students.length === 0) {
    list.innerHTML = `<li class="empty-row">生徒がまだいません。上のフォームから追加してください。</li>`;
    return;
  }
  list.innerHTML = students
    .map(
      (s) => `
    <li class="module-row ${s.student_id === state.professorStudentId ? "active" : ""}" data-student-id="${s.student_id}">
      <span style="flex:1">${s.display_name}</span>
      <button class="btn-icon" data-remove-student="${s.student_id}" title="削除" aria-label="削除">🗑</button>
    </li>`
    )
    .join("");

  list.querySelectorAll("[data-student-id]").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("[data-remove-student]")) return;
      state.professorStudentId = row.dataset.studentId;
      renderAll();
    });
  });
  list.querySelectorAll("[data-remove-student]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("この生徒を削除しますか？対話履歴も削除されます。")) return;
      await deleteStudent(classId, btn.dataset.removeStudent);
      if (state.professorStudentId === btn.dataset.removeStudent) state.professorStudentId = null;
      await renderAll();
    });
  });
}

function renderModuleManageList(modules) {
  const list = document.getElementById("module-manage-list");
  if (modules.length === 0) {
    list.innerHTML = `<li class="empty-row">章がまだありません。下からPDFをアップロードしてください。</li>`;
    return;
  }
  list.innerHTML = modules
    .map(
      (m, idx) => `
    <li class="module-row" style="cursor:default;">
      <span class="module-number">${String(idx + 1).padStart(2, "0")}</span>
      <span style="flex:1">${m.title}</span>
      <button class="btn-icon" data-delete-module="${m.module_id}" title="削除" aria-label="削除">🗑</button>
    </li>`
    )
    .join("");

  list.querySelectorAll("[data-delete-module]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("この章を削除しますか？")) return;
      await deleteModule(classId, btn.dataset.deleteModule);
      await loadClassData();
      await renderAll();
    });
  });
}

function renderModuleSelect(modules) {
  const select = document.getElementById("professor-module-select");
  const prevValue = select.value;
  select.innerHTML =
    `<option value="__overall__">総合俯瞰評価</option>` +
    modules.map((m) => `<option value="${m.module_id}">${m.title}</option>`).join("");
  if (prevValue && [...select.options].some((o) => o.value === prevValue)) select.value = prevValue;
  select.onchange = () => fetchProfessorView(classId).then(renderReport);
}

function renderReport(data) {
  const modules = data.modules || [];
  const student = (data.students || []).find((s) => s.student_id === state.professorStudentId);
  const select = document.getElementById("professor-module-select");
  const selected = select.value || "__overall__";

  const scoresLine = document.getElementById("scores-line");
  const growthEl = document.getElementById("growth-report");
  const actionEl = document.getElementById("action-plan");
  const nameEl = document.getElementById("report-student-name");

  if (!student) {
    nameEl.textContent = "生徒を選択してください";
    scoresLine.textContent = "";
    growthEl.value = "";
    actionEl.value = "";
    drawRadar(document.getElementById("professor-radar"), radarRef, [1, 1, 1], [4, 4, 3]);
    return;
  }

  nameEl.textContent = student.display_name;
  const enrollmentModules = student.enrollment.modules || {};

  if (selected === "__overall__") {
    const entries = Object.values(enrollmentModules);
    if (entries.length === 0) {
      scoresLine.textContent = "まだ対話データがありません。";
      drawRadar(document.getElementById("professor-radar"), radarRef, [1, 1, 1], [4, 4, 3]);
    } else {
      const avg = (key) => entries.reduce((sum, e) => sum + (e.current_status?.[key] || 1), 0) / entries.length;
      const targetAvg = (key) => modules.reduce((sum, m) => sum + (m.passing_criteria?.[key] || 4), 0) / (modules.length || 1);
      const current = [avg("knowledge_level"), avg("thinking_level"), avg("application_level")];
      const target = [targetAvg("knowledge_level"), targetAvg("thinking_level"), targetAvg("application_level")];
      scoresLine.textContent = `全モジュール平均 — 知識:${current[0].toFixed(1)} / 思考:${current[1].toFixed(1)} / 応用:${current[2].toFixed(1)}`;
      drawRadar(document.getElementById("professor-radar"), radarRef, current, target);
    }
    growthEl.value = student.enrollment.overall_report || "対話が始まると分析が生成されます。";
    actionEl.value = student.enrollment.overall_action_plan || "";
  } else {
    const modInfo = modules.find((m) => m.module_id === selected);
    const progress = enrollmentModules[selected] || {};
    const status = progress.current_status || { knowledge_level: 1, thinking_level: 1, application_level: 1 };
    const criteria = modInfo?.passing_criteria || { knowledge_level: 4, thinking_level: 4, application_level: 3 };

    scoresLine.textContent = `知識:Lv.${status.knowledge_level}/${criteria.knowledge_level}  思考:Lv.${status.thinking_level}/${criteria.thinking_level}  応用:Lv.${status.application_level}/${criteria.application_level}`;
    drawRadar(
      document.getElementById("professor-radar"),
      radarRef,
      [status.knowledge_level, status.thinking_level, status.application_level],
      [criteria.knowledge_level, criteria.thinking_level, criteria.application_level]
    );
    growthEl.value = progress.growth_report || "現在対話を進めています。";
    actionEl.value = progress.action_plan || "";
  }
}


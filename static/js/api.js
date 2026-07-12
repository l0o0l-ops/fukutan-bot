// ==========================================
// 共通APIヘルパー（index.html / class_select.html / student.js / professor.js から利用）
// ==========================================

export async function fetchClasses() {
  const res = await fetch("/api/classes");
  if (!res.ok) throw new Error("授業一覧の取得に失敗しました");
  return res.json();
}

export async function createClass(className) {
  const body = new URLSearchParams({ class_name: className });
  const res = await fetch("/api/classes", { method: "POST", body });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "作成に失敗しました");
  }
  return res.json();
}

export async function fetchClass(classId) {
  const res = await fetch(`/api/classes/${classId}`);
  if (!res.ok) throw new Error("授業データの取得に失敗しました");
  return res.json();
}

export async function addStudent(classId, displayName) {
  const body = new URLSearchParams({ display_name: displayName });
  const res = await fetch(`/api/classes/${classId}/students`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "生徒の追加に失敗しました");
  }
  return res.json();
}

export async function deleteStudent(classId, studentId) {
  const res = await fetch(`/api/classes/${classId}/students/${studentId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("削除に失敗しました");
  return res.json();
}

export async function deleteModule(classId, moduleId) {
  const res = await fetch(`/api/classes/${classId}/modules/${moduleId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("削除に失敗しました");
  return res.json();
}

export async function uploadPdfModule(classId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`/api/classes/${classId}/modules/from-pdf`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "章の生成に失敗しました");
  }
  return res.json();
}

export async function fetchEnrollment(classId, studentId) {
  const res = await fetch(
    `/api/classes/${classId}/students/${studentId}/enrollment`,
  );
  if (!res.ok) throw new Error("履修データの取得に失敗しました");
  return res.json();
}

export async function sendChat(classId, studentId, moduleId, message) {
  const body = new URLSearchParams({
    class_id: classId,
    student_id: studentId,
    module_id: moduleId,
    message,
  });
  const res = await fetch("/api/chat", { method: "POST", body });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "AIとの通信に失敗しました");
  }
  return res.json();
}

export async function fetchProfessorView(classId) {
  const res = await fetch(`/api/classes/${classId}/professor-view`);
  if (!res.ok) throw new Error("教授用データの取得に失敗しました");
  return res.json();
}

export function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// レーダーチャート（Chart.jsをラップ、student.js / professor.js 両方から使う）
export function drawRadar(canvasEl, chartRefHolder, current, target) {
  if (chartRefHolder.chart) {
    chartRefHolder.chart.data.datasets[0].data = current;
    chartRefHolder.chart.data.datasets[1].data = target;
    chartRefHolder.chart.update();
    return;
  }
  chartRefHolder.chart = new Chart(canvasEl.getContext("2d"), {
    type: "radar",
    data: {
      labels: ["知識", "思考", "応用"],
      datasets: [
        {
          label: "現在地",
          data: current,
          borderColor: "#d98e33",
          backgroundColor: "rgba(217, 142, 51, 0.25)",
          borderWidth: 2,
        },
        {
          label: "目標",
          data: target,
          borderColor: "#12182b",
          backgroundColor: "transparent",
          borderDash: [4, 4],
          borderWidth: 1.5,
          pointRadius: 0,
        },
      ],
    },
    options: {
      scales: { r: { min: 0, max: 5, ticks: { stepSize: 1 } } },
      plugins: {
        legend: {
          position: "bottom",
          labels: { font: { family: "Inter", size: 11 } },
        },
      },
    },
  });
}

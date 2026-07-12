const urlParams = new URLSearchParams(window.location.search);
const classId = urlParams.get('class_id') || 'class_001';

document.addEventListener('DOMContentLoaded', async () => {
    const targetSelector = document.getElementById('target-selector');
    const panelContainer = document.getElementById('panel-container');
    const state = {};

    const res = await fetch(`/api/classes/${classId}/professor-view`);
    const data = await res.json();

    // 1. メニュー生成
    data.students.forEach(s => {
        const li = document.createElement('li');
        li.className = 'target-item';
        li.dataset.target = `panel-${s.student_id}`;
        li.textContent = `👨‍🎓 ${s.display_name}`;
        targetSelector.appendChild(li);

        // 2. コンテンツパネル生成
        const pnl = document.createElement('div');
        pnl.id = `panel-${s.student_id}`;
        pnl.className = 'content-panel';
        pnl.innerHTML = `
            <h2>${s.display_name}さんのカルテ</h2>
            <div style="height: 200px;"><canvas id="radar-${s.student_id}"></canvas></div>
            <p><strong>成長日報:</strong> ${s.enrollment.overall_report || "データなし"}</p>
        `;
        panelContainer.appendChild(pnl);
    });

    // 3. クリックイベント割り当て
    document.querySelectorAll('.target-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.target-item').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.content-panel').forEach(p => p.classList.remove('active'));
            item.classList.add('active');
            document.getElementById(item.dataset.target).classList.add('active');
        });
    });

    // 4. チャート描画
    drawRadar("overall-radar", "overall", state, [3,3,3], [4,4,3]);
    data.students.forEach(s => {
        const stats = s.enrollment.modules ? Object.values(s.enrollment.modules)[0]?.current_status : {knowledge_level:1, thinking_level:1, application_level:1};
        drawRadar(`radar-${s.student_id}`, s.student_id, state, [stats.knowledge_level, stats.thinking_level, stats.application_level], [4,4,3]);
    });
});

function drawRadar(canvasId, key, state, current, target) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    state[key] = new Chart(canvas.getContext("2d"), {
        type: "radar",
        data: {
            labels: ["知識", "思考", "応用"],
            datasets: [{label: "現在", data: current, borderColor: "#f59e0b"}, {label: "目標", data: target, borderColor: "#2a2d36"}]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
}
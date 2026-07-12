const urlParams = new URLSearchParams(window.location.search);
const currentClassId = urlParams.get('class_id') || 'class_001';

document.addEventListener('DOMContentLoaded', () => {
    
    // === 1. 左メニューの切り替えロジック ===
    const targetItems = document.querySelectorAll('.target-item');
    const contentPanels = document.querySelectorAll('.content-panel');

    targetItems.forEach(item => {
        item.addEventListener('click', () => {
            // 選択状態のリセット
            targetItems.forEach(t => t.classList.remove('active'));
            contentPanels.forEach(p => p.classList.remove('active'));

            // クリックされたものをアクティブに
            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // === 2. レーダーチャートの初期描画（モックデータ） ===
    // ※先ほど提示していただいたChart.jsのラッパー関数を想定
    const state = {}; 

    // クラス全体の平均チャート
    drawRadar("overall-radar", "overallRadar", state, [3.2, 2.8, 3.5], [4, 4, 3]);
    
    // 生徒ごとの個別チャート
    drawRadar("student-1-radar", "student1Radar", state, [4, 4, 3], [4, 4, 3]);
    drawRadar("student-2-radar", "student2Radar", state, [2, 1, 1], [4, 4, 3]);

});

// ==========================================
// レーダーチャート描画関数 (先ほどのものをそのまま流用)
// ==========================================
function drawRadar(canvasId, stateKey, state, current, target) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
  
    if (state[stateKey]) {
      state[stateKey].data.datasets[0].data = current;
      state[stateKey].data.datasets[1].data = target;
      state[stateKey].update();
      return;
    }
  
    Chart.defaults.font.family = "'Space Grotesk', sans-serif";
    Chart.defaults.color = '#9ca3af';
  
    state[stateKey] = new Chart(canvas.getContext("2d"), {
      type: "radar",
      data: {
        labels: ["知識", "思考", "応用"],
        datasets: [
          {
            label: "現在地 / 現在の平均",
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
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 800, easing: 'easeOutQuart' },
        scales: { 
            r: { 
                min: 0, max: 5, ticks: { stepSize: 1, display: false },
                grid: { color: '#2a2d36' }, angleLines: { color: '#2a2d36' },
                pointLabels: { font: { size: 12, family: "Inter" }, color: '#f3f4f6' }
            } 
        },
        plugins: { legend: { position: "bottom" } },
      },
    });
}
const urlParams = new URLSearchParams(window.location.search);
const currentClassId = urlParams.get('class_id') || 'class_001';

document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // 1. Chart.js (レーダーチャート) の初期化
    // ==========================================
    const ctx = document.getElementById('radarChart').getContext('2d');
    
    // Space Groteskフォントをデフォルトに
    Chart.defaults.font.family = "'Space Grotesk', sans-serif";
    Chart.defaults.color = '#9ca3af'; // muted text

    const radarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Knowledge', 'Thinking', 'Application'],
            datasets: [
                {
                    label: 'Target Goal',
                    data: [4, 4, 3], // 目標値
                    borderColor: 'rgba(245, 158, 11, 0.4)', // 控えめなアンバー
                    backgroundColor: 'rgba(0, 0, 0, 0)',
                    borderDash: [5, 5],
                    borderWidth: 2,
                    pointRadius: 0
                },
                {
                    label: 'Current Status',
                    data: [1, 1, 1], // 初期値
                    borderColor: '#3b82f6', // ブルー系
                    backgroundColor: 'rgba(59, 130, 246, 0.2)',
                    borderWidth: 2,
                    pointBackgroundColor: '#3b82f6',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    min: 0,
                    max: 5,
                    ticks: { stepSize: 1, display: false },
                    grid: { color: '#2a2d36' },
                    angleLines: { color: '#2a2d36' },
                    pointLabels: {
                        font: { size: 14, weight: 'bold' },
                        color: '#f3f4f6'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#9ca3af' }
                }
            },
            animation: {
                duration: 800,
                easing: 'easeOutQuart'
            }
        }
    });

    // ==========================================
    // 2. チャット通信処理 (Fetch API)
    // ==========================================
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatBox = document.getElementById('chat-box');

    function appendMessage(role, text) {
        const div = document.createElement('div');
        div.className = `chat-bubble ${role}`;
        div.textContent = text;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight; // 一番下にスクロール
    }

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // 1. ユーザーの入力を画面に反映
        appendMessage('user', text);
        chatInput.value = '';
        sendBtn.disabled = true;

        try {
            // 2. FastAPIエンドポイントへ非同期POST
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    student_id: "student_001",
                    module_id: "mod_01"
                })
            });

            const data = await response.json();

            // 3. AIの返答を画面に反映
            appendMessage('assistant', data.reply);

            // 4. レーダーチャートのアニメーション更新
            radarChart.data.datasets[1].data = [
                data.current_status.knowledge,
                data.current_status.thinking,
                data.current_status.application
            ];
            radarChart.update(); // 💡 これが呼ばれるとグラフがヌルッと動く

        } catch (error) {
            console.error("Error:", error);
            appendMessage('assistant', '通信エラーが発生しました。');
        } finally {
            sendBtn.disabled = false;
            chatInput.focus();
        }
    }

    // イベントリスナー
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});
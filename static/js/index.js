document.addEventListener('DOMContentLoaded', async () => {
    const classGrid = document.getElementById('class-grid');
    const loading = document.getElementById('loading');

    try {
        // 本来は fetch('/api/classes') などでバックエンドから取得します。
        // ここではAPIが繋がるまでのモックデータとして処理を組みます。
        const mockClasses = [
            { id: "class_001", name: "DevOps基礎講座2026", studentCount: 42, currentModule: "第3章" },
            { id: "class_002", name: "クラウドアーキテクチャ概論", studentCount: 18, currentModule: "第1章" }
        ];

        // API通信の遅延をシミュレート（デモ時のハッタリ用）
        await new Promise(resolve => setTimeout(resolve, 600));

        // ローディング非表示
        loading.style.display = 'none';

        // 授業カードの生成
        mockClasses.forEach(cls => {
            const card = document.createElement('div');
            card.className = 'class-card';
            
            card.innerHTML = `
                <h3 style="margin-top: 0; color: var(--text-main); font-family: 'Inter', sans-serif;">${cls.name}</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.6;">
                    現在の登録生徒: ${cls.studentCount}名<br>
                    進行中モジュール: ${cls.currentModule}
                </p>
                
                <div class="demo-actions">
                    <a href="/student?class_id=${cls.id}" class="btn btn-student">👤 Enter as Student</a>
                    <a href="/professor?class_id=${cls.id}" class="btn btn-prof">👨‍🏫 Enter as Prof</a>
                </div>
            `;
            
            classGrid.appendChild(card);
        });

    } catch (error) {
        console.error("Error loading classes:", error);
        loading.textContent = "授業データの読み込みに失敗しました。";
    }
});
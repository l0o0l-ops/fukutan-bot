document.addEventListener('DOMContentLoaded', async () => {
    const classGrid = document.getElementById('class-grid');
    const loading = document.getElementById('loading');

    try {
        const response = await fetch('/api/classes');
        const data = await response.json();
        
        loading.style.display = 'none';

        if (data.classes.length === 0) {
            classGrid.innerHTML = '<p class="loading-text">授業がまだありません。Settingsから追加してください。</p>';
            return;
        }

        data.classes.forEach(cls => {
            const card = document.createElement('div');
            card.className = 'class-card';
            
            // 🚀 ここで cls.name を直接指定
            card.innerHTML = `
                <h3 style="margin-top: 0; color: var(--text-main); font-family: 'Inter', sans-serif;">${cls.name}</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.6;">
                    現在の登録生徒: ${cls.studentCount || 0}名<br>
                    進行中モジュール: ${cls.currentModule || '未設定'}
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
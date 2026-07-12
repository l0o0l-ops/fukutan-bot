document.addEventListener('DOMContentLoaded', async () => {
    const classList = document.getElementById('class-list');
    const newClassInput = document.getElementById('new-class-input');
    const addClassBtn = document.getElementById('add-class-btn');

    // 🚀 初期ロード: Firestoreから既存クラス全読み込み
    const res = await fetch('/api/classes');
    const data = await res.json();
    classList.innerHTML = '';
    data.classes.forEach(c => {
        const li = document.createElement('li');
        li.className = 'list-item';
        li.id = `class-${c.id}`;
        li.innerHTML = `<span>${c.class_name}</span><button class="delete-btn" onclick="destroyClass('${c.id}')">🗑️ 削除</button>`;
        classList.appendChild(li);
    });

    // クラス追加本番通信
    addClassBtn.addEventListener('click', async () => {

        const name = newClassInput.value.trim();
        if (!name) return;

        // 🚀 修正: Formデータとして送信
        const body = new URLSearchParams();
        body.append("class_name", name); // main.pyの引数名と一致させる

        const response = await fetch('/api/classes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body
        });
        const created = await response.json();

        const li = document.createElement('li');
        li.className = 'list-item';
        li.id = `class-${created.id}`;
        li.innerHTML = `<span>${created.class_name}</span><button class="delete-btn" onclick="destroyClass('${created.id}')">🗑️ 削除</button>`;
        classList.appendChild(li);
        newClassInput.value = '';
    });

    window.destroyClass = async function(id) {
        if(!confirm("本当にこの授業を削除しますか？")) return;
        await fetch(`/api/classes/${id}`, { method: 'DELETE' });
        document.getElementById(`class-${id}`).remove();
    }
});
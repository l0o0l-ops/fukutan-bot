window.destroyClass = async function(id) {
    if(!confirm("本当にこの授業を削除しますか？")) return;
    await fetch(`/api/classes/${id}`, { method: 'DELETE' });
    document.getElementById(`class-${id}`).remove();
}


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



});

// === 🚀 生徒管理ロジック (追加分) ===
const studentList = document.getElementById('student-list');
const newStudentInput = document.getElementById('new-student-input');
const addStudentBtn = document.getElementById('add-student-btn');

// 生徒一覧の初期ロード
// ※特定のクラス(class_001)の生徒を読み込む想定（デモ用）
const classId = "class_001"; 

// 生徒リストの描画関数
async function loadStudents() {
    const res = await fetch(`/api/classes/${classId}`);
    const data = await res.json();
    studentList.innerHTML = '';
    if (data.roster) {
        data.roster.forEach(s => {
            appendStudentToList(s.student_id, s.display_name);
        });
    }
}
loadStudents();

// 生徒の追加処理
addStudentBtn.addEventListener('click', async () => {
    const name = newStudentInput.value.trim();
    if (!name) return;

    const body = new URLSearchParams();
    body.append("display_name", name);

    const response = await fetch(`/api/classes/${classId}/students`, {
        method: 'POST',
        body: body
    });
    
    if (response.ok) {
        const newStudent = await response.json();
        appendStudentToList(newStudent.student_id, newStudent.display_name);
        newStudentInput.value = '';
    } else {
        alert("生徒の追加に失敗しました");
    }
});

// 生徒削除用関数
window.destroyStudent = async function(studentId) {
    if(!confirm("本当にこの生徒を削除しますか？")) return;
    await fetch(`/api/classes/${classId}/students/${studentId}`, { method: 'DELETE' });
    document.getElementById(`student-${studentId}`).remove();
}

function appendStudentToList(id, name) {
    const li = document.createElement('li');
    li.className = 'list-item';
    li.id = `student-${id}`;
    li.innerHTML = `<span>${name}</span><button class="delete-btn" onclick="destroyStudent('${id}')">🗑️ 削除</button>`;
    studentList.appendChild(li);
}


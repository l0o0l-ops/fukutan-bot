document.addEventListener('DOMContentLoaded', () => {
    // === 授業(Class)管理のDOM ===
    const classList = document.getElementById('class-list');
    const newClassInput = document.getElementById('new-class-input');
    const addClassBtn = document.getElementById('add-class-btn');

    // === 生徒(Student)管理のDOM ===
    const studentList = document.getElementById('student-list');
    const newStudentInput = document.getElementById('new-student-input');
    const addStudentBtn = document.getElementById('add-student-btn');

    // 授業の追加処理
    addClassBtn.addEventListener('click', () => {
        const className = newClassInput.value.trim();
        if (!className) return;

        // 本来はここでFastAPI(Firestore)へPOSTリクエストを送信する
        const newId = `class-${Date.now()}`;
        const li = document.createElement('li');
        li.className = 'list-item';
        li.id = newId;
        li.innerHTML = `
            <span>${className}</span>
            <button class="delete-btn" onclick="deleteItem('${newId}', '授業')">🗑️ 削除</button>
        `;
        
        classList.appendChild(li);
        newClassInput.value = ''; // 入力欄をクリア
    });

    // 生徒の追加処理
    addStudentBtn.addEventListener('click', () => {
        const studentName = newStudentInput.value.trim();
        if (!studentName) return;

        // 本来はここでFastAPI(Firestore)へPOSTリクエストを送信する
        const newId = `student-${Date.now()}`;
        const li = document.createElement('li');
        li.className = 'list-item';
        li.id = newId;
        li.innerHTML = `
            <span>${studentName}</span>
            <button class="delete-btn" onclick="deleteItem('${newId}', '生徒')">🗑️ 削除</button>
        `;
        
        studentList.appendChild(li);
        newStudentInput.value = ''; // 入力欄をクリア
    });

    // Enterキーでも追加できるようにする（UX向上）
    newClassInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addClassBtn.click();
    });
    newStudentInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addStudentBtn.click();
    });
});

// 削除機能（グローバル関数）
window.deleteItem = function(elementId, typeName) {
    if(confirm(`本当にこの${typeName}を削除しますか？\n紐づくすべてのデータが失われます。`)) {
        // 本来はここでFastAPI(Firestore)へDELETEリクエストを送信する
        const item = document.getElementById(elementId);
        if(item) {
            item.remove();
        }
    }
}
/* Boterx Dashboard — App JS */

// Global helpers
async function api(url, options = {}) {
    const res = await fetch(url, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...options.headers }
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

// Status badge HTML
function statusBadge(status) {
    const map = {
        'pending': '<span class="badge badge-pending">معلقة</span>',
        'approved': '<span class="badge badge-approved">موافق</span>',
        'rejected': '<span class="badge badge-rejected">مرفوض</span>',
        'active': '<span class="badge badge-active">نشطة</span>',
        'completed': '<span class="badge badge-completed">مكتملة</span>',
        'cancelled': '<span class="badge badge-cancelled">ملغاة</span>',
        'waiting': '<span class="badge badge-pending">بانتظار</span>',
        'matched': '<span class="badge badge-active">مطابقة</span>',
        'code_verified': '<span class="badge badge-approved">كود مؤكد</span>',
        'awaiting_admin_review': '<span class="badge badge-pending">مراجعة الإدارة</span>',
        'admin_received': '<span class="badge badge-approved">الإدارة استلمت</span>',
        'transfer_confirmed': '<span class="badge badge-approved">تحويل مؤكد</span>',
        'yes': '<span class="badge badge-approved">نعم</span>',
        'no': '<span class="badge badge-rejected">لا</span>',
    };
    return map[status] || `<span class="badge" style="background:#334155;color:#94A3B8">${status || '—'}</span>`;
}

// Format number
function fmtNum(n) {
    return new Number(n || 0).toLocaleString('ar-EG');
}

// Format amount
function fmtAmount(n, currency = '') {
    return `${new Number(n || 0).toLocaleString('ar-EG', {maximumFractionDigits: 2})} ${currency}`;
}

// Escape HTML
function esc(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// Toast notification
function toast(message, type = 'info') {
    const colors = { info: 'bg-blue-500', success: 'bg-green-500', error: 'bg-red-500', warning: 'bg-amber-500' };
    const t = document.createElement('div');
    t.className = `fixed bottom-4 left-4 ${colors[type]} text-white px-4 py-2 rounded-lg shadow-lg z-[200] text-sm fade-in`;
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity 0.3s'; setTimeout(() => t.remove(), 300); }, 3000);
}

// Keyboard shortcut: Ctrl+K
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const search = document.getElementById('globalSearch');
        if (search) search.focus();
    }
});

/* Boterx Dashboard — App JS v3 */

// Global API helper
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
        'inactive': '<span class="badge badge-cancelled">متوقفة</span>',
        'completed': '<span class="badge badge-completed">مكتملة</span>',
        'cancelled': '<span class="badge badge-cancelled">ملغاة</span>',
        'waiting': '<span class="badge badge-pending">بانتظار</span>',
        'matched': '<span class="badge badge-active">مطابقة</span>',
        'code_verified': '<span class="badge badge-approved">كود مؤكد</span>',
        'awaiting_admin_review': '<span class="badge badge-pending">مراجعة الإدارة</span>',
        'admin_received': '<span class="badge badge-approved">الإدارة استلمت</span>',
        'transfer_confirmed': '<span class="badge badge-approved">تحويل مؤكد</span>',
        'disputed': '<span class="badge badge-rejected">نزاع مفتوح</span>',
        'resolved': '<span class="badge badge-approved">تم الحل</span>',
        'open': '<span class="badge badge-pending">مفتوحة</span>',
        'scheduled_freeze': '<span class="badge badge-pending">⏰ مجمد</span>',
        'yes': '<span class="badge badge-approved">نعم</span>',
        'no': '<span class="badge badge-rejected">لا</span>',
    };
    return map[status] || `<span class="badge" style="background:#334155;color:#94A3B8">${status || '—'}</span>`;
}

// Format number
function fmtNum(n) {
    return (n || 0).toLocaleString('ar-EG');
}

// Format amount
function fmtAmount(n, currency = '') {
    return `${(n || 0).toLocaleString('ar-EG', {maximumFractionDigits: 2})} ${currency}`;
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
    const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
    const container = document.getElementById('toastContainer') || createToastContainer();
    const t = document.createElement('div');
    t.className = `${colors[type]} text-white px-4 py-3 rounded-lg shadow-2xl text-sm fade-in flex items-center gap-2 mb-2 min-w-[250px]`;
    t.innerHTML = `<span>${icons[type]}</span> ${message}`;
    container.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity 0.3s'; setTimeout(() => t.remove(), 300); }, 3500);
}

function createToastContainer() {
    const c = document.createElement('div');
    c.id = 'toastContainer';
    c.className = 'fixed bottom-4 left-4 z-[300] flex flex-col';
    document.body.appendChild(c);
    return c;
}

// ===== Notification System with Sound =====

const Notifier = {
    enabled: true,
    soundEnabled: true,
    audioContext: null,
    lastPendingCount: 0,
    lastMatchCount: 0,
    lastComplaintsCount: 0,
    lastTradingCount: 0,
    lastSvrpCount: 0,

    init() {
        // Load saved preferences
        this.soundEnabled = localStorage.getItem('boterx_sound') !== 'false';
        this.enabled = localStorage.getItem('boterx_notif') !== 'false';

        // Create audio context on first user interaction
        document.addEventListener('click', () => {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
        }, { once: true });
    },

    toggleSound() {
        this.soundEnabled = !this.soundEnabled;
        localStorage.setItem('boterx_sound', this.soundEnabled);
        toast(this.soundEnabled ? '🔊 الصوت مفعل' : '🔇 الصوت مكتوم', 'info');
    },

    async check() {
        try {
            const res = await fetch('/api/stats');
            const stats = await res.json();
            const pendingNow = stats.transactions?.pending || 0;
            const matchesNow = stats.matches?.pending || 0;
            const activeMatches = stats.matches?.active || 0;
            const complaintsNow = stats.complaints?.open || 0;
            const tradingNow = stats.trading?.pending_orders || 0;
            const svrpNow = stats.svrp?.pending_requests || 0;

            // New pending transactions
            if (pendingNow > this.lastPendingCount && this.lastPendingCount > 0) {
                const diff = pendingNow - this.lastPendingCount;
                this.notify(`📥 ${diff} طلب معاملة جديد`, 'new_txn');
                this.playSound('notification');
            }

            // New match requests
            if (matchesNow > this.lastMatchCount && this.lastMatchCount > 0) {
                const diff = matchesNow - this.lastMatchCount;
                this.notify(`🔄 ${diff} طلب مطابقة جديد`, 'new_match');
                this.playSound('alert');
            }

            // New complaints
            if (complaintsNow > this.lastComplaintsCount && this.lastComplaintsCount > 0) {
                const diff = complaintsNow - this.lastComplaintsCount;
                this.notify(`📢 ${diff} شكوى جديدة`, 'new_complaint');
                this.playSound('alert');
            }

            // New trade orders
            if (tradingNow > this.lastTradingCount && this.lastTradingCount > 0) {
                this.notify(`💱 طلب تداول جديد`, 'new_trade');
                this.playSound('notification');
            }

            // New SVRP requests
            if (svrpNow > this.lastSvrpCount && this.lastSvrpCount > 0) {
                this.notify(`💎 طلب استرداد جديد`, 'new_svrp');
                this.playSound('notification');
            }

            this.lastPendingCount = pendingNow;
            this.lastMatchCount = matchesNow;
            this.lastComplaintsCount = complaintsNow;
            this.lastTradingCount = tradingNow;
            this.lastSvrpCount = svrpNow;

            // Update notification badge (total)
            const total = pendingNow + matchesNow + complaintsNow + tradingNow + svrpNow;
            const badge = document.getElementById('notifBadge');
            if (badge) {
                badge.textContent = total || '';
                badge.style.display = total > 0 ? 'flex' : 'none';
            }

            // Update sidebar red dots
            this.updateSidebarDots(pendingNow, matchesNow, complaintsNow, tradingNow, svrpNow);

            // Update live stats bar
            const liveBar = document.getElementById('liveStats');
            if (liveBar) {
                const parts = [];
                if (stats.users?.total) parts.push(`👥 ${fmtNum(stats.users.total)}`);
                if (pendingNow) parts.push(`⏳ ${pendingNow} معلقة`);
                if (activeMatches) parts.push(`🔄 ${activeMatches} مطابقة`);
                if (complaintsNow) parts.push(`📢 ${complaintsNow} شكاوى`);
                if (tradingNow) parts.push(`💱 ${tradingNow} تداول`);
                if (stats.lottery?.participants) parts.push(`🎰 ${stats.lottery.participants} مشارك`);
                if (stats.wheel?.participants) parts.push(`🎡 ${stats.wheel.participants} لاعب`);
                if (stats.lottery?.distributed) parts.push(`💰 ${fmtNum(stats.lottery.distributed)} موزّع`);
                liveBar.textContent = parts.join(' | ') || 'متصل';
            }
        } catch (e) { /* silent */ }
    },

    updateSidebarDots(txns, matches, complaints, trading, svrp) {
        const dots = {
            'transactions': txns,
            'matching': matches,
            'complaints': complaints,
            'trading': trading,
            'svrp': svrp,
        };
        for (const [page, count] of Object.entries(dots)) {
            const link = document.querySelector(`a[href="/${page}"]`);
            if (!link) continue;
            let dot = link.querySelector('.sidebar-dot');
            if (count > 0) {
                if (!dot) {
                    dot = document.createElement('span');
                    dot.className = 'sidebar-dot';
                    dot.style.cssText = 'position:absolute;top:8px;left:8px;width:8px;height:8px;background:#EF4444;border-radius:50%;animation:pulse 2s infinite';
                    link.style.position = 'relative';
                    link.appendChild(dot);
                }
                dot.style.display = 'block';
            } else if (dot) {
                dot.style.display = 'none';
            }
        }
    },

    notify(message, type) {
        if (!this.enabled) return;

        // Browser notification
        if (Notification.permission === 'granted') {
            const n = new Notification('🔔 Boterx', { body: message, icon: '/static/img/icon.png', tag: type, requireInteraction: false });
            setTimeout(() => n.close(), 4000);
        }

        // In-page notification
        const container = document.getElementById('notificationsList');
        if (container) {
            const item = document.createElement('div');
            item.className = 'flex items-center gap-2 p-2 rounded-lg bg-slate-700/50 text-sm animate-fade-in';
            item.innerHTML = `<span>${message}</span> <span class="text-xs text-slate-500">${new Date().toLocaleTimeString('ar-EG')}</span>`;
            container.prepend(item);
            if (container.children.length > 20) container.lastElementChild.remove();
        }

        // Large popup notification (1 second visible)
        this.showPopup(message, type);

        // Sound (1 second, loud)
        this.playSound(type === 'new_match' || type === 'new_complaint' ? 'alert' : 'notification');
    },

    showPopup(message, type) {
        // Remove any existing popup
        const existing = document.getElementById('bigPopup');
        if (existing) existing.remove();

        const colors = {
            'new_txn': { bg: 'bg-blue-600', icon: '📥' },
            'new_match': { bg: 'bg-green-600', icon: '🔄' },
            'new_complaint': { bg: 'bg-red-600', icon: '📢' },
            'new_trade': { bg: 'bg-amber-600', icon: '💱' },
            'new_svrp': { bg: 'bg-purple-600', icon: '💎' },
        };
        const c = colors[type] || { bg: 'bg-blue-600', icon: '🔔' };

        const popup = document.createElement('div');
        popup.id = 'bigPopup';
        popup.className = `fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 ${c.bg} text-white px-8 py-6 rounded-2xl shadow-2xl z-[500] text-center`;
        popup.innerHTML = `
            <div class="text-4xl mb-2">${c.icon}</div>
            <div class="text-lg font-bold">${message}</div>
            <div class="text-xs opacity-75 mt-1">${new Date().toLocaleTimeString('ar-EG')}</div>
        `;
        document.body.appendChild(popup);

        // Show for 1 second then fade out
        setTimeout(() => {
            popup.style.transition = 'opacity 0.3s, transform 0.3s';
            popup.style.opacity = '0';
            popup.style.transform = 'translate(-50%, -60%) scale(0.9)';
            setTimeout(() => popup.remove(), 300);
        }, 1000);
    },

    playSound(type = 'notification') {
        if (!this.soundEnabled || !this.audioContext) return;
        try {
            const ctx = this.audioContext;
            const now = ctx.currentTime;

            if (type === 'alert') {
                // Alert: 3 beeps over 1 second, loud
                for (let i = 0; i < 3; i++) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.frequency.value = 880;
                    osc.type = 'square';
                    gain.gain.setValueAtTime(0.3, now + i * 0.3);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.3 + 0.25);
                    osc.start(now + i * 0.3);
                    osc.stop(now + i * 0.3 + 0.25);
                }
            } else if (type === 'success') {
                // Success: rising notes, 1 second, loud
                const notes = [523, 659, 784, 1047];
                notes.forEach((freq, i) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.frequency.value = freq;
                    osc.type = 'sine';
                    gain.gain.setValueAtTime(0.3, now + i * 0.25);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.25 + 0.2);
                    osc.start(now + i * 0.25);
                    osc.stop(now + i * 0.25 + 0.2);
                });
            } else {
                // Notification: 2 beeps, 1 second, loud
                for (let i = 0; i < 2; i++) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.frequency.value = 740;
                    osc.type = 'sine';
                    gain.gain.setValueAtTime(0.3, now + i * 0.5);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.5 + 0.4);
                    osc.start(now + i * 0.5);
                    osc.stop(now + i * 0.5 + 0.4);
                }
            }
        } catch (e) { /* audio not available */ }
    },

    playSuccessSound() { this.playSound('success'); },
};

// Request notification permission
function requestNotificationPermission() {
    if (Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

// ===== Action Confirmation Helper =====
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Keyboard shortcut: Ctrl+K
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const search = document.getElementById('globalSearch');
        if (search) search.focus();
    }
    // Ctrl+N = toggle notifications
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        Notifier.toggleSound();
    }
});

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    Notifier.init();
    requestNotificationPermission();
    // Check for updates every 5 seconds
    setInterval(() => Notifier.check(), 5000);
    Notifier.check();

    // Click handler for notification permission request
    document.addEventListener('click', requestNotificationPermission, { once: true });
});

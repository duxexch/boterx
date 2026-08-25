// baseApp.js - Alpine.js component for the main dashboard layout
function baseApp() {
    return {
        sidebarOpen: window.innerWidth >= 1024,
        mobileSidebar: false,
        darkMode: localStorage.getItem('darkMode') !== 'false',
        isFullscreen: false,
        notifCount: 0,
        notifications: [],
        activityTicker: [],
        liveSource: null,
        lang: localStorage.getItem('lang') || 'ar',
        copied: false,

        init() {
            try { this.applyDarkMode(); } catch (e) {}
            try { this.applyLang(); } catch (e) {}
            try { this.startLiveStats(); } catch (e) {}
        },

        t(key) {
            // tr() (app.js) resolves the top-level `const I18N` via scope chain —
            // window.I18N does NOT exist because const doesn't attach to window
            try { return tr(key); } catch (e) {}
            return key;
        },

        applyLang() {
            document.documentElement.lang = this.lang;
            document.documentElement.dir = this.lang === 'ar' ? 'rtl' : 'ltr';
        },

        toggleLang() {
            this.lang = this.lang === 'ar' ? 'en' : 'ar';
            localStorage.setItem('lang', this.lang);
            this.applyLang();
            window.location.reload();
        },

        applyDarkMode() {
            if (this.darkMode) {
                document.documentElement.classList.remove('light-mode');
                document.body.classList.remove('light-mode');
            } else {
                document.documentElement.classList.add('light-mode');
                document.body.classList.add('light-mode');
            }
        },

        toggleDarkMode() {
            this.darkMode = !this.darkMode;
            localStorage.setItem('darkMode', this.darkMode);
            this.applyDarkMode();
        },

        toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().then(() => { this.isFullscreen = true; });
            } else {
                document.exitFullscreen().then(() => { this.isFullscreen = false; });
            }
        },

        startLiveStats() {
            this.fetchStats();
            this._statsTimer = setInterval(() => this.fetchStats(), 10000);
            if (typeof EventSource !== 'undefined') {
                try {
                    this.liveSource = new EventSource('/api/stats/live');
                    this.liveSource.onmessage = (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            this.processLiveStats(data);
                        } catch(e) {}
                    };
                    this.liveSource.onerror = () => {
                        if (this.liveSource) { this.liveSource.close(); this.liveSource = null; }
                    };
                } catch(e) {}
            }
        },

        async fetchStats() {
            try {
                const stats = await (window.api ? api('/api/stats') : fetch('/api/stats', { credentials: 'same-origin' }).then(r => r.json()));
                const p = stats.transactions?.pending || 0, m = stats.matches?.pending || 0;
                const c = stats.complaints?.open || 0, tr2 = stats.trading?.pending_orders || 0;
                const sv = stats.svrp?.pending_requests || 0;
                const lt = stats.lottery?.tickets_sold || 0, ws = stats.wheel?.total_spins || 0;
                const nu = stats.users?.today || 0;

                if (!this._primed) {
                    this._primed = true;
                    this.lastPendingCount = p; this.lastMatchCount = m;
                    this.lastComplaintsCount = c; this.lastTradingCount = tr2;
                    this.lastSvrpCount = sv; this.lastLotteryCount = lt;
                    this.lastWheelCount = ws; this.lastNewUsers = nu;
                }
                if (p > this.lastPendingCount && this.lastPendingCount >= 0) this.notify('📥 ' + (p - this.lastPendingCount) + ' ' + tr('pending_transactions'), 'new_txn');
                if (m > this.lastMatchCount && this.lastMatchCount >= 0) this.notify('🔄 ' + (m - this.lastMatchCount) + ' ' + tr('matching'), 'new_match');
                if (c > this.lastComplaintsCount && this.lastComplaintsCount >= 0) this.notify('📢 ' + (c - this.lastComplaintsCount) + ' ' + tr('complaints'), 'new_complaint');
                if (tr2 > this.lastTradingCount && this.lastTradingCount >= 0) this.notify('💱 ' + tr('trading'), 'new_trade');
                if (sv > this.lastSvrpCount && this.lastSvrpCount >= 0) this.notify('💎 ' + tr('svrp'), 'new_svrp');
                if (lt > this.lastLotteryCount && this.lastLotteryCount >= 0) this.notify('🎰 ' + (lt - this.lastLotteryCount) + ' ' + tr('lottery'), 'new_lottery');
                if (ws > this.lastWheelCount && this.lastWheelCount >= 0) this.notify('🎡 ' + (ws - this.lastWheelCount) + ' ' + tr('wheel'), 'new_wheel');
                if (nu > this.lastNewUsers && this.lastNewUsers >= 0) this.notify('👤 ' + (nu - this.lastNewUsers) + ' ' + tr('users'), 'new_user');

                this.lastPendingCount = p; this.lastMatchCount = m;
                this.lastComplaintsCount = c; this.lastTradingCount = tr2;
                this.lastSvrpCount = sv; this.lastLotteryCount = lt;
                this.lastWheelCount = ws; this.lastNewUsers = nu;

                const total = p + m + c + tr2 + sv;
                const badge = document.getElementById('notifBadge');
                if (badge) { badge.textContent = total || ''; badge.style.display = total > 0 ? 'flex' : 'none'; }

                this.updateSidebarDots(p, m, c, tr2, sv, lt, ws, nu);

                const liveBar = document.getElementById('liveStats');
                if (liveBar) {
                    const parts = [];
                    const _fmtNum = window.fmtNum || function(n){ return (n||0).toLocaleString(); };
                    if (stats.users?.total) parts.push('👥 ' + _fmtNum(stats.users.total));
                    if (p) parts.push('⏳ ' + p);
                    if (m) parts.push('🔄 ' + m);
                    if (c) parts.push('📢 ' + c);
                    if (tr2) parts.push('💱 ' + tr2);
                    if (stats.lottery?.participants) parts.push('🎰 ' + stats.lottery.participants);
                    if (stats.wheel?.participants) parts.push('🎡 ' + stats.wheel.participants);
                    liveBar.textContent = parts.join(' | ') || tr('connected');
                }
            } catch (e) {}
        },

        updateSidebarDots(txns, matches, complaints, trading, svrp, lottery, wheel, users) {
            const dots = { transactions: txns, matching: matches, complaints: complaints, trading: trading, svrp: svrp, lottery: lottery, wheel: wheel, users: users };
            for (const [page, count] of Object.entries(dots)) {
                const link = document.querySelector('a[href="/' + page + '"]');
                if (!link) continue;
                let dot = link.querySelector('.sidebar-dot');
                if (count > 0) {
                    if (!dot) {
                        dot = document.createElement('span');
                        dot.className = 'sidebar-dot';
                        dot.style.cssText = 'position:absolute;top:8px;left:8px;width:8px;height:8px;background:#EF4444;border-radius:50%;animation:pulse 2s infinite;cursor:pointer';
                        link.style.position = 'relative';
                        link.appendChild(dot);
                    }
                    dot.style.display = 'block';
                    dot.onclick = (e) => { e.preventDefault(); e.stopPropagation(); window.location.href = '/' + page; };
                } else if (dot) dot.style.display = 'none';
            }
        },
        notify(message, type) {
            if (!this.enabled) return;
            if (Notification.permission === 'granted') {
                const n = new Notification('🔔 VEX Games', { body: message, tag: type, icon: '/static/icons/icon-192.png', requireInteraction: type === 'broadcast' });
                setTimeout(() => n.close(), type === 'broadcast' ? 8000 : 4000);
                n.onclick = () => { window.focus(); n.close(); };
            }
            const container = document.getElementById('notificationsList');
            if (container) {
                const item = document.createElement('div');
                item.className = 'flex items-center gap-2 p-2 rounded-lg bg-slate-700/50 text-sm';
                item.innerHTML = '<span>' + message + '</span> <span class="text-xs text-slate-500">' + new Date().toLocaleTimeString() + '</span>';
                container.prepend(item);
                if (container.children.length > 20) container.lastElementChild.remove();
            }
            this.showPopup(message, type);
            let soundType = 'notification';
            if (type === 'broadcast') soundType = 'broadcast';
            else if (type === 'new_match' || type === 'new_complaint') soundType = 'alert';
            else if (type === 'deposit_approved' || type === 'withdrawal_approved' || type === 'vex_deposit') soundType = 'success';
            this.playSound(soundType);
        },
        showPopup(message, type) {
            const existing = document.getElementById('bigPopup');
            if (existing) existing.remove();
            const colors = {
                'new_txn': { bg: 'bg-blue-600', icon: '📥', url: '/transactions' },
                'new_match': { bg: 'bg-green-600', icon: '🔄', url: '/matching' },
                'new_complaint': { bg: 'bg-red-600', icon: '📢', url: '/complaints' },
                'new_trade': { bg: 'bg-amber-600', icon: '💱', url: '/trading' },
                'new_svrp': { bg: 'bg-purple-600', icon: '💎', url: '/svrp' },
                'new_lottery': { bg: 'bg-amber-600', icon: '🎰', url: '/lottery' },
                'new_wheel': { bg: 'bg-blue-600', icon: '🎡', url: '/wheel' },
                'new_user': { bg: 'bg-green-600', icon: '👤', url: '/users' },
            };
            const c = colors[type] || { bg: 'bg-blue-600', icon: '🔔', url: '/dashboard' };
            const popup = document.createElement('div');
            popup.id = 'bigPopup';
            popup.className = 'fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 ' + c.bg + ' text-white px-8 py-6 rounded-2xl shadow-2xl z-[500] text-center cursor-pointer';
            popup.innerHTML = '<div class="text-4xl mb-2">' + c.icon + '</div><div class="text-lg font-bold">' + message + '</div><div class="text-xs mt-2 opacity-50">' + tr('click_to_open') + ' ←</div>';
            popup.onclick = () => { window.location.href = c.url; };
            document.body.appendChild(popup);
            setTimeout(() => { popup.style.transition = 'opacity 0.3s, transform 0.3s'; popup.style.opacity = '0'; popup.style.transform = 'translate(-50%, -60%) scale(0.9)'; setTimeout(() => popup.remove(), 300); }, 3000);
        },
        playSound(type = 'notification') {
            if (!this.soundEnabled || !this.audioContext) return;
            try {
                const ctx = this.audioContext, now = ctx.currentTime;
                if (type === 'alert') {
                    for (let i = 0; i < 3; i++) {
                        const osc = ctx.createOscillator(), gain = ctx.createGain();
                        osc.connect(gain); gain.connect(ctx.destination);
                        osc.frequency.value = 880; osc.type = 'square';
                        gain.gain.setValueAtTime(0.35, now + i * 0.3);
                        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.3 + 0.25);
                        osc.start(now + i * 0.3); osc.stop(now + i * 0.3 + 0.25);
                    }
                    const bass = ctx.createOscillator(), bassGain = ctx.createGain();
                    bass.connect(bassGain); bassGain.connect(ctx.destination);
                    bass.frequency.value = 120; bass.type = 'sawtooth';
                    bassGain.gain.setValueAtTime(0.35, now);
                    bassGain.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
                    bass.start(now); bass.stop(now + 0.5);
                } else if (type === 'success') {
                    [523, 659, 784, 1047].forEach((freq, i) => {
                        const osc = ctx.createOscillator(), gain = ctx.createGain();
                        osc.connect(gain); gain.connect(ctx.destination);
                        osc.frequency.value = freq; osc.type = 'sine';
                        gain.gain.setValueAtTime(0.3, now + i * 0.12);
                        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.12 + 0.3);
                        osc.start(now + i * 0.12); osc.stop(now + i * 0.12 + 0.3);
                        const harm = ctx.createOscillator(), hGain = ctx.createGain();
                        harm.connect(hGain); hGain.connect(ctx.destination);
                        harm.frequency.value = freq * 2; harm.type = 'sine';
                        hGain.gain.setValueAtTime(0.1, now + i * 0.12);
                        hGain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.12 + 0.2);
                        harm.start(now + i * 0.12); harm.stop(now + i * 0.12 + 0.2);
                    });
                } else if (type === 'broadcast') {
                    [392, 523, 659, 784, 1047].forEach((freq, i) => {
                        const osc = ctx.createOscillator(), gain = ctx.createGain();
                        osc.connect(gain); gain.connect(ctx.destination);
                        osc.frequency.value = freq; osc.type = 'triangle';
                        gain.gain.setValueAtTime(0.3, now + i * 0.1);
                        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.1 + 0.4);
                        osc.start(now + i * 0.1); osc.stop(now + i * 0.1 + 0.4);
                    });
                    const chime = ctx.createOscillator(), cGain = ctx.createGain();
                    chime.connect(cGain); cGain.connect(ctx.destination);
                    chime.frequency.value = 1568; chime.type = 'sine';
                    cGain.gain.setValueAtTime(0.25, now + 0.5);
                    cGain.gain.exponentialRampToValueAtTime(0.001, now + 1.0);
                    chime.start(now + 0.5); chime.stop(now + 1.0);
                } else {
                    for (let i = 0; i < 2; i++) {
                        const osc = ctx.createOscillator(), gain = ctx.createGain();
                        osc.connect(gain); gain.connect(ctx.destination);
                        osc.frequency.value = 740; osc.type = 'sine';
                        gain.gain.setValueAtTime(0.2, now + i * 0.4);
                        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.4 + 0.35);
                        osc.start(now + i * 0.4); osc.stop(now + i * 0.4 + 0.35);
                    }
                }
            } catch (e) {}
            },
            playSuccessSound() { this.playSound('success'); },
        }
    };

// Register with Alpine (works regardless of load order:
// if Alpine already exists register now, otherwise wait for alpine:init)
if (window.Alpine) {
    Alpine.data('baseApp', baseApp);
} else {
    document.addEventListener('alpine:init', () => Alpine.data('baseApp', baseApp));
}
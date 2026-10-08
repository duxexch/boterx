# -*- coding: utf-8 -*-
"""Replace the AI Agents section (HTML + JS) in channels.html with the flexible agent system."""
import io

PATH = 'dashboard/templates/channels.html'
content = io.open(PATH, 'r', encoding='utf-8').read()
orig_len = len(content)

# ---------- 1. HTML SECTION ----------
ai_marker = content.find('🧠 AI Agents')
if ai_marker == -1:
    raise SystemExit('AI marker not found')
ai_start = content.rfind('<div class="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">', 0, ai_marker)
if ai_start == -1:
    raise SystemExit('AI section start not found')

pa_marker = content.find('🔐 Platform Accounts')
if pa_marker == -1:
    raise SystemExit('Platform Accounts marker not found')
pa_start = content.rfind('<div class="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">', 0, pa_marker)
if pa_start == -1 or pa_start <= ai_start:
    raise SystemExit('Platform section start not found')

NEW_HTML = """<div class="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
            <div class="flex items-center justify-between flex-wrap gap-2">
                <h3 class="font-bold">🧠 AI Agents — وكلاء أذكياء بتحكم كامل</h3>
                <button @click="openAddAgentModal()" class="btn btn-primary btn-sm">➕ وكيل جديد</button>
            </div>
            <p class="text-xs text-slate-400">اكتب اسم الوكيل → مفتاح API الخاص به → وصف مهمته → يشغل نفسه ويتحكم في اللوحة كاملة (موافقة معاملات، رد على الشكاوى، بث رسائل، حظر/فك حظر) ويراقب كل شيء.</p>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <!-- Agents list -->
                <div class="space-y-2 max-h-[32rem] overflow-auto">
                    <template x-for="a in aiAgents" :key="a.id">
                        <div class="p-3 rounded-xl bg-slate-900/60 border" :class="a.is_active === 'yes' ? 'border-green-500/30' : 'border-slate-700 opacity-60'">
                            <div class="flex items-center justify-between gap-2 flex-wrap">
                                <div class="flex items-center gap-2 flex-wrap">
                                    <span class="font-bold" x-text="a.name"></span>
                                    <span class="px-2 py-0.5 rounded text-xs" :class="a.is_active === 'yes' ? 'bg-green-500/20 text-green-400' : 'bg-slate-600/20 text-slate-400'" x-text="a.is_active === 'yes' ? '✅ نشط' : '⏸️ متوقف'"></span>
                                    <span class="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300" x-text="providerLabel(a.provider)"></span>
                                    <span class="px-2 py-0.5 rounded text-xs" :class="a.has_api_key ? 'bg-amber-500/20 text-amber-400' : 'bg-slate-600/20 text-slate-500'" x-text="a.has_api_key ? '🔑 مفتاح خاص' : '🔑 مفتاح عام'"></span>
                                </div>
                                <div class="flex gap-1">
                                    <button @click="runAgent(a)" class="btn btn-success btn-sm" title="تشغيل المهمة الآن">▶️ شغّل</button>
                                    <button @click="openAgentModal(a)" class="btn btn-sm" style="background:#334155" title="تعديل / تحكم">⚙️</button>
                                    <button @click="testAIAgent(a)" class="btn btn-sm" style="background:#334155" title="اختبار الاتصال">🧪</button>
                                    <button @click="toggleAgentActive(a)" class="btn btn-sm" :class="a.is_active === 'yes' ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300'" x-text="a.is_active === 'yes' ? '⏸️' : '▶️'"></button>
                                    <button @click="deleteAIAgent(a.id)" class="btn btn-danger btn-sm">🗑️</button>
                                </div>
                            </div>
                            <p class="text-xs text-slate-400 mt-2 line-clamp-2" x-text="a.job_description || a.instructions || '— بدون وصف مهمة —'"></p>
                            <p class="text-[10px] text-slate-500 mt-1" x-show="a.last_run_at">
                                ⏱ آخر تشغيل: <span x-text="a.last_run_at"></span> — <span class="text-slate-400" x-text="(a.last_run_result || '').slice(0, 120)"></span>
                            </p>
                        </div>
                    </template>
                    <p x-show="aiAgents.length === 0" class="text-center text-slate-400 p-6">لا يوجد وكلاء — اضغط «➕ وكيل جديد»</p>
                </div>

                <!-- Agent form -->
                <div class="bg-slate-900/50 rounded-xl border border-slate-700 p-4 space-y-3" x-show="showAgentForm">
                    <h4 class="font-bold" x-text="editingAgent ? ('✏️ تحكم: ' + (editingAgent.name || '')) : '➕ إنشاء وكيل جديد'"></h4>
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">🤖 اسم الوكيل *</label>
                        <input x-model="agentForm.name" class="input w-full" placeholder="مثال: مراقب المعاملات، مساعد الدعم، صائد العروض">
                    </div>
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">📝 وظيفته (Job Description) *</label>
                        <textarea x-model="agentForm.job_description" rows="3" class="input w-full" placeholder="مثال: راجع المعاملات المعلقة كل فترة،وافق على الصغيرة أقل من 500 وارفض المشبوهة، ورد على الشكاوى المفتوحة بلطف، وابث تحذيراً عند اكتشاف احتيال."></textarea>
                        <p class="text-xs text-slate-500 mt-1">اكتب مهمته بالتفصيل — هو ينفذها بنفسه ويتحكم في اللوحة: موافقة/رفض معاملات، رد شكاوى، بث، حظر/فك حظر.</p>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-sm text-slate-400 mb-1">🤖 المزوّد</label>
                            <select x-model="agentForm.provider" class="input w-full"><option value="auto">Auto</option><option value="openai">OpenAI</option><option value="claude">Claude</option><option value="kimi">Kimi</option><option value="openrouter">OpenRouter</option></select>
                        </div>
                        <div>
                            <label class="block text-sm text-slate-400 mb-1">🔄 احتياطي</label>
                            <select x-model="agentForm.fallback_provider" class="input w-full"><option value="">بدون</option><option value="openai">OpenAI</option><option value="claude">Claude</option><option value="kimi">Kimi</option><option value="openrouter">OpenRouter</option></select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">🔑 مفتاح API الخاص بالوكيل</label>
                        <input x-model="agentForm.api_key" type="password" class="input w-full font-mono" :placeholder="editingAgent && editingAgent.has_api_key ? '•••• محفوظ — اتركه فارغاً للإبقاء' : 'sk-... أو مفتاح OpenRouter'">
                        <p class="text-xs text-slate-500 mt-1">اختياري — لو فاضي يستخدم مفتاح المزوّد الافتراضي من صفحة مفاتيح AI.</p>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-sm text-slate-400 mb-1">🔧 Base URL (اختياري)</label>
                            <input x-model="agentForm.base_url" class="input w-full" placeholder="https://openrouter.ai/api/v1">
                        </div>
                        <div>
                            <label class="block text-sm text-slate-400 mb-1">📋 الموديل</label>
                            <input x-model="agentForm.default_model" class="input w-full" placeholder="gpt-4o-mini">
                        </div>
                    </div>
                    <div>
                        <label class="block text-sm text-slate-400 mb-1">🎯 قواعد إضافية (System Prompt)</label>
                        <textarea x-model="agentForm.instructions" rows="2" class="input w-full" placeholder="قواعد صارمة: لا توافق على معاملة أكبر من 1000 بدون مراجعة... إلخ"></textarea>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div><label class="block text-sm text-slate-400 mb-1">🌡 الحرارة</label><input type="number" step="0.1" min="0" max="2" x-model.number="agentForm.temperature" class="input w-full"></div>
                        <div><label class="block text-sm text-slate-400 mb-1">Max Tokens</label><input type="number" min="100" max="16000" x-model.number="agentForm.max_tokens" class="input w-full"></div>
                    </div>
                    <label class="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" x-model="agentForm.is_active" class="sr-only peer">
                        <div class="w-10 h-5 bg-slate-600 rounded-full peer peer-checked:after:translate-x-5 rtl:peer-checked:after:-translate-x-5 peer-checked:bg-green-500 after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all"></div>
                        <span class="ml-2 text-sm text-slate-300">نشط</span>
                    </label>
                    <div class="flex gap-2 pt-1">
                        <button @click="saveAgent()" class="btn btn-primary btn-sm flex-1" x-text="editingAgent ? '💾 حفظ التعديلات' : '➕ إنشاء الوكيل'"></button>
                        <button @click="cancelAgentForm()" class="btn btn-sm" style="background:#475569">إلغاء</button>
                    </div>
                </div>
            </div>
        </div>

        """

new_content = content[:ai_start] + NEW_HTML + content[pa_start:]

# ---------- 2. JS: agentForm + state ----------
old_form = "        aiAgentForm: { name: '', provider: 'auto', fallback_provider: '', instructions: '' },"
new_form = """        editingAgent: null,
        showAgentForm: false,
        agentForm: { name: '', provider: 'auto', fallback_provider: '', instructions: '', job_description: '', api_key: '', base_url: '', default_model: '', temperature: 0.7, max_tokens: 2048, is_active: true },
        agentRunResult: null,"""
if old_form not in new_content:
    raise SystemExit('aiAgentForm line not found')
new_content = new_content.replace(old_form, new_form, 1)

# ---------- 3. JS: replace createAIAgent with new functions ----------
create_start = new_content.find('        async createAIAgent() {')
save_start = new_content.find('        async saveAIAgent(a) {')
if create_start == -1 or save_start == -1 or save_start <= create_start:
    raise SystemExit('createAIAgent/saveAIAgent markers not found')

NEW_JS = """        providerLabel(p) { const labels = { openai: 'OpenAI', claude: 'Claude', kimi: 'Kimi', openrouter: 'OpenRouter', auto: 'Auto' }; return labels[p] || p; },
        providerClass(p) { const cls = { openai: 'bg-green-500/20 text-green-400', claude: 'bg-purple-500/20 text-purple-400', kimi: 'bg-blue-500/20 text-blue-400', openrouter: 'bg-orange-500/20 text-orange-400', auto: 'bg-slate-500/20 text-slate-300' }; return cls[p] || 'bg-slate-500/20 text-slate-300'; },
        openAddAgentModal() {
            this.editingAgent = null;
            this.agentForm = { name: '', provider: 'auto', fallback_provider: '', instructions: '', job_description: '', api_key: '', base_url: '', default_model: '', temperature: 0.7, max_tokens: 2048, is_active: true };
            this.showAgentForm = true;
        },
        openAgentModal(a) {
            this.editingAgent = a;
            this.agentForm = { name: a.name || '', provider: a.provider || 'auto', fallback_provider: a.fallback_provider || '', instructions: a.instructions || '', job_description: a.job_description || '', api_key: '', base_url: a.base_url || '', default_model: a.default_model || '', temperature: parseFloat(a.temperature) || 0.7, max_tokens: parseInt(a.max_tokens) || 2048, is_active: a.is_active === 'yes' };
            this.showAgentForm = true;
            this.$nextTick(() => this.$el.querySelector('[x-show=\\"showAgentForm\\"]')?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
        },
        cancelAgentForm() { this.showAgentForm = false; this.editingAgent = null; },
        async saveAgent() {
            if (!this.agentForm.name.trim()) return toast('اكتب اسم الوكيل', 'warning');
            if (!this.agentForm.job_description.trim() && !this.agentForm.instructions.trim()) return toast('اكتب وظيفة الوكيل أو قواعده', 'warning');
            try {
                const payload = { ...this.agentForm };
                if (this.editingAgent && !payload.api_key) delete payload.api_key; // keep stored key
                const url = this.editingAgent ? `/api/ai-agents/${this.editingAgent.id}` : '/api/ai-agents';
                const method = this.editingAgent ? 'PUT' : 'POST';
                await api(url, { method, body: JSON.stringify(payload) });
                toast(this.editingAgent ? 'تم حفظ التعديلات' : 'تم إنشاء الوكيل', 'success');
                this.cancelAgentForm();
                await this.loadAIAgents();
            } catch(e) { toast('فشل الحفظ', 'error'); }
        },
        async toggleAgentActive(a) {
            try {
                await api(`/api/ai-agents/${a.id}`, { method: 'PUT', body: JSON.stringify({ is_active: a.is_active === 'yes' ? 'no' : 'yes' }) });
                await this.loadAIAgents();
            } catch(e) { toast('فشل', 'error'); }
        },
        async runAgent(a) {
            if (!confirm('تشغيل الوكيل «' + a.name + '» الآن لينفذ مهمته على حالة اللوحة الحالية؟')) return;
            toast('الوكيل يعمل...', 'info');
            try {
                const d = await api(`/api/ai-agents/${a.id}/run`, { method: 'POST', body: '{}' });
                if (d.success) {
                    this.agentRunResult = d;
                    const acts = (d.actions_executed || []);
                    let msg = '✅ ' + a.name + ':\\n' + (d.report || 'تم');
                    if (acts.length) msg += '\\n\\n' + acts.map(r => (r.ok ? '✅' : '❌') + ' ' + r.action + ': ' + r.message).join('\\n');
                    alert(msg);
                } else { toast(d.error || 'فشل التشغيل', 'error'); }
                await this.loadAIAgents();
            } catch(e) { toast('فشل التشغيل: ' + (e.message || ''), 'error'); }
        },
"""
new_content = new_content[:create_start] + NEW_JS + new_content[save_start:]

io.open(PATH, 'w', encoding='utf-8').write(new_content)
print(f'Done. {orig_len} -> {len(new_content)} chars')
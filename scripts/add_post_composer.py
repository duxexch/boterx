# -*- coding: utf-8 -*-
"""Add comprehensive post creation UI to channels.html."""
import io

PATH = 'dashboard/templates/channels.html'
content = io.open(PATH, 'r', encoding='utf-8').read()
orig_len = len(content)

# ========== 1. Add PostComposer modal + Create Post button + post history ==========
# Find the end of the existing channel detail modal (line with </div> after modal)
# Insert BEFORE the closing {% endblock %} or at the end of the template content area

# Find where to add the "Create Post" button — right after the filter/category bar
# and before the channel grid
marker = '<div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">'
if marker in content:
    # Add "Create Post" button before the grid
    create_btn = """        <!-- Create Post Button -->
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold" x-show="tab === 'campaigns'" x-text="lang === 'ar' ? '📢 القنوات والنشر' : '📢 Channels & Publishing'"></h3>
            <div class="flex gap-2">
                <button @click="openPostComposer()" class="btn btn-primary">
                    <i class="fas fa-plus"></i> <span x-text="lang === 'ar' ? 'إنشاء منشور' : 'Create Post'"></span>
                </button>
            </div>
        </div>
"""
    if create_btn not in content:
        content = content.replace(marker, create_btn + '        ' + marker, 1)
        print('OK: Create Post button added')

# ========== 2. Add PostComposer modal before channel detail modal ==========
POST_COMPOSER = """
<!-- ===== POST COMPOSER MODAL ===== -->
<div x-show="showPostComposer" class="modal-overlay" @click.self="closePostComposer()" style="display:none" x-cloak>
    <div class="modal max-w-4xl">
        <div class="flex items-center justify-between mb-4">
            <h3 class="font-bold text-lg">📝 إنشاء منشور جديد</h3>
            <button @click="closePostComposer()" class="text-slate-400 hover:text-white"><i class="fas fa-times text-xl"></i></button>
        </div>

        <!-- Post Text -->
        <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">✍️ نص المنشور</label>
            <textarea x-model="postForm.message" rows="6" class="input w-full" placeholder="اكتب نص المنشور هنا... يدعم HTML للتيليغرام (bold, italic, links)"></textarea>
            <div class="flex items-center gap-3 mt-1">
                <span class="text-xs text-slate-500" x-text="(postForm.message || '').length + ' حرف'"></span>
                <div class="flex gap-1">
                    <button @click="postForm.message += '<b>نص</b>'" class="text-xs px-2 py-0.5 bg-slate-700 rounded hover:bg-slate-600">B</button>
                    <button @click="postForm.message += '<i>نص</i>'" class="text-xs px-2 py-0.5 bg-slate-700 rounded hover:bg-slate-600 italic">I</button>
                    <button @click="postForm.message += '<a href=\\'url\\'>نص</a>'" class="text-xs px-2 py-0.5 bg-slate-700 rounded hover:bg-slate-600">🔗</button>
                </div>
            </div>
        </div>

        <!-- Media Upload -->
        <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">📎 وسائط (صورة / فيديو / كلاهما)</label>
            <div class="flex flex-wrap gap-3">
                <label class="w-20 h-20 rounded-xl border-2 border-dashed border-slate-500 flex flex-col items-center justify-center cursor-pointer hover:border-green-500 transition">
                    <i class="fas fa-cloud-upload-alt text-xl text-slate-400"></i>
                    <span class="text-[10px] text-slate-500">رفع</span>
                    <input type="file" class="hidden" accept="image/*,video/*" @change="uploadPostMedia($event)" multiple>
                </label>
                <template x-for="(media, idx) in postForm.media" :key="idx">
                    <div class="relative w-20 h-20 rounded-xl overflow-hidden bg-slate-700 border border-slate-600 group">
                        <img x-show="media.type && media.type.startsWith('image')" :src="media.url" class="w-full h-full object-cover">
                        <video x-show="media.type && media.type.startsWith('video')" :src="media.url" class="w-full h-full object-cover"></video>
                        <div x-show="!media.type || (!media.type.startsWith('image') && !media.type.startsWith('video'))" class="w-full h-full flex items-center justify-center"><i class="fas fa-file text-xl text-slate-400"></i></div>
                        <button @click="removePostMedia(idx)" class="absolute inset-0 bg-red-600/80 flex items-center justify-center opacity-0 group-hover:opacity-100 transition"><i class="fas fa-trash text-white"></i></button>
                    </div>
                </template>
            </div>
        </div>

        <!-- Target Selection: Channels -->
        <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">📢 القنوات المستهدفة</label>
            <div class="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-40 overflow-auto bg-slate-900/50 rounded-xl p-3">
                <template x-for="ch in channels" :key="ch.id">
                    <label class="flex items-center gap-2 p-2 rounded-lg cursor-pointer transition" :class="postForm.channelIds.includes(ch.id) ? 'bg-green-500/20 border border-green-500/30' : 'bg-slate-800 border border-transparent hover:border-slate-600'">
                        <input type="checkbox" :value="ch.id" @change="togglePostChannel(ch.id)" class="accent-green-500" :checked="postForm.channelIds.includes(ch.id)">
                        <div>
                            <span class="text-sm" x-text="ch.title || 'غير معروف'"></span>
                            <span class="text-xs text-slate-500 block" x-text="ch.chat_id"></span>
                        </div>
                    </label>
                </template>
            </div>
            <div class="flex gap-2 mt-2">
                <button @click="selectAllChannels()" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">اختيار الكل</button>
                <button @click="postForm.channelIds = []" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">إلغاء الكل</button>
            </div>
        </div>

        <!-- Target Selection: Groups -->
        <div class="mb-4" x-show="groups.length > 0">
            <label class="block text-sm text-slate-400 mb-1">👥 مجموعات القنوات</label>
            <div class="flex flex-wrap gap-2">
                <template x-for="grp in groups" :key="grp.id">
                    <button @click="togglePostGroup(grp)" class="px-3 py-1.5 rounded-lg text-sm transition" :class="postForm.groupIds.includes(grp.id) ? 'bg-purple-500/20 border border-purple-500/30 text-purple-300' : 'bg-slate-800 border border-slate-600 text-slate-400 hover:border-slate-500'" x-text="grp.name"></button>
                </template>
            </div>
        </div>

        <!-- Schedule Options -->
        <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">⏰ الجدولة</label>
            <div class="flex gap-2 flex-wrap">
                <button @click="postForm.scheduleType = 'now'" class="px-4 py-2 rounded-lg text-sm transition" :class="postForm.scheduleType === 'now' ? 'bg-green-500/20 border border-green-500/30 text-green-300' : 'bg-slate-800 border border-slate-600 text-slate-400'">📤 فوري</button>
                <button @click="postForm.scheduleType = 'timed'" class="px-4 py-2 rounded-lg text-sm transition" :class="postForm.scheduleType === 'timed' ? 'bg-amber-500/20 border border-amber-500/30 text-amber-300' : 'bg-slate-800 border border-slate-600 text-slate-400'">📅 مجدول</button>
                <button @click="postForm.scheduleType = 'cron'" class="px-4 py-2 rounded-lg text-sm transition" :class="postForm.scheduleType === 'cron' ? 'bg-blue-500/20 border border-blue-500/30 text-blue-300' : 'bg-slate-800 border border-slate-600 text-slate-400'">🔄 كرون</button>
            </div>
            <!-- Timed -->
            <div x-show="postForm.scheduleType === 'timed'" class="mt-2">
                <input type="datetime-local" x-model="postForm.scheduledAt" class="input w-full md:w-auto">
            </div>
            <!-- Cron -->
            <div x-show="postForm.scheduleType === 'cron'" class="mt-2 space-y-2">
                <input type="text" x-model="postForm.cronExpr" class="input w-full md:w-96" placeholder="مثال: 0 9 * * * (كل يوم الساعة 9 صباحاً)">
                <div class="flex flex-wrap gap-2">
                    <button @click="postForm.cronExpr = '0 9 * * *'" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">كل يوم 9 ص</button>
                    <button @click="postForm.cronExpr = '0 9,18 * * *'" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">9 ص + 6 م</button>
                    <button @click="postForm.cronExpr = '0 */3 * * *'" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">كل 3 ساعات</button>
                    <button @click="postForm.cronExpr = '0 12 * * 1-5'" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">أيام العمل 12 ظ</button>
                    <button @click="postForm.cronExpr = '0 10 * * 0'" class="text-xs px-2 py-1 bg-slate-700 rounded hover:bg-slate-600">السبت 10 ص</button>
                </div>
                <p class="text-xs text-slate-500">تنسيق كرون: <code>دقيقة ساعة يوم الشهر يوم_الأسبوع</code></p>
            </div>
        </div>

        <!-- Priority -->
        <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">🏷️ الأولوية</label>
            <div class="flex gap-2">
                <button @click="postForm.priority = 'low'" class="px-3 py-1.5 rounded-lg text-sm" :class="postForm.priority === 'low' ? 'bg-slate-500/30 border border-slate-400' : 'bg-slate-800 border border-slate-600'">عادي</button>
                <button @click="postForm.priority = 'normal'" class="px-3 py-1.5 rounded-lg text-sm" :class="postForm.priority === 'normal' ? 'bg-green-500/20 border border-green-500/30' : 'bg-slate-800 border border-slate-600'">متوسط</button>
                <button @click="postForm.priority = 'high'" class="px-3 py-1.5 rounded-lg text-sm" :class="postForm.priority === 'high' ? 'bg-red-500/20 border border-red-500/30' : 'bg-slate-800 border border-slate-600'">عالي</button>
            </div>
        </div>

        <!-- Preview -->
        <div x-show="postForm.message || postForm.media.length > 0" class="mb-4 p-4 bg-slate-900/50 rounded-xl border border-slate-700">
            <h4 class="text-sm text-slate-400 mb-2">👁️ معاينة</h4>
            <div class="bg-slate-800 rounded-lg p-3">
                <div x-show="postForm.media.length > 0" class="flex gap-2 mb-2 flex-wrap">
                    <template x-for="(media, idx) in postForm.media" :key="'preview-'+idx">
                        <div class="w-32 h-24 rounded-lg overflow-hidden bg-slate-700">
                            <img x-show="media.type && media.type.startsWith('image')" :src="media.url" class="w-full h-full object-cover">
                            <video x-show="media.type && media.type.startsWith('video')" :src="media.url" class="w-full h-full object-cover"></video>
                        </div>
                    </template>
                </div>
                <p class="text-sm whitespace-pre-wrap" x-html="postForm.message || '(بدون نص)'"></p>
            </div>
            <div class="mt-2 text-xs text-slate-500">
                <span x-text="'📢 ' + (postForm.channelIds.length || 0) + ' قناة'"></span>
                <span x-show="postForm.groupIds.length > 0" x-text="' | 👥 ' + (postForm.groupIds.length || 0) + ' مجموعة'"></span>
                <span x-show="postForm.scheduleType !== 'now'" x-text="' | ⏰ ' + (postForm.scheduleType === 'timed' ? 'مجدول' : 'كرون')"></span>
            </div>
        </div>

        <!-- Submit -->
        <div class="flex gap-3">
            <button @click="submitPost()" class="btn btn-primary flex-1" :disabled="!postForm.message && postForm.media.length === 0">
                <i class="fas fa-paper-plane"></i>
                <span x-text="postForm.scheduleType === 'now' ? '📤 نشر الآن' : (postForm.scheduleType === 'timed' ? '📅 جدولة' : '🔄 إعداد كرون')"></span>
            </button>
            <button @click="closePostComposer()" class="btn" style="background:#475569">إلغاء</button>
        </div>
    </div>
</div>

"""

# Insert before the Channel Detail Modal
detail_modal_marker = '<!-- Channel Detail Modal -->'
if detail_modal_marker in content and POST_COMPOSER not in content:
    content = content.replace(detail_modal_marker, POST_COMPOSER + '\n' + detail_modal_marker, 1)
    print('OK: PostComposer modal added')

# ========== 3. Add JS functions to channelsApp ==========
# Find the closing of the function (before the last </script>)
# Insert postForm data and methods

POST_JS = """
        // === Post Composer ===
        showPostComposer: false,
        postForm: {
            message: '',
            media: [],
            channelIds: [],
            groupIds: [],
            scheduleType: 'now',
            scheduledAt: '',
            cronExpr: '',
            priority: 'normal',
        },
        openPostComposer() {
            this.postForm = { message: '', media: [], channelIds: [], groupIds: [], scheduleType: 'now', scheduledAt: '', cronExpr: '', priority: 'normal' };
            this.showPostComposer = true;
        },
        closePostComposer() { this.showPostComposer = false; },
        togglePostChannel(id) {
            const idx = this.postForm.channelIds.indexOf(id);
            if (idx >= 0) this.postForm.channelIds.splice(idx, 1);
            else this.postForm.channelIds.push(id);
        },
        togglePostGroup(grp) {
            const idx = this.postForm.groupIds.indexOf(grp.id);
            if (idx >= 0) { this.postForm.groupIds.splice(idx, 1); return; }
            this.postForm.groupIds.push(grp.id);
            const chIds = (grp.channel_ids || '').split('|').map(s => s.trim()).filter(Boolean);
            chIds.forEach(cid => { if (!this.postForm.channelIds.includes(cid)) this.postForm.channelIds.push(cid); });
        },
        selectAllChannels() { this.postForm.channelIds = this.channels.map(c => c.id).filter(Boolean); },
        async uploadPostMedia(event) {
            const files = event.target.files;
            if (!files) return;
            for (const file of files) {
                const form = new FormData();
                form.append('file', file);
                try {
                    const res = await fetch('/api/upload-broadcast-media', { method: 'POST', body: form, credentials: 'same-origin' });
                    const d = await res.json();
                    if (d.url) {
                        const absUrl = d.absolute_url || ('https://vex.deals' + d.url);
                        this.postForm.media.push({ url: absUrl, localUrl: d.url, type: file.type || 'image' });
                    } else {
                        toast(d.error || 'فشل الرفع', 'error');
                    }
                } catch(e) { toast('فشل رفع الملف', 'error'); }
            }
            event.target.value = '';
        },
        removePostMedia(idx) { this.postForm.media.splice(idx, 1); },
        async submitPost() {
            if (!this.postForm.message && this.postForm.media.length === 0) return toast('اكتب رسالة أو أضف وسائط', 'warning');
            if (this.postForm.channelIds.length === 0 && this.postForm.groupIds.length === 0) return toast('اختر قناة واحدة على الأقل', 'warning');
            if (this.postForm.scheduleType === 'timed' && !this.postForm.scheduledAt) return toast('حدد وقت الإرسال', 'warning');
            if (this.postForm.scheduleType === 'cron' && !this.postForm.cronExpr) return toast('اكتب تعبير كرون', 'warning');
            try {
                const payload = {
                    message: this.postForm.message,
                    media_urls: this.postForm.media.map(m => m.url),
                    channels: this.postForm.channelIds,
                    groups: this.postForm.groupIds,
                    schedule_type: this.postForm.scheduleType,
                    scheduled_at: this.postForm.scheduledAt,
                    cron_expr: this.postForm.cronExpr,
                    priority: this.postForm.priority,
                };
                const d = await api('/api/posts/create', { method: 'POST', body: JSON.stringify(payload) });
                if (d.success) {
                    toast(d.message || 'تم الإنشاء', 'success');
                    this.closePostComposer();
                    await this.loadVault();
                } else {
                    toast(d.error || 'فشل', 'error');
                }
            } catch(e) { toast('خطأ: ' + (e.message || ''), 'error'); }
        },
"""

# Insert before the closing of channelsApp return block
# Find the line right before the last two closing braces
insert_marker = "        // === Channels Posting (quick inline) ==="
if insert_marker in content:
    content = content.replace(insert_marker, POST_JS + '\n' + insert_marker, 1)
    print('OK: Post composer JS added')
else:
    # Try another insertion point
    insert_marker2 = "        // Channel Detail Modal"
    if insert_marker2 in content:
        content = content.replace(insert_marker2, POST_JS + '\n        // Channel Detail Modal', 1)
        print('OK: Post composer JS added (alt)')
    else:
        # Insert before selectedChannel
        insert_marker3 = "        selectedChannel: null,"
        if insert_marker3 in content:
            content = content.replace(insert_marker3, POST_JS + '\n        selectedChannel: null,', 1)
            print('OK: Post composer JS added (alt2)')
        else:
            print('WARN: Could not find JS insertion point')

io.open(PATH, 'w', encoding='utf-8').write(content)
print(f'\nDone. {orig_len} -> {len(content)} chars ({len(content)-orig_len:+d})')

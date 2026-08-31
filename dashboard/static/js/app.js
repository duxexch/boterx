/* Boterx Dashboard — App JS v5 — Complete Bilingual */

// ===== Global i18n Dictionary =====
const I18N = {
    ar: {
        // Sidebar
        dashboard: 'لوحة التحكم', transactions: 'المعاملات', users: 'المستخدمين',
        transactions_label: 'المعاملات',
        matching: 'المطابقات', svrp: 'التعويض', trading: 'التداول',
        agents: 'وكلاء المطابقة', clients: 'العملاء (White-Label)', tickets: 'التذاكر',
        user: 'المستخدم', no_results: 'لا توجد نتائج',
        lottery: 'اليانصيب', wheel: 'عجلة الحظ', companies: 'الشركات',
        payment_methods: 'وسائل الدفع', apps: 'التطبيقات', referrals: 'الإحالات',
        channels: 'القنوات', bots: 'البوتات', complaints: 'الشكاوى',
        broadcast: 'بث رسالة', statistics: 'الإحصائيات', admins: 'إدارة الأدمن',
        themes: 'الثيمات', exchange_addresses: 'عناوين الصرافة',
        send_message: 'رسالة لمستخدم', backup: 'النسخ الاحتياطي', settings: 'الإعدادات',
        operations: 'العمليات', management: 'الإدارة', system: 'النظام',
        advanced_system: 'النظام المتقدم',
        ai_api_keys: 'مفاتيح AI API', ai_providers: 'مزوّدو AI', ai_models: 'نماذج AI',
        // Navbar
        search_placeholder: 'بحث سريع... Ctrl+K', connected: 'متصل',
        notifications: 'الإشعارات', mark_read: 'تعليم كمقروء',
        no_notifications: 'لا توجد إشعارات', admin: 'أدمن', logout: 'خروج',
        page_title: 'لوحة التحكم', admin_panel: 'لوحة التحكم الإدارية',
        // Common UI
        loading: 'جارٍ التحميل...', no_data: 'لا توجد بيانات', save: 'حفظ',
        cancel: 'إلغاء', delete: 'حذف', edit: 'تعديل', add: 'إضافة',
        confirm: 'تأكيد', search: 'بحث', refresh: 'تحديث', back: 'رجوع',
        close: 'إغلاق', approve: 'موافقة', reject: 'رفض', export: 'تصدير',
        status: 'الحالة', date: 'التاريخ', amount: 'المبلغ', type: 'النوع',
        name: 'الاسم', id: 'المعرف', actions: 'إجراءات', total: 'الإجمالي',
        page: 'صفحة', of: 'من', previous: 'السابق', next: 'التالي',
        all: 'الكل', pending: 'معلقة', approved: 'موافق عليه', rejected: 'مرفوض',
        active: 'نشط', inactive: 'متوقف', completed: 'مكتمل', cancelled: 'ملغي',
        yes: 'نعم', no: 'لا', phone: 'الهاتف', language: 'اللغة', currency: 'العملة',
        customer_id: 'رقم العميل', company: 'الشركة', wallet: 'المحفظة',
        deposit: 'إيداع', withdraw: 'سحب', balance: 'الرصيد', frozen: 'مجمد',
        available: 'متاح', earned: 'مكتسب', verified: 'موثق', unverified: 'غير موثق',
        // Dashboard
        total_users: 'إجمالي المستخدمين', new_today: 'جدد اليوم',
        total_transactions: 'إجمالي المعاملات', pending_transactions: 'معاملات معلقة',
        transaction_volume: 'حجم المعاملات', today: 'اليوم', active_matches: 'مطابقات نشطة', pending_matches: 'مطابقات معلقة',
        lottery_participants: 'مشاركين اليانصيب', wheel_players: 'لاعبي عجلة الحظ',
        distributed: 'موزّع', pending_items: 'العناصر المعلقة',
        bulk_approve: 'موافقة جماعية', bulk_reject: 'رفض جماعي',
        recent_transactions: 'آخر المعاملات', recent_users: 'آخر المستخدمين',
        view_all: 'عرض الكل', recent_activity: 'النشاط الأخير',
        tx_distribution: 'توزيع حالات المعاملات', tx_last_30: 'معاملات آخر 30 يوم',
        // Transactions
        tx_id: 'رقم المعاملة', client: 'العميل', tx_type: 'النوع',
        tx_company: 'الشركة', tx_amount: 'المبلغ', tx_status: 'الحالة',
        tx_date: 'التاريخ', tx_actions: 'إجراءات', auto_update: 'تحديث تلقائي',
        min_amount: 'أقل مبلغ', max_amount: 'أعلى مبلغ', date_from: 'من تاريخ',
        date_to: 'إلى تاريخ', export_csv: 'تصدير CSV', select_all: 'تحديد الكل',
        approve_modal_title: 'موافقة على المعاملة', amount_editable: 'المبلغ (يمكنك تعديله)',
        approve_confirm: 'موافقة وتأكيد المبلغ', reject_reason: 'سبب الرفض',
        // Users
        user_search: 'بحث بالاسم/الهاتف/ID', banned: 'محظور', ban: 'حظر',
        unban: 'إلغاء الحظر', ban_reason: 'سبب الحظر', profile: 'الملف الشخصي',
        registration_date: 'تاريخ التسجيل', user_transactions: 'معاملات المستخدم',
        svrp_wallet: 'محفظة التعويض', company_accounts: 'حسابات الشركات',
        // Matching
        active_matches_tab: 'نشطة', pending_requests_tab: 'معلقة', logs_tab: 'سجلات',
        match_id: 'رقم المطابقة', depositor: 'المودع', withdrawer: 'الساحب',
        // Channels
        add_channel: 'إضافة قناة', channel_title: 'اسم القناة',
        chat_id: 'Chat ID', channel_type: 'النوع', channel: 'قناة', group: 'مجموعة',
        supergroup: 'مجموعة خارقة', category: 'الفئة', relay_to_users: 'للمستخدمين',
        relay_to_channels: 'للقنوات', ai_enabled: 'AI مفعّل', send_message_btn: 'إرسال',
        post_vault: 'الأرشيف', ai_settings: 'إعدادات AI', daily_report: 'تقرير يومي',
        source_channels: 'القنوات المصدرية', uncategorized: 'غير مصنف',
        // SVRP
        svrp_wallets: 'المحافظ', recovery_requests: 'طلبات الاسترداد',
        bonus_requests: 'طلبات المكافآت', promo_codes: 'الرموز الترويجية',
        // Lottery
        lottery_rounds: 'جولات اليانصيب', tickets_sold: 'تذاكر مباعة',
        participants: 'مشاركين', winners: 'فائزين', prize_pool: 'الجائزة',
        draw_time: 'موعد السحب', ticket_price: 'سعر التذكرة',
        // Settings
        system_settings: 'إعدادات النظام', button_labels: 'مسميات الأزرار',
        audit_log: 'سجل الإجراءات', setting_key: 'المفتاح', setting_value: 'القيمة',
        // Dashboard extras
        trading_orders: 'طلبات التداول', pending_trading: 'تداول معلّق',
        pending_svrp: 'تعويض معلّق', load_failed: 'فشل التحميل',
        no_transactions: 'لا توجد معاملات', no_users: 'لا يوجد مستخدمين', no_activity: 'لا يوجد نشاط',
        bulk_approve_txns: 'موافقة جماعية على المعاملات',
        bulk_reject_txns: 'رفض جماعي على المعاملات',
        top_companies: 'أعلى 5 شركات بالحجم',
        user_registrations: 'تسجيلات المستخدمين (14 يوم)',
        confirm_bulk_approve: 'موافقة جماعية على كل المعاملات المعلقة؟',
        confirm_bulk_reject: 'رفض كل المعاملات المعلقة؟',
        bulk_approved: 'تمت الموافقة الجماعية',
        operation_failed: 'فشلت العملية',
        bulk_rejected: 'تم الرفض الجماعي',
        admin_id: 'معرف الأدمن', enter_admin_id: 'أدخل معرف الأدمن',
        password: 'كلمة المرور', login: 'دخول', login_title: 'دخول — Boterx',
        all_rights: 'جميع الحقوق محفوظة', search_dots: 'بحث...',
        manager: 'مدير', general_manager: 'مدير عام',
        switch_to_arabic: 'التحويل للعربية', last_activity: 'آخر نشاط:',
        total_amount: 'إجمالي المبلغ', avg_amount: 'متوسط المبلغ',
        approved_volume: 'حجم المعاملات الموافق عليها', all_types: 'جميع الأنواع',
        selected: 'محدد', deselect_all: 'إلغاء التحديد',
        txn_details: 'تفاصيل المعاملة', client_name: 'اسم العميل',
        admin_note: 'ملاحظة الأدمن', phone_number: 'رقم الهاتف',
        banned_count: 'محظورين', verified_phones: 'هواتف موثقة',
        user_search_placeholder: 'بحث بالاسم/الهاتف/معرف العميل/Telegram ID...',
        not_banned: 'غير محظور', user_details: 'تفاصيل المستخدم',
        phone_verified: 'الهاتف موثق', pending_balance: 'مجمد',
        total_earned: 'إجمالي الأرباح', freeze_balance: 'تجميد الرصيد',
        unfreeze_balance: 'فك التجميد', ban_user: 'حظر مستخدم',
        confirm_ban: 'تأكيد الحظر', user_banned: 'تم حظر المستخدم',
        ban_failed: 'فشل الحظر', unban_user: 'إلغاء حظر المستخدم',
        user_unbanned: 'تم إلغاء الحظر', updated: 'تم التحديث',
        update_failed: 'فشل التحديث', confirm_freeze: 'تجميد رصيد المستخدم بالكامل؟',
        unfreeze_amount: 'المبلغ المراد فك تجميده؟', balance_frozen: 'تم تجميد الرصيد',
        freeze_failed: 'فشل التجميد', balance_unfrozen: 'تم فك التجميد',
        channels_groups: 'القنوات والمجموعات', channels_tab: 'قنوات', groups_tab: 'مجموعات',
        archive: 'الأرشيف', active_count: 'نشط', categories: 'الفئات',
        unknown: 'غير معروف', send: 'إرسال',
        add_channel_group: 'إضافة قناة / مجموعة', channel_name: 'اسم القناة',
        channel_example: 'مثال: قناة أخبار', not_enabled: 'غير مفعّل',
        ai_instructions: 'تعليمات AI', test: 'اختبار', text_replace: 'استبدال النصوص',
        find_text: 'ابحث عن...', replace_with: 'استبدال بـ...',
        today_posts: 'منشورات اليوم', ai_processed: 'تمت المعالجة بالـ AI',
        users_reached: 'المستخدمون الذين وصلوا', active_channels: 'قنوات نشطة',
        recent_relays: 'إعادة التوجيه الأخيرة', source: 'المصدر', preview: 'معاينة',
        users_count: 'المستخدمون', channels_count: 'القنوات', no_settings: 'لا توجد إعدادات',
        original_text: 'النص الأصلي', new_text: 'النص الجديد',
        no_button_labels: 'لا توجد مسميات أزرار', no_audit_log: 'لا توجد سجلات إجراءات بعد',
        total_complaints: 'إجمالي الشكاوى', open_complaints: 'شكاوى مفتوحة',
        resolved: 'تم الحل', message_text: 'نص الرسالة', admin_reply: 'رد الأدمن',
        no_complaints: 'لا توجد شكاوى', reply_to_complaint: 'الرد على الشكوى',
        original_message: 'الرسالة الأصلية:', write_reply_here: 'اكتب ردك هنا...',
        replied: 'تم الرد', admin_management: 'إدارة الأدمن',
        manage_admins: 'إدارة المدراء', admin_management_desc: 'إضافة، إزالة، وتعديل صلاحيات الأدمن',
        add_admin: 'إضافة أدمن', permanent: 'دائم', temporary: 'مؤقت',
        full_access: 'وصول كامل', full_permission: 'صلاحية كاملة',
        support: 'الدعم', telegram_id: 'Telegram ID', role: 'الدور',
        no_admins_yet: 'لا يوجد أدمن بعد', add_new_admin: 'إضافة أدمن جديد',
        admin_name: 'اسم الأدمن', duration_hours: 'المدة (ساعات)',
        leave_empty_permanent: 'اتركه فارغاً للدائم', expiry_date: 'تاريخ الانتهاء',
        assign_role: 'تعيين الدور', admin_label: 'أدمن:', new_role: 'دور جديد',
        confirm_removal: 'تأكيد الإزالة', confirm_remove_admin: 'هل أنت متأكد من إزالة',
        from_admins: 'من الأدمن؟', permissions_revoked: 'سيتم إبطال جميع الصلاحيات فوراً.',
        remove: 'إزالة', broadcast_message: 'بث رسالة',
        send_to_all: 'إرسال رسالة لكل المستخدمين', message_type: 'نوع الرسالة',
        image: 'صورة', video: 'فيديو', message_text_label: 'نص الرسالة',
        write_message_here: 'اكتب الرسالة هنا...', broadcast_queued: 'سيتم إضافة الرسالة لقائمة البث',
        send_broadcast: 'إرسال البث', sending: 'جارٍ الإرسال...', preview_label: 'معاينة:',
        detailed_stats: 'الإحصائيات التفصيلية', stats_description: 'تحليل شامل لأداء النظام والمعاملات والمستخدمين',
        this_week: 'هذا الأسبوع', this_month: 'هذا الشهر',
        avg_transaction: 'متوسط المعاملة', completion_rate: 'معدل الإكمال',
        transactions_over_time: 'المعاملات عبر الزمن', tx_type_distribution: 'توزيع أنواع المعاملات',
        user_growth: 'نمو المستخدمين', top_users: 'أعلى 10 مستخدمين بالمعاملات',
        complaints_stats: 'إحصائيات الشكاوى', resolution_rate: 'معدل الحل',
        resolution_progress: 'تقدم الحل', loading_stats: 'جارٍ تحميل الإحصائيات...',
        stats_load_failed: 'فشل تحميل الإحصائيات', new_users: 'المستخدمون الجدد',
        notifications_title: 'الإشعارات', time: 'الوقت',
        total_users_label: 'إجمالي المستخدمين', dispute: 'نزاع', open: 'مفتوح',
        auto_rejected: 'رفض تلقائي', withdrawal_rejected: 'رفض سحب',
        pending_withdrawal: 'سحب معلق', pending_code_verification: 'بانتظار الكود',
        muted: 'صامت', click_to_open: 'انقر للذهاب',
        // AI API Keys page
        add_api_key: 'إضافة مفتاح API', provider: 'المزوّد', api_key: 'مفتاح API',
        model: 'النموذج', is_active: 'مفعّل', priority: 'الأولوية',
        base_url: 'Base URL', api_key_placeholder: 'sk-... أو المفتاح الخاص بالمزوّد',
        model_placeholder: 'مثال: gpt-4o، claude-3-5-sonnet، gemini-1.5-pro',
        test_connection: 'اختبار الاتصال', connection_success: 'الاتصال ناجح',
        connection_failed: 'فشل الاتصال', edit_key: 'تعديل المفتاح', delete_key: 'حذف المفتاح',
        no_keys_yet: 'لا توجد مفاتيح بعد — أضف أول مفتاح API',
        key_name: 'اسم المفتاح', key_name_placeholder: 'مثال: OpenAI Main، Anthropic Backup',
        provider_openai: 'OpenAI', provider_anthropic: 'Anthropic', provider_google: 'Google (Gemini)',
        provider_azure: 'Azure OpenAI', provider_custom: 'مخصص (Custom)',
        models_fetched: 'تم جلب النماذج', fetch_models: 'جلب النماذج',
        auto_fetch_models: 'جلب النماذج تلقائياً', models_list: 'قائمة النماذج',
        default_model: 'النموذج الافتراضي', temperature: 'Temperature',
        max_tokens: 'Max Tokens', timeout_seconds: 'المهلة (ثوانٍ)',
        provider_info: 'معلومات المزوّد', api_docs_link: 'رابط التوثيق',
        key_validated: 'المفتاح صالح', key_invalid: 'المفتاح غير صالح',
        usage_stats: 'إحصائيات الاستخدام', requests_today: 'طلبات اليوم',
        tokens_today: 'توكنز اليوم', cost_estimate_usd: 'التكلفة التقديرية (USD)',
        // Channels page
        campaigns_tab: 'الحملات', channels_tab: 'القنوات', groups_tab: 'المجموعات',
        vault_tab: 'الأرشيف', ai_tab: 'AI', report_tab: 'التقرير',
        analytics_tab: 'تحليلات', ainet_tab: 'الشبكة',
        total_partners: 'إجمالي الشركاء', active_partners: 'الشركاء النشطون',
        total_subscribers: 'إجمالي المشتركين', cpm: 'CPM', total_revenue: 'إجمالي الإيرادات',
        new_partner: 'شريك جديد', add_channel: 'إضافة قناة',
        enable: 'تفعيل', for_users: 'للمستخدمين', for_channels: 'للقنوات',
        platform: 'المنصة', role: 'الدور', source_publish: 'Source + Publish',
        source_only: 'Source only', publish_only: 'Publish only',
        ai_agent: 'وكيل AI', platform_account: 'حساب المنصة',
        owner_admin_id: 'Owner Admin ID', manager_admin_ids: 'Manager Admin IDs',
        allow_subadmin_publish: 'سماح نشر Subadmin', category: 'الفئة',
        send: 'إرسال', cancel: 'إلغاء', add: 'إضافة', launch_now: 'إطلاق فوري',
        schedule_campaign: 'جدولة الحملة',
        channel_name: 'اسم القناة', chat_id: 'Chat ID', type: 'النوع',
        channel: 'قناة', group: 'مجموعة', supergroup: 'مجموعة خارقة',
        platform: 'المنصة', channel_role: 'الدور', owner_admin_id: 'Owner Admin ID',
        manager_admin_ids: 'Manager Admin IDs', category: 'الفئة',
        sports: 'رياضة', finance: 'مال', trading: 'تداول', games: 'ألعاب',
        news: 'أخبار', marketing: 'تسويق', entertainment: 'ترفيه', other: 'أخرى',
        uncategorized: 'غير مصنف',
        create_group: 'إنشاء مجموعة', group_name: 'اسم المجموعة',
        group_description: 'وصف المجموعة', create: 'إنشاء',
        vault_date: 'التاريخ', vault_provider: 'المزود',
        vault_original: 'الأصلي', vault_processed: 'المعالج', vault_actions: 'الإجراءات',
        ai_instructions: 'تعليمات AI', test: 'اختبار',
        ai_agents: 'وكلاء AI', add_agent: 'إضافة وكيل',
        platform_accounts: 'حسابات المنصة', add_account: 'إضافة حساب',
        source_channels: 'القنوات المصدرية', add_source: 'إضافة مصدر',
        today_posts: 'منشورات اليوم', ai_processed: 'تمت المعالجة بالـ AI',
        users_reached: 'المستخدمون الذين وصلوا', active_channels: 'قنوات نشطة',
        source: 'المصدر', preview: 'معاينة', users_count: 'المستخدمون',
        channels_count: 'القنوات', actions: 'الإجراءات',
        // General terms
        active_players: 'لاعبون نشطون', add_game: 'إضافة لعبة',
        algorithm_config: 'إعدادات الخوارزمية', compensation_interval: 'فترة التعويض',
        config: 'الإعدادات', cur_aed: 'درهم إماراتي (AED)', cur_current: 'العملة الحالية',
        cur_egp: 'جنيه مصري (EGP)', cur_kwd: 'دينار كويتي (KWD)', cur_sar: 'ريال سعودي (SAR)',
        cur_title: 'العملة', cur_usd: 'دولار أمريكي (USD)', cur_usdt: 'USDT',
        err_generic: 'حدث خطأ عام', games: 'الألعاب', hero_badge: 'شعار البطل',
        hero_cta_games: 'استعرض الألعاب', hero_cta_login: 'دخول الحساب',
        hero_cta_play: 'العب الآن', hero_p: 'الوصف الرئيسي',
        hub_champions: 'الأبطال', hub_loading: 'جارٍ التحميل...',
        hub_my_account: 'حسابي', hub_my_wallet: 'محفظتي', hub_no_games: 'لا توجد ألعاب',
        hub_num: 'الرقم', max_bets_hour: 'الحد الأقصى للرهانات/ساعة',
        max_daily_loss: 'الحد الأقصى للخسارة اليومية', max_daily_win: 'الحد الأقصى للربح اليومي',
        min_balance: 'الحد الأدنى للرصيد', nav_account: 'الحساب',
        nav_play_now: 'العب الآن', net_profit: 'صافي الربح',
        no_pending_deposits: 'لا توجد إيداعات معلقة', pending_deposits: 'إيداعات معلقة',
        platform_edge: 'هامش المنصة', players: 'اللاعبون', risk_alerts: 'تنبيهات المخاطر',
        seg_churning: 'متردد', seg_hot: 'نشط جداً', seg_loser: 'خاسر',
        seg_new: 'جديد', seg_regular: 'منتظم', seg_vip: 'VIP', seg_winner: 'فائز',
        stat_always: 'متاح دائماً', stat_games_diff: 'ألعاب مختلفة',
        stat_paid: 'جوائز مدفوعة', stat_users: 'مستخدمون مسجلون',
        tag_daily: 'يومي', tag_instant: 'فوري', tag_online: 'أونلاين', tag_secure: 'آمن',
        target_edge: 'هامش مستهدف', ticker_label: 'مؤشر مباشر', total_wagered: 'إجمالي المراهنات',
        wdr_acc_ph: 'رقم الحساب/المحفظة', wdr_amt_ph: 'المبلغ', wdr_choose: 'اختر وسيلة',
        wdr_confirm: 'تأكيد السحب', wdr_enter_both: 'أدخل الحساب والمبلغ',
        wdr_or_manual: 'أو أدخل يدوياً', wdr_pending: 'قيد المراجعة',
        wdr_requested: 'تم طلب السحب', wdr_title: 'سحب الأموال', wdr_your_bal: 'رصيدك',
        // Duplicate cleanup - x000 etc are legacy codes, mapped to proper keys above
        // ===== Broadcast & Social (v20260826) =====
        copy_permanent_link: 'نسخ رابط العرض الدائم',
        broadcast_all: 'بث جماعي', broadcast_single: 'بث فردي',
        broadcast_to_all_agents: 'بث لجميع الوكلاء', broadcast_to_all_channels: 'بث لجميع القنوات',
        all_users: 'كل المستخدمين', specific_user: 'مستخدم محدد',
        both_channels: 'الاثنين', clear_selection: 'مسح التحديد',
        target_countries: 'الدول المستهدفة', target_countries_label: 'الدول المستهدفة (متعددة)',
        target_agents: 'الوكلاء المستهدفين', target_platforms: 'منصات السوشيال ميديا',
        target_platforms_label: 'منصات السوشيال ميديا',
        social_platforms: 'منصات السوشيال ميديا',
        telegram: 'تيليغرام', whatsapp: 'واتساب', facebook: 'فيسبوك', instagram: 'إنستجرام',
        twitter: 'تويتر/إكس', tiktok: 'تيك توك', youtube: 'يوتيوب', linkedin: 'لينكدإن',
        web: 'الموقع',
        // Channels / social
        social_tab: 'السوشيال', campaigns_tab: 'الحملات', network_tab: 'الشبكة',
        add_social_account: 'إضافة حساب سوشيال', no_social_accounts: 'لا توجد حسابات سوشيال ميديا — أضف أول حساب',
        account_name: 'اسم الحساب', handle: 'المعرف', platform_account: 'حساب المنصة',
        access_token: 'رمز الوصول', page_id: 'معرف الصفحة', business_account_id: 'معرف حساب الأعمال',
        phone_number_id: 'معرف رقم الهاتف', subscriber_count: 'عدد المشتركين',
        followers: 'المتابعون', contact: 'جهة الاتصال', confirm_delete: 'تأكيد الحذف',
        campaign_name: 'اسم الحملة', content_categories: 'فئات المحتوى',
        posting_permissions: 'صلاحيات النشر', sub_agent: 'الوكيل الفرعي',
        sub_agents_connected: 'وكلاء فرعيون متصلون', platforms_connected: 'منصات متصلة',
        active_accounts: 'حسابات نشطة', total_accounts: 'إجمالي الحسابات',
        total_campaigns: 'إجمالي الحملات', total_reach: 'إجمالي الوصول',
        total_clicks: 'إجمالي النقرات', ctr: 'معدل النقر CTR', conversions: 'التحويلات',
        clicks: 'النقرات', reach: 'الوصول', daily_reach: 'الوصول اليومي',
        last_sync: 'آخر مزامنة', revenue_share: 'نسبة الأرباح',
        top_campaigns: 'أفضل الحملات', pending_matches: 'مطابقات معلقة',
        // Campaign wizard
        create_campaign: '📊 إنشاء حملة إعلانية',
        campaign_wizard_content: '💬 المحتوى', campaign_wizard_platform: '🎯 المنصة',
        campaign_wizard_audience: '👥 الجمهور', campaign_wizard_schedule: '⏰ الجدولة',
        running: 'جاري التنفيذ', completed: 'مكتملة', failed: 'فشلت',
        draft: 'مسودة', scheduled: 'مجدولة',
        active_campaigns: 'نشطة', new_campaign: '➕ حملة جديدة',
        no_campaigns: 'لا توجد حملات — أنشئ حملتك الأولى',
        total_reach: 'إجمالي الوصول',
        campaign_preview: '👁️ معاينة الحملة', launch_now: '🚀 إطلاق الآن',
        select_all: 'تحديد الكل', clear_all: 'مسح الكل',
        previous: 'السابق', next: 'التالي',
        // Post Composer
        post_composer_title: 'إنشاء منشور جديد',
        post_composer_subtitle: 'صيغة HTML مدعومة — أزرار Deep Link متاحة',
        content_type: 'نوع المحتوى',
        content_info: 'معلومة', content_question: 'سؤال', content_prediction: 'توقع',
        content_analysis: 'تحليل', content_live: 'مباشر', content_result: 'نتيجة',
        post_editor_placeholder: 'اكتب نص المنشور هنا... يدعم HTML للتيليغرام',
        dynamic_placeholders: ' marqueurs dynamiques',
        media_label: '📎 وسائط',
        deep_link_buttons: '🔗 أزرار Deep Link',
        deep_link_individual: 'فردي', deep_link_bulk: 'الجملة',
        bulk_import_hint: 'صق كلمات مع روابط — كل سطر: الكلمة | https://رابط',
        bulk_apply: 'تطبيق', bulk_cancel: 'إلغاء',
        btn_text_placeholder: 'نص الزر (الكلمة التسويقية)',
        add_button: 'إضافة زر',
        post_preview: 'معاينة المنشور', more_buttons: 'أزرار أخرى',
        target_channels: '📢 القنوات المستهدفة',
        select_all_channels: 'الكل', clear_selection: 'مسح',
        search_ellipsis: 'بحث...',
        channels_count: 'قناة', groups_count: 'مجموعة',
        groups_label: 'المجموعات',
        schedule_label: '⏰ الجدولة',
        schedule_immediate: '📤 فوري', schedule_timed: '📅 مجدول', schedule_cron: '🔄 كرون',
        cron_9am_daily: '9ص يومي', cron_9am_6pm: '9ص+6م', cron_every_3h: 'كل 3س', cron_workdays: 'أيام العمل',
        priority_label: '🏷️ الأولوية',
        priority_low: 'عاد', priority_normal: 'متوسط', priority_high: 'عالي',
        targets_selected: 'هدف محدد',
        publish_now: '📤 نشر الآن', schedule_action: '📅 جدولة', cron_action: '🔄 كرون',
        // AI Composer
        ai_generate: 'توليد بالـ AI',
        ai_compose_title: '✨ توليد بوست بالذكاء الاصطناعي',
        ai_compose_subtitle: 'اختر النوع والنبرة واترك الباقي على AI',
        ai_provider: 'مزود الـ AI',
        ai_content_type: 'نوع المحتوى',
        ai_channel_identity: 'هوية القناة / النبرة',
        ai_channel_identity_hint: 'مثال: قناة رياضية، قناة ترويجية، قناة أخبار',
        ai_user_note: 'ملاحظة إضافية (اختياري)',
        ai_user_note_hint: 'مثال: ركّز على مباراة الأهلي والزمالك، أضف إحصائيات...',
        ai_generated: 'تم التوليد بنجاح',
        ai_generating: 'جاري التوليد بالـ AI...',
        ai_use_result: 'استخدام في المحرر',
        ai_generate_btn: 'توليد',
        // Translation
        translate_btn: 'ترجمة',
        translate_title: '🌐 ترجمة البوست',
        translate_subtitle: 'اختر اللغة المطلوبة واترك الباقي على AI',
        translate_target: 'اللغة المطلوبة',
        translate_loading: 'جاري الترجمة...',
        translate_done: 'تمت الترجمة بنجاح',
        translate_apply: 'تطبيق الترجمة',
        // Platform preview
        select_platform: 'اختر المنصة',
        char_limit_warning: 'تجاوز الحد المسموح للمنصة',
        copy_text: 'نسخ', download: 'تحميل',
        silent_mode: 'وضع صامت', pin_message: 'تثبيت الرسالة',
        hashtags_count: 'هاشتاجات',
        location_tag: '标记 الموقع',
        link_preview: 'معاينة الرابط', preview_url: 'رابط المعاينة',
        add_tweet: 'إضافة تغريدة', poll: 'استطلاع', tweets: 'تغريدات',
        thread_builder: 'منشئ Thread', thread_info: 'افصل بين التغريدات بـ --- لبناء Thread',
        poll_creator: 'إنشاء استطلاع', poll_option: 'خيار', add_option: 'إضافة خيار',
        twitter_tips: 'نصائح Twitter/X', twitter_tips_text: 'الحد 280 حرف. الروابط = 23 حرف. الصور/GIF تُضاف تلقائياً. استخدم # للهاشتاجات.',
        api_posting: 'نشر عبر API', copy_posting: 'نسخ للنشر يدوياً', copy_and_post: 'نسخ والذهاب للنشر',
        content_story: '📱 Story', content_thread: '🧵 Thread', content_event: '📅 حدث',
        tg_editor_placeholder: 'اكتب منشورك هنا... (HTML مدعوم)', wa_editor_placeholder: 'اكتب رسالتك هنا... (Markdown مدعوم)',
        ig_editor_placeholder: 'اكتب كابشن هنا... (#hashtags مدعومة)', fb_editor_placeholder: 'اكتب منشورك هنا...',
        tw_editor_placeholder: 'اكتب تغريدتك هنا... (280 حرف)',
        ig_hashtag_helper: 'مساعد الهاشتاجات', ig_hashtag_tip: 'أضف هاشتاجات بـ # في نهاية البوست. Instagram يسمح بـ 30 هاشتاج.',
        ig_location_placeholder: 'مثال: Dubai, UAE',
    },
    en: {
        // Sidebar
        dashboard: 'Dashboard', transactions: 'Transactions', users: 'Users',
        transactions_label: 'Transactions',
        matching: 'Matching', svrp: 'Compensation', trading: 'Trading',
        agents: 'Matching Agents', clients: 'Clients (White-Label)', tickets: 'Tickets',
        user: 'User', no_results: 'No results',
        lottery: 'Lottery', wheel: 'Wheel of Fortune', companies: 'Companies',
        payment_methods: 'Payment Methods', apps: 'Apps', referrals: 'Referrals',
        channels: 'Channels', bots: 'Bots', complaints: 'Complaints',
        broadcast: 'Broadcast', statistics: 'Statistics', admins: 'Admin Management',
        themes: 'Themes', exchange_addresses: 'Exchange Addresses',
        send_message: 'Send Message', backup: 'Backup', settings: 'Settings',
        operations: 'Operations', management: 'Management', system: 'System',
        advanced_system: 'Advanced System',
        ai_api_keys: 'AI API Keys', ai_providers: 'AI Providers', ai_models: 'AI Models',
        // Navbar
        search_placeholder: 'Quick search... Ctrl+K', connected: 'Connected',
        notifications: 'Notifications', mark_read: 'Mark as read',
        no_notifications: 'No notifications', admin: 'Admin', logout: 'Logout',
        page_title: 'Dashboard', admin_panel: 'Admin Panel',
        // Common UI
        loading: 'Loading...', no_data: 'No data', save: 'Save',
        cancel: 'Cancel', delete: 'Delete', edit: 'Edit', add: 'Add',
        confirm: 'Confirm', search: 'Search', refresh: 'Refresh', back: 'Back',
        close: 'Close', approve: 'Approve', reject: 'Reject', export: 'Export',
        status: 'Status', date: 'Date', amount: 'Amount', type: 'Type',
        name: 'Name', id: 'ID', actions: 'Actions', total: 'Total',
        page: 'Page', of: 'of', previous: 'Previous', next: 'Next',
        all: 'All', pending: 'Pending', approved: 'Approved', rejected: 'Rejected',
        active: 'Active', inactive: 'Inactive', completed: 'Completed', cancelled: 'Cancelled',
        yes: 'Yes', no: 'No', phone: 'Phone', language: 'Language', currency: 'Currency',
        customer_id: 'Customer ID', company: 'Company', wallet: 'Wallet',
        deposit: 'Deposit', withdraw: 'Withdraw', balance: 'Balance', frozen: 'Frozen',
        available: 'Available', earned: 'Earned', verified: 'Verified', unverified: 'Unverified',
        // Dashboard
        total_users: 'Total Users', new_today: 'New Today',
        total_transactions: 'Total Transactions', pending_transactions: 'Pending Transactions',
        transaction_volume: 'Transaction Volume', today: 'Today', active_matches: 'Active Matches', pending_matches: 'Pending Matches',
        lottery_participants: 'Lottery Participants', wheel_players: 'Wheel Players',
        distributed: 'Distributed', pending_items: 'Pending Items',
        bulk_approve: 'Bulk Approve', bulk_reject: 'Bulk Reject',
        recent_transactions: 'Recent Transactions', recent_users: 'Recent Users',
        view_all: 'View All', recent_activity: 'Recent Activity',
        tx_distribution: 'Transaction Status Distribution', tx_last_30: 'Transactions Last 30 Days',
        // Transactions
        tx_id: 'Transaction ID', client: 'Client', tx_type: 'Type',
        tx_company: 'Company', tx_amount: 'Amount', tx_status: 'Status',
        tx_date: 'Date', tx_actions: 'Actions', auto_update: 'Auto Update',
        min_amount: 'Min Amount', max_amount: 'Max Amount', date_from: 'From Date',
        date_to: 'To Date', export_csv: 'Export CSV', select_all: 'Select All',
        approve_modal_title: 'Approve Transaction', amount_editable: 'Amount (editable)',
        approve_confirm: 'Approve & Confirm Amount', reject_reason: 'Reject Reason',
        // Users
        user_search: 'Search by name/phone/ID', banned: 'Banned', ban: 'Ban',
        unban: 'Unban', ban_reason: 'Ban Reason', profile: 'Profile',
        registration_date: 'Registration Date', user_transactions: 'User Transactions',
        svrp_wallet: 'SVRP Wallet', company_accounts: 'Company Accounts',
        // Matching
        active_matches_tab: 'Active', pending_requests_tab: 'Pending', logs_tab: 'Logs',
        match_id: 'Match ID', depositor: 'Depositor', withdrawer: 'Withdrawer',
        // Channels
        add_channel: 'Add Channel', channel_title: 'Channel Name',
        chat_id: 'Chat ID', channel_type: 'Type', channel: 'Channel', group: 'Group',
        supergroup: 'Supergroup', category: 'Category', relay_to_users: 'To Users',
        relay_to_channels: 'To Channels', ai_enabled: 'AI Enabled', send_message_btn: 'Send',
        post_vault: 'Archive', ai_settings: 'AI Settings', daily_report: 'Daily Report',
        source_channels: 'Source Channels', uncategorized: 'Uncategorized',
        // SVRP
        svrp_wallets: 'Wallets', recovery_requests: 'Recovery Requests',
        bonus_requests: 'Bonus Requests', promo_codes: 'Promo Codes',
        // Lottery
        lottery_rounds: 'Lottery Rounds', tickets_sold: 'Tickets Sold',
        participants: 'Participants', winners: 'Winners', prize_pool: 'Prize Pool',
        draw_time: 'Draw Time', ticket_price: 'Ticket Price',
        // Settings
        system_settings: 'System Settings', button_labels: 'Button Labels',
        audit_log: 'Audit Log', setting_key: 'Key', setting_value: 'Value',
        // Dashboard extras
        trading_orders: 'Trading Orders', pending_trading: 'Pending Trading',
        pending_svrp: 'Pending Compensation', load_failed: 'Failed to load',
        no_transactions: 'No transactions', no_users: 'No users', no_activity: 'No activity',
        bulk_approve_txns: 'Bulk Approve Transactions',
        bulk_reject_txns: 'Bulk Reject Transactions',
        top_companies: 'Top 5 Companies by Volume',
        user_registrations: 'User Registrations (14 days)',
        confirm_bulk_approve: 'Bulk approve all pending transactions?',
        confirm_bulk_reject: 'Reject all pending transactions?',
        bulk_approved: 'Bulk approved', operation_failed: 'Operation failed',
        bulk_rejected: 'Bulk rejected', admin_id: 'Admin ID',
        enter_admin_id: 'Enter Admin ID', password: 'Password', login: 'Login',
        login_title: 'Login — Boterx', all_rights: 'All rights reserved',
        search_dots: 'Search...', manager: 'Manager', general_manager: 'General Manager',
        switch_to_arabic: 'Switch to Arabic', last_activity: 'Last activity:',
        total_amount: 'Total Amount', avg_amount: 'Average Amount',
        approved_volume: 'Approved Volume', all_types: 'All Types',
        selected: 'Selected', deselect_all: 'Deselect All',
        txn_details: 'Transaction Details', client_name: 'Client Name',
        admin_note: 'Admin Note', phone_number: 'Phone Number',
        banned_count: 'Banned', verified_phones: 'Verified Phones',
        user_search_placeholder: 'Search by name/phone/customer ID/Telegram ID...',
        not_banned: 'Not Banned', user_details: 'User Details',
        phone_verified: 'Phone Verified', pending_balance: 'Pending',
        total_earned: 'Total Earned', freeze_balance: 'Freeze Balance',
        unfreeze_balance: 'Unfreeze', ban_user: 'Ban User', confirm_ban: 'Confirm Ban',
        user_banned: 'User banned', ban_failed: 'Ban failed',
        unban_user: 'Unban User', user_unbanned: 'User unbanned', updated: 'Updated',
        update_failed: 'Update failed', confirm_freeze: 'Freeze all user balance?',
        unfreeze_amount: 'Amount to unfreeze?', balance_frozen: 'Balance frozen',
        freeze_failed: 'Freeze failed', balance_unfrozen: 'Balance unfrozen',
        channels_groups: 'Channels & Groups', channels_tab: 'Channels', groups_tab: 'Groups',
        archive: 'Archive', active_count: 'Active', categories: 'Categories',
        unknown: 'Unknown', send: 'Send', add_channel_group: 'Add Channel / Group',
        channel_name: 'Channel Name', channel_example: 'Example: News Channel',
        not_enabled: 'Not Enabled', ai_instructions: 'AI Instructions', test: 'Test',
        text_replace: 'Text Replacement', find_text: 'Search for...',
        replace_with: 'Replace with...', today_posts: 'Today Posts',
        ai_processed: 'AI Processed', users_reached: 'Users Reached',
        active_channels: 'Active Channels', recent_relays: 'Recent Relays',
        source: 'Source', preview: 'Preview', users_count: 'Users',
        channels_count: 'Channels', no_settings: 'No settings',
        original_text: 'Original Text', new_text: 'New Text',
        no_button_labels: 'No button labels', no_audit_log: 'No audit logs yet',
        total_complaints: 'Total Complaints', open_complaints: 'Open Complaints',
        resolved: 'Resolved', message_text: 'Message', admin_reply: 'Admin Reply',
        no_complaints: 'No complaints', reply_to_complaint: 'Reply to Complaint',
        original_message: 'Original message:', write_reply_here: 'Write your reply here...',
        replied: 'Replied', admin_management: 'Admin Management',
        manage_admins: 'Manage Administrators', admin_management_desc: 'Add, remove, and edit admin permissions',
        add_admin: 'Add Admin', permanent: 'Permanent', temporary: 'Temporary',
        full_access: 'Full Access', full_permission: 'Full Permission',
        support: 'Support', telegram_id: 'Telegram ID', role: 'Role',
        no_admins_yet: 'No admins yet', add_new_admin: 'Add New Admin',
        admin_name: 'Admin Name', duration_hours: 'Duration (hours)',
        leave_empty_permanent: 'Leave empty for permanent', expiry_date: 'Expiry Date',
        assign_role: 'Assign Role', admin_label: 'Admin:', new_role: 'New Role',
        confirm_removal: 'Confirm Removal', confirm_remove_admin: 'Are you sure you want to remove',
        from_admins: 'from admins?', permissions_revoked: 'All permissions will be revoked immediately.',
        remove: 'Remove', broadcast_message: 'Broadcast Message',
        send_to_all: 'Send message to all users', message_type: 'Message Type',
        image: 'Image', video: 'Video', message_text_label: 'Message Text',
        write_message_here: 'Write message here...', broadcast_queued: 'Message will be added to broadcast queue',
        send_broadcast: 'Send Broadcast', sending: 'Sending...', preview_label: 'Preview:',
        detailed_stats: 'Detailed Statistics', stats_description: 'Comprehensive analysis of system performance, transactions, and users',
        this_week: 'This Week', this_month: 'This Month',
        avg_transaction: 'Average Transaction', completion_rate: 'Completion Rate',
        transactions_over_time: 'Transactions Over Time', tx_type_distribution: 'Transaction Type Distribution',
        user_growth: 'User Growth', top_users: 'Top 10 Users by Transactions',
        complaints_stats: 'Complaints Statistics', resolution_rate: 'Resolution Rate',
        resolution_progress: 'Resolution Progress', loading_stats: 'Loading statistics...',
        stats_load_failed: 'Failed to load statistics', new_users: 'New Users',
        notifications_title: 'Notifications', time: 'Time', total_users_label: 'Total Users',
        dispute: 'Dispute', open: 'Open', auto_rejected: 'Auto Rejected',
        withdrawal_rejected: 'Withdrawal Rejected', pending_withdrawal: 'Pending Withdrawal',
        pending_code_verification: 'Awaiting Code', muted: 'Muted', click_to_open: 'Click to go',
        // AI API Keys page
        add_api_key: 'Add API Key', provider: 'Provider', api_key: 'API Key',
        model: 'Model', is_active: 'Active', priority: 'Priority',
        base_url: 'Base URL', api_key_placeholder: 'sk-... or provider-specific key',
        model_placeholder: 'e.g., gpt-4o, claude-3-5-sonnet, gemini-1.5-pro',
        test_connection: 'Test Connection', connection_success: 'Connection successful',
        connection_failed: 'Connection failed', edit_key: 'Edit Key', delete_key: 'Delete Key',
        no_keys_yet: 'No keys yet — add your first API key',
        key_name: 'Key Name', key_name_placeholder: 'e.g., OpenAI Main, Anthropic Backup',
        provider_openai: 'OpenAI', provider_anthropic: 'Anthropic', provider_google: 'Google (Gemini)',
        provider_azure: 'Azure OpenAI', provider_custom: 'Custom',
        models_fetched: 'Models fetched', fetch_models: 'Fetch Models',
        auto_fetch_models: 'Auto-fetch models', models_list: 'Models List',
        default_model: 'Default Model', temperature: 'Temperature',
        max_tokens: 'Max Tokens', timeout_seconds: 'Timeout (seconds)',
        provider_info: 'Provider Info', api_docs_link: 'API Docs Link',
        key_validated: 'Key is valid', key_invalid: 'Key is invalid',
        usage_stats: 'Usage Stats', requests_today: 'Requests Today',
        tokens_today: 'Tokens Today', cost_estimate_usd: 'Estimated Cost (USD)',
        // Channels page
        campaigns_tab: 'Campaigns', channels_tab: 'Channels', groups_tab: 'Groups',
        vault_tab: 'Vault', ai_tab: 'AI', report_tab: 'Report',
        analytics_tab: 'Analytics', ainet_tab: 'Network',
        total_partners: 'Total Partners', active_partners: 'Active Partners',
        total_subscribers: 'Total Subscribers', cpm: 'CPM', total_revenue: 'Total Revenue',
        new_partner: 'New Partner', add_channel: 'Add Channel',
        enable: 'Enable', for_users: 'For Users', for_channels: 'For Channels',
        platform: 'Platform', role: 'Role', source_publish: 'Source + Publish',
        source_only: 'Source only', publish_only: 'Publish only',
        ai_agent: 'AI Agent', platform_account: 'Platform Account',
        owner_admin_id: 'Owner Admin ID', manager_admin_ids: 'Manager Admin IDs',
        allow_subadmin_publish: 'Allow Subadmin Publish', category: 'Category',
        send: 'Send', cancel: 'Cancel', add: 'Add', launch_now: 'Launch Now',
        schedule_campaign: 'Schedule Campaign',
        channel_name: 'Channel Name', chat_id: 'Chat ID', type: 'Type',
        channel: 'Channel', group: 'Group', supergroup: 'Supergroup',
        platform: 'Platform', channel_role: 'Role', owner_admin_id: 'Owner Admin ID',
        manager_admin_ids: 'Manager Admin IDs', category: 'Category',
        sports: 'Sports', finance: 'Finance', trading: 'Trading', games: 'Games',
        news: 'News', marketing: 'Marketing', entertainment: 'Entertainment', other: 'Other',
        uncategorized: 'Uncategorized',
        create_group: 'Create Group', group_name: 'Group Name',
        group_description: 'Group Description', create: 'Create',
        vault_date: 'Date', vault_provider: 'Provider',
        vault_original: 'Original', vault_processed: 'Processed', vault_actions: 'Actions',
        ai_instructions: 'AI Instructions', test: 'Test',
        ai_agents: 'AI Agents', add_agent: 'Add Agent',
        platform_accounts: 'Platform Accounts', add_account: 'Add Account',
        source_channels: 'Source Channels', add_source: 'Add Source',
        today_posts: 'Today Posts', ai_processed: 'AI Processed',
        users_reached: 'Users Reached', active_channels: 'Active Channels',
        source: 'Source', preview: 'Preview', users_count: 'Users',
        channels_count: 'Channels', actions: 'Actions',
        // General terms (legacy audit keys)
        active_players: 'Active Players', add_game: 'Add Game',
        algorithm_config: 'Algorithm Config', compensation_interval: 'Compensation Interval',
        config: 'Config', cur_aed: 'AED', cur_current: 'Current Currency',
        cur_egp: 'EGP', cur_kwd: 'KWD', cur_sar: 'SAR', cur_title: 'Currency',
        cur_usd: 'USD', cur_usdt: 'USDT', err_generic: 'Generic error', games: 'Games',
        hero_badge: 'Hero Badge', hero_cta_games: 'Browse Games', hero_cta_login: 'Log In',
        hero_cta_play: 'Play Now', hero_p: 'Hero Description',
        hub_champions: 'Champions', hub_loading: 'Loading...', hub_my_account: 'My Account',
        hub_my_wallet: 'My Wallet', hub_no_games: 'No Games', hub_num: 'Number',
        max_bets_hour: 'Max Bets/Hour', max_daily_loss: 'Max Daily Loss',
        max_daily_win: 'Max Daily Win', min_balance: 'Min Balance',
        nav_account: 'Account', nav_play_now: 'Play Now', net_profit: 'Net Profit',
        no_pending_deposits: 'No Pending Deposits', pending_deposits: 'Pending Deposits',
        platform_edge: 'Platform Edge', players: 'Players', risk_alerts: 'Risk Alerts',
        seg_churning: 'Churning', seg_hot: 'Hot', seg_loser: 'Loser',
        seg_new: 'New', seg_regular: 'Regular', seg_vip: 'VIP', seg_winner: 'Winner',
        stat_always: 'Always Available', stat_games_diff: 'Different Games',
        stat_paid: 'Prizes Paid', stat_users: 'Registered Users',
        tag_daily: 'Daily', tag_instant: 'Instant', tag_online: 'Online', tag_secure: 'Secure',
        target_edge: 'Target Edge', ticker_label: 'Live Ticker', total_wagered: 'Total Wagered',
        wdr_acc_ph: 'Account/Wallet', wdr_amt_ph: 'Amount', wdr_choose: 'Choose Method',
        wdr_confirm: 'Confirm Withdrawal', wdr_enter_both: 'Enter both account and amount',
        wdr_or_manual: 'Or enter manually', wdr_pending: 'Pending Review',
        wdr_requested: 'Withdrawal Requested', wdr_title: 'Withdraw', wdr_your_bal: 'Your Balance',
        // ===== Broadcast & Social (v20260826) =====
        copy_permanent_link: 'Copy Permanent Demo Link',
        broadcast_all: 'Bulk Broadcast', broadcast_single: 'Single Broadcast',
        broadcast_to_all_agents: 'Broadcast to all agents', broadcast_to_all_channels: 'Broadcast to all channels',
        all_users: 'All Users', specific_user: 'Specific user',
        both_channels: 'Both', clear_selection: 'Clear Selection',
        target_countries: 'Target Countries', target_countries_label: 'Target Countries (multiple)',
        target_agents: 'Target Agents', target_platforms: 'Social Media Platforms',
        target_platforms_label: 'Social Media Platforms',
        social_platforms: 'Social Media Platforms',
        telegram: 'Telegram', whatsapp: 'WhatsApp', facebook: 'Facebook', instagram: 'Instagram',
        twitter: 'Twitter/X', tiktok: 'TikTok', youtube: 'YouTube', linkedin: 'LinkedIn',
        web: 'Website',
        // Channels / social
        social_tab: 'Social', campaigns_tab: 'Campaigns', network_tab: 'Network',
        add_social_account: 'Add Social Account', no_social_accounts: 'No social media accounts — add the first one',
        account_name: 'Account Name', handle: 'Handle', platform_account: 'Platform Account',
        access_token: 'Access Token', page_id: 'Page ID', business_account_id: 'Business Account ID',
        phone_number_id: 'Phone Number ID', subscriber_count: 'Subscriber Count',
        followers: 'Followers', contact: 'Contact', confirm_delete: 'Confirm Delete',
        campaign_name: 'Campaign Name', content_categories: 'Content Categories',
        posting_permissions: 'Posting Permissions', sub_agent: 'Sub-Agent',
        sub_agents_connected: 'Sub-agents connected', platforms_connected: 'Connected platforms',
        active_accounts: 'Active accounts', total_accounts: 'Total accounts',
        total_campaigns: 'Total campaigns', total_reach: 'Total reach',
        total_clicks: 'Total clicks', ctr: 'Click rate (CTR)', conversions: 'Conversions',
        clicks: 'Clicks', reach: 'Reach', daily_reach: 'Daily reach',
        last_sync: 'Last sync', revenue_share: 'Revenue Share',
        top_campaigns: 'Top Campaigns', pending_matches: 'Pending Matches',
        // Campaign wizard
        create_campaign: '📊 Create Ad Campaign',
        campaign_wizard_content: '💬 Content', campaign_wizard_platform: '🎯 Platform',
        campaign_wizard_audience: '👥 Audience', campaign_wizard_schedule: '⏰ Schedule',
        running: 'Running', completed: 'Completed', failed: 'Failed',
        draft: 'Draft', scheduled: 'Scheduled',
        active_campaigns: 'Active', new_campaign: '➕ New Campaign',
        no_campaigns: 'No campaigns — create your first one',
        total_reach: 'Total Reach',
        campaign_preview: '👁️ Campaign Preview', launch_now: '🚀 Launch Now',
        select_all: 'Select All', clear_all: 'Clear All',
        previous: 'Previous', next: 'Next',
        // Post Composer
        post_composer_title: 'Create New Post',
        post_composer_subtitle: 'HTML supported — Deep Link buttons available',
        content_type: 'Content Type',
        content_info: 'Info', content_question: 'Question', content_prediction: 'Prediction',
        content_analysis: 'Analysis', content_live: 'Live', content_result: 'Result',
        post_editor_placeholder: 'Write post text here... supports HTML for Telegram',
        dynamic_placeholders: 'Dynamic Placeholders',
        media_label: '📎 Media',
        deep_link_buttons: '🔗 Deep Link Buttons',
        deep_link_individual: 'Individual', deep_link_bulk: 'Bulk',
        bulk_import_hint: 'Paste keywords with links — each line: keyword | https://link',
        bulk_apply: 'Apply', bulk_cancel: 'Cancel',
        btn_text_placeholder: 'Button text (marketing keyword)',
        add_button: 'Add Button',
        post_preview: 'Post Preview', more_buttons: 'more buttons',
        target_channels: '📢 Target Channels',
        select_all_channels: 'All', clear_selection: 'Clear',
        search_ellipsis: 'Search...',
        channels_count: 'channels', groups_count: 'groups',
        groups_label: 'Groups',
        schedule_label: '⏰ Schedule',
        schedule_immediate: '📤 Immediate', schedule_timed: '📅 Scheduled', schedule_cron: '🔄 Cron',
        cron_9am_daily: '9AM Daily', cron_9am_6pm: '9AM+6PM', cron_every_3h: 'Every 3h', cron_workdays: 'Workdays',
        priority_label: '🏷️ Priority',
        priority_low: 'Low', priority_normal: 'Normal', priority_high: 'High',
        targets_selected: 'targets selected',
        publish_now: '📤 Publish Now', schedule_action: '📅 Schedule', cron_action: '🔄 Cron',
        // AI Composer
        ai_generate: 'AI Generate',
        ai_compose_title: '✨ AI Post Composer',
        ai_compose_subtitle: 'Choose type & tone, let AI write the rest',
        ai_provider: 'AI Provider',
        ai_content_type: 'Content Type',
        ai_channel_identity: 'Channel Identity / Tone',
        ai_channel_identity_hint: 'e.g. sports channel, promo channel, news channel',
        ai_user_note: 'Additional Note (optional)',
        ai_user_note_hint: 'e.g. focus on Al-Ahly vs Zamalek match, add stats...',
        ai_generated: 'Generated successfully',
        ai_generating: 'Generating with AI...',
        ai_use_result: 'Use in Editor',
        ai_generate_btn: 'Generate',
        // Translation
        translate_btn: 'Translate',
        translate_title: '🌐 Translate Post',
        translate_subtitle: 'Choose target language, let AI handle the rest',
        translate_target: 'Target Language',
        translate_loading: 'Translating...',
        translate_done: 'Translation complete',
        translate_apply: 'Apply Translation',
        // Platform preview
        select_platform: 'Select Platform',
        char_limit_warning: 'Exceeds platform character limit',
        copy_text: 'Copy', download: 'Download',
        silent_mode: 'Silent', pin_message: 'Pin',
        hashtags_count: 'Hashtags',
        location_tag: 'Location',
        link_preview: 'Link Preview', preview_url: 'Preview URL',
        add_tweet: 'Add Tweet', poll: 'Poll', tweets: 'Tweets',
        thread_builder: 'Thread Builder', thread_info: 'Separate tweets with --- to build a Thread',
        poll_creator: 'Create Poll', poll_option: 'Option', add_option: 'Add Option',
        twitter_tips: 'Twitter/X Tips', twitter_tips_text: '280 char limit. URLs = 23 chars. Images/GIF auto-attached. Use # for hashtags.',
        api_posting: 'Post via API', copy_posting: 'Copy to Post', copy_and_post: 'Copy & Go Post',
        content_story: '📱 Story', content_thread: '🧵 Thread', content_event: '📅 Event',
        tg_editor_placeholder: 'Write your post here... (HTML supported)', wa_editor_placeholder: 'Write your message here... (Markdown supported)',
        ig_editor_placeholder: 'Write your caption here... (#hashtags supported)', fb_editor_placeholder: 'Write your post here...',
        tw_editor_placeholder: 'Write your tweet here... (280 chars)',
        ig_hashtag_helper: 'Hashtag Helper', ig_hashtag_tip: 'Add hashtags with # at end of post. Instagram allows 30 hashtags.',
        ig_location_placeholder: 'e.g. Dubai, UAE',
        smart_posting_monitor: 'Smart Posting Monitor',
        posting_pending: 'Pending', posting_channels_today: 'Channels posted today',
        posting_total_today: 'Total posts today', posting_sent: 'Sent',
        parent_group: 'Parent Group', sub_groups: 'Sub-groups',
        create_group: 'Create Group', no_groups: 'No groups', refresh: 'Refresh',
    }
};

// Global translation function
function tr(key) {
    const lang = localStorage.getItem('lang') || 'ar';
    const dict = I18N[lang] || I18N.ar;
    // Key-based dict lookup ONLY — passing text through the lexicon
    // translator corrupted UI text (e.g. "dashboard" -> "dبشكلhboard")
    return dict[key] || I18N.ar[key] || key;
}

// Apply language to document
function applyDocumentLang() {
    const lang = localStorage.getItem('lang') || 'ar';
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
}

// Apply on load
document.addEventListener('DOMContentLoaded', () => {
    applyDocumentLang();
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = tr(el.getAttribute('data-i18n'));
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = tr(el.getAttribute('data-i18n-placeholder'));
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
        el.placeholder = tr(el.getAttribute('data-i18n-ph'));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        el.title = tr(el.getAttribute('data-i18n-title'));
    });
});

// ===== API helper =====
async function api(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = { ...options.headers };
    if (method !== 'GET' && method !== 'HEAD') {
        headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(url, {
        ...options,
        method,
        credentials: 'same-origin',
        headers
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

// ===== Status badge =====
function statusBadge(status) {
    const map = {
        'pending': '<span class="badge badge-pending">' + tr('pending') + '</span>',
        'approved': '<span class="badge badge-approved">' + tr('approved') + '</span>',
        'rejected': '<span class="badge badge-rejected">' + tr('rejected') + '</span>',
        'active': '<span class="badge badge-active">' + tr('active') + '</span>',
        'inactive': '<span class="badge badge-cancelled">' + tr('inactive') + '</span>',
        'completed': '<span class="badge badge-completed">' + tr('completed') + '</span>',
        'cancelled': '<span class="badge badge-cancelled">' + tr('cancelled') + '</span>',
        'waiting': '<span class="badge badge-pending">' + tr('pending') + '</span>',
        'matched': '<span class="badge badge-active">' + tr('active') + '</span>',
        'code_verified': '<span class="badge badge-approved">' + tr('approved') + '</span>',
        'awaiting_admin_review': '<span class="badge badge-pending">' + tr('pending') + '</span>',
        'admin_received': '<span class="badge badge-approved">' + tr('approved') + '</span>',
        'transfer_confirmed': '<span class="badge badge-approved">' + tr('approved') + '</span>',
        'disputed': '<span class="badge badge-rejected">' + tr('dispute') + '</span>',
        'resolved': '<span class="badge badge-approved">' + tr('approved') + '</span>',
        'open': '<span class="badge badge-pending">' + tr('open') + '</span>',
        'yes': '<span class="badge badge-approved">' + tr('yes') + '</span>',
        'no': '<span class="badge badge-rejected">' + tr('no') + '</span>',
        'auto_rejected': '<span class="badge badge-rejected">' + tr('auto_rejected') + '</span>',
        'withdrawal_rejected': '<span class="badge badge-rejected">' + tr('withdrawal_rejected') + '</span>',
        'withdrawal_auto_rejected': '<span class="badge badge-rejected">' + tr('auto_rejected') + '</span>',
        'pending_withdrawal': '<span class="badge badge-pending">' + tr('pending_withdrawal') + '</span>',
        'pending_code_verification': '<span class="badge badge-pending">' + tr('pending_code_verification') + '</span>',
    };
    return map[status] || '<span class="badge" style="background:#334155;color:#94A3B8">' + (status || '—') + '</span>';
}

function fmtNum(n) { const l = localStorage.getItem('lang') || 'ar'; return (n || 0).toLocaleString(l === 'ar' ? 'ar-EG' : 'en-US'); }
function fmtAmount(n, currency = '') { const l = localStorage.getItem('lang') || 'ar'; return (n || 0).toLocaleString(l === 'ar' ? 'ar-EG' : 'en-US', {maximumFractionDigits: 2}) + ' ' + currency; }
function esc(text) { const d = document.createElement('div'); d.textContent = text || ''; return d.innerHTML; }

// ===== Toast =====
function toast(message, type = 'info') {
    const colors = { info: 'bg-blue-600', success: 'bg-green-600', error: 'bg-red-600', warning: 'bg-amber-600' };
    const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
    const c = document.getElementById('toastContainer') || createToastContainer();
    const t = document.createElement('div');
    t.className = colors[type] + ' text-white px-4 py-3 rounded-lg shadow-2xl text-sm flex items-center gap-2 mb-2 min-w-[250px]';
    t.innerHTML = '<span>' + icons[type] + '</span> ' + message;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity 0.3s'; setTimeout(() => t.remove(), 300); }, 3500);
}
function createToastContainer() { const c = document.createElement('div'); c.id = 'toastContainer'; c.className = 'fixed bottom-4 left-4 z-[300] flex flex-col'; document.body.appendChild(c); return c; }

// ===== Notifier =====
const Notifier = {
    enabled: true, soundEnabled: true, audioContext: null,
    lastPendingCount: 0, lastMatchCount: 0, lastComplaintsCount: 0,
    lastTradingCount: 0, lastSvrpCount: 0, lastLotteryCount: 0,
    lastWheelCount: 0, lastNewUsers: 0,

    init() {
        this.soundEnabled = localStorage.getItem('boterx_sound') !== 'false';
        this.enabled = localStorage.getItem('boterx_notif') !== 'false';
        document.addEventListener('click', () => {
            if (!this.audioContext) this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }, { once: true });
    },
    toggleSound() {
        this.soundEnabled = !this.soundEnabled;
        localStorage.setItem('boterx_sound', this.soundEnabled);
        toast(this.soundEnabled ? '🔊 ' + tr('connected') : '🔇 ' + tr('muted'), 'info');
    },
    async check() {
        try {
            const res = await api('/api/stats');
            if (res.status === 401 || res.status === 403) {
                if (this._timer) { clearInterval(this._timer); this._timer = null; }
                return;
            }
            const stats = await res.json();
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
                if (stats.users?.total) parts.push('👥 ' + fmtNum(stats.users.total));
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
            item.innerHTML = '<span>' + message + '</span> <span class="text-xs text-slate-500">' + (window.__ADMIN_CLOCK__ || new Date()).toLocaleTimeString() + '</span>';
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
            'new_trade': { bg: 'bg-amber-600', icon: '💱', url: '/games' },
            'new_svrp': { bg: 'bg-purple-600', icon: '💎', url: '/games' },
            'new_lottery': { bg: 'bg-amber-600', icon: '🎰', url: '/games' },
            'new_wheel': { bg: 'bg-blue-600', icon: '🎡', url: '/games' },
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
                bassGain.gain.setValueAtTime(0.4, now);
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
                    gain.gain.setValueAtTime(0.3, now + i * 0.4);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.4 + 0.35);
                    osc.start(now + i * 0.4); osc.stop(now + i * 0.4 + 0.35);
                }
            }
        } catch (e) {}
    },
    playSuccessSound() { this.playSound('success'); },
};

function requestNotificationPermission() {
    if (Notification.permission === 'default') Notification.requestPermission();
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const s = document.getElementById('globalSearch');
        if (s) s.focus();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        Notifier.toggleSound();
    }
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    Notifier.init();
    requestNotificationPermission();
    Notifier._timer = setInterval(() => Notifier.check(), 5000);
    Notifier.check();
    document.addEventListener('click', requestNotificationPermission, { once: true });
});

// Global search
function globalSearchApp() {
    return {
        query: '', results: [], loading: false, showResults: false,
        async search() {
            if (this.query.length < 2) { this.results = []; return; }
            this.loading = true;
            const q = this.query.toLowerCase(), results = [];
            try {
                const txnRes = await fetch('/api/transactions?search=' + encodeURIComponent(this.query) + '&per_page=5');
                const txnData = await txnRes.json();
                (txnData.transactions || []).forEach(t => {
                    results.push({ type: tr('transactions'), icon: t.type === 'deposit' ? '💵' : '💸',
                        title: t.name + ' — ' + t.amount + ' ' + (t.currency || ''), subtitle: t.id + ' | ' + t.company, url: '/transactions' });
                });
                const userRes = await fetch('/api/users?search=' + encodeURIComponent(this.query) + '&per_page=5');
                const userData = await userRes.json();
                (userData.users || []).forEach(u => {
                    results.push({ type: tr('users'), icon: '👤', title: u.name + ' — ' + (u.customer_id || ''),
                        subtitle: (u.phone || '') + ' | ' + (u.currency || ''), url: '/users' });
                });
            } catch(e) {}
            this.results = results.slice(0, 10);
            this.loading = false;
        }
    }
}
/* Boterx Dashboard — App JS v4 — Full Bilingual */

// ===== Global i18n Dictionary =====
const I18N = {
    ar: {
        // Sidebar
        dashboard: 'لوحة التحكم', transactions: 'المعاملات', users: 'المستخدمين',
        transactions_label: 'المعاملات',
        matching: 'المطابقات', svrp: 'التعويض', trading: 'التداول',
        lottery: 'اليانصيب', wheel: 'عجلة الحظ', companies: 'الشركات',
        payment_methods: 'وسائل الدفع', apps: 'التطبيقات', referrals: 'الإحالات',
        channels: 'القنوات', bots: 'البوتات', complaints: 'الشكاوى',
        broadcast: 'بث رسالة', statistics: 'الإحصائيات', admins: 'إدارة الأدمن',
        themes: 'الثيمات', exchange_addresses: 'عناوين الصرافة',
        send_message: 'رسالة لمستخدم', backup: 'النسخ الاحتياطي', settings: 'الإعدادات',
        operations: 'العمليات', management: 'الإدارة', system: 'النظام',
        advanced_system: 'النظام المتقدم',
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
        transaction_volume: 'حجم المعاملات', today: 'اليوم', active_matches: 'مطابقات نشطة',
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
        // Sidebar
        dashboard: 'لوحة التحكم', transactions: 'المعاملات', users: 'المستخدمين',
        transactions_label: 'المعاملات',
        matching: 'المطابقات', svrp: 'التعويض', trading: 'التداول',
        lottery: 'اليانصيب', wheel: 'عجلة الحظ', companies: 'الشركات',
        payment_methods: 'وسائل الدفع', apps: 'التطبيقات', referrals: 'الإحالات',
        channels: 'القنوات', bots: 'البوتات', complaints: 'الشكاوى',
        broadcast: 'بث رسالة', statistics: 'الإحصائيات', admins: 'إدارة الأدمن',
        themes: 'الثيمات', exchange_addresses: 'عناوين الصرافة',
        send_message: 'رسالة لمستخدم', backup: 'النسخ الاحتياطي', settings: 'الإعدادات',
        operations: 'العمليات', management: 'الإدارة', system: 'النظام',
        advanced_system: 'النظام المتقدم',
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
        total_users: 'Total Users', new_today: 'New Today',
        total_transactions: 'Total Transactions', pending_transactions: 'Pending Transactions',
        transaction_volume: 'Transaction Volume', today: 'Today', active_matches: 'Active Matches',
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
        trading_orders: 'Trading Orders',
        pending_matches: 'Pending Matches',
        pending_trading: 'Pending Trading',
        pending_svrp: 'Pending Compensation',
        load_failed: 'Failed to load',
        no_transactions: 'No transactions', no_users: 'No users', no_activity: 'No activity',
        bulk_approve_txns: 'Bulk Approve Transactions',
        bulk_reject_txns: 'Bulk Reject Transactions',
        top_companies: 'Top 5 Companies by Volume',
        user_registrations: 'User Registrations (14 days)',
        confirm_bulk_approve: 'Bulk approve all pending transactions?',
        confirm_bulk_reject: 'Reject all pending transactions?',
        bulk_approved: 'Bulk approved',
        operation_failed: 'Operation failed',
        bulk_rejected: 'Bulk rejected',
        admin_id: 'Admin ID',
        enter_admin_id: 'Enter Admin ID',
        password: 'Password',
        login: 'Login',
        login_title: 'Login — Boterx',
        all_rights: 'All rights reserved',
        search_dots: 'Search...',
        manager: 'Manager',
        general_manager: 'General Manager',
        switch_to_arabic: 'Switch to Arabic',
        last_activity: 'Last activity:',
        total_amount: 'Total Amount',
        avg_amount: 'Average Amount',
        approved_volume: 'Approved Volume',
        all_types: 'All Types',
        selected: 'Selected',
        deselect_all: 'Deselect All',
        txn_details: 'Transaction Details',
        client_name: 'Client Name',
        admin_note: 'Admin Note',
        phone_number: 'Phone Number',
        banned_count: 'Banned',
        verified_phones: 'Verified Phones',
        user_search_placeholder: 'Search by name/phone/customer ID/Telegram ID...',
        not_banned: 'Not Banned',
        user_details: 'User Details',
        phone_verified: 'Phone Verified',
        pending_balance: 'Pending',
        total_earned: 'Total Earned',
        freeze_balance: 'Freeze Balance',
        unfreeze_balance: 'Unfreeze',
        ban_user: 'Ban User',
        confirm_ban: 'Confirm Ban',
        user_banned: 'User banned',
        ban_failed: 'Ban failed',
        unban_user: 'Unban User',
        user_unbanned: 'User unbanned',
        updated: 'Updated',
        update_failed: 'Update failed',
        confirm_freeze: 'Freeze all user balance?',
        unfreeze_amount: 'How much to unfreeze?',
        balance_frozen: 'Balance frozen',
        freeze_failed: 'Freeze failed',
        balance_unfrozen: 'Balance unfrozen',
        channels_groups: 'Channels & Groups',
        channels_tab: 'Channels',
        groups_tab: 'Groups',
        archive: 'Archive',
        active_count: 'Active',
        categories: 'Categories',
        unknown: 'Unknown',
        send: 'Send',
        add_channel_group: 'Add Channel / Group',
        channel_name: 'Channel Name',
        channel_example: 'Example: News Channel',
        not_enabled: 'Not Enabled',
        ai_instructions: 'AI Instructions',
        test: 'Test',
        text_replace: 'Text Replacement',
        find_text: 'Search for...',
        replace_with: 'Replace with...',
        today_posts: 'Today Posts',
        ai_processed: 'AI Processed',
        users_reached: 'Users Reached',
        active_channels: 'Active Channels',
        recent_relays: 'Recent Relays',
        source: 'Source',
        preview: 'Preview',
        users_count: 'Users',
        channels_count: 'Channels',
        no_settings: 'No settings',
        original_text: 'Original Text',
        new_text: 'New Text',
        no_button_labels: 'No button labels',
        no_audit_log: 'No audit logs yet',
        total_complaints: 'Total Complaints',
        open_complaints: 'Open Complaints',
        resolved: 'Resolved',
        message_text: 'Message',
        admin_reply: 'Admin Reply',
        no_complaints: 'No complaints',
        reply_to_complaint: 'Reply to Complaint',
        original_message: 'Original message:',
        write_reply_here: 'Write your reply here...',
        replied: 'Replied',
        admin_management: 'Admin Management',
        manage_admins: 'Manage Administrators',
        admin_management_desc: 'Add, remove, and edit admin permissions',
        add_admin: 'Add Admin',
        permanent: 'Permanent',
        temporary: 'Temporary',
        full_access: 'Full Access',
        full_permission: 'Full Permission',
        support: 'Support',
        telegram_id: 'Telegram ID',
        role: 'Role',
        no_admins_yet: 'No admins yet',
        add_new_admin: 'Add New Admin',
        admin_name: 'Admin Name',
        duration_hours: 'Duration (hours)',
        leave_empty_permanent: 'Leave empty for permanent',
        expiry_date: 'Expiry Date',
        assign_role: 'Assign Role',
        admin_label: 'Admin:',
        new_role: 'New Role',
        confirm_removal: 'Confirm Removal',
        confirm_remove_admin: 'Are you sure you want to remove',
        from_admins: 'from admins?',
        permissions_revoked: 'All permissions will be revoked immediately.',
        remove: 'Remove',
        broadcast_message: 'Broadcast Message',
        send_to_all: 'Send message to all users',
        message_type: 'Message Type',
        image: 'Image',
        video: 'Video',
        message_text_label: 'Message Text',
        write_message_here: 'Write message here...',
        broadcast_queued: 'Message will be added to broadcast queue',
        send_broadcast: 'Send Broadcast',
        sending: 'Sending...',
        preview_label: 'Preview:',
        detailed_stats: 'Detailed Statistics',
        stats_description: 'Comprehensive analysis of system performance, transactions, and users',
        this_week: 'This Week',
        this_month: 'This Month',
        avg_transaction: 'Average Transaction',
        completion_rate: 'Completion Rate',
        transactions_over_time: 'Transactions Over Time',
        tx_type_distribution: 'Transaction Type Distribution',
        user_growth: 'User Growth',
        top_users: 'Top 10 Users by Transactions',
        complaints_stats: 'Complaints Statistics',
        resolution_rate: 'Resolution Rate',
        resolution_progress: 'Resolution Progress',
        loading_stats: 'Loading statistics...',
        stats_load_failed: 'Failed to load statistics',
        new_users: 'New Users',
permissions_revoked: 'سيتم إبطال جميع صلاحياته فوراً.',
        remove: 'إزالة',
        broadcast_message: 'بث رسالة',
        send_to_all: 'إرسال رسالة لكل المستخدمين',
        message_type: 'نوع الرسالة',
        image: 'صورة',
        video: 'فيديو',
        message_text_label: 'نص الرسالة',
        write_message_here: 'اكتب الرسالة هنا...',
        broadcast_queued: 'سيتم إضافة الرسالة لقائمة البث',
        send_broadcast: 'إرسال البث',
        sending: 'جارٍ الإرسال...',
        preview_label: 'معاينة:',
        detailed_stats: 'الإحصائيات التفصيلية',
        stats_description: 'تحليل شامل لأداء النظام والمعاملات والمستخدمين',
        this_week: 'الأسبوع',
        this_month: 'الشهر',
        avg_transaction: 'متوسط المعاملة',
        completion_rate: 'معدل الإكمال',
        transactions_over_time: 'المعاملات عبر الزمن',
        tx_type_distribution: 'توزيع أنواع المعاملات',
        user_growth: 'نمو المستخدمين',
        top_users: 'أعلى 10 مستخدمين بالمعاملات',
        complaints_stats: 'إحصائيات الشكاوى',
        resolution_rate: 'معدل الحل',
        resolution_progress: 'تقدم الحل',
        loading_stats: 'جارٍ تحميل الإحصائيات...',
        stats_load_failed: 'فشل تحميل الإحصائيات',
        new_users: 'المستخدمون الجدد',
},
    en: {
        // Sidebar
        dashboard: 'Dashboard', transactions: 'Transactions', users: 'Users',
        transactions_label: 'Transactions',
        matching: 'Matching', svrp: 'Compensation', trading: 'Trading',
        lottery: 'Lottery', wheel: 'Wheel of Fortune', companies: 'Companies',
        payment_methods: 'Payment Methods', apps: 'Apps', referrals: 'Referrals',
        channels: 'Channels', bots: 'Bots', complaints: 'Complaints',
        broadcast: 'Broadcast', statistics: 'Statistics', admins: 'Admin Management',
        themes: 'Themes', exchange_addresses: 'Exchange Addresses',
        send_message: 'Send Message', backup: 'Backup', settings: 'Settings',
        operations: 'Operations', management: 'Management', system: 'System',
        advanced_system: 'Advanced System',
        // Navbar
        search_placeholder: 'Quick search... Ctrl+K', connected: 'Connected',
        notifications: 'Notifications', mark_read: 'Mark as read',
        no_notifications: 'No notifications', admin: 'Admin', logout: 'Logout',
        page_title: 'Dashboard', admin_panel: 'Admin Dashboard',
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
        transaction_volume: 'Transaction Volume', today: 'Today', active_matches: 'Active Matches',
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
    }
};

// Global translation function
function tr(key) {
    const lang = localStorage.getItem('lang') || 'ar';
    const dict = I18N[lang] || I18N.ar;
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
    // Auto-translate elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = tr(el.getAttribute('data-i18n'));
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = tr(el.getAttribute('data-i18n-placeholder'));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        el.title = tr(el.getAttribute('data-i18n-title'));
    });
});

// ===== API helper =====
async function api(url, options = {}) {
    const res = await fetch(url, {
        ...options,
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', ...options.headers }
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
        'disputed': '<span class="badge badge-rejected">Dispute</span>',
        'resolved': '<span class="badge badge-approved">' + tr('approved') + '</span>',
        'open': '<span class="badge badge-pending">Open</span>',
        'yes': '<span class="badge badge-approved">' + tr('yes') + '</span>',
        'no': '<span class="badge badge-rejected">' + tr('no') + '</span>',
        'auto_rejected': '<span class="badge badge-rejected">رفض تلقائي</span>',
        'withdrawal_rejected': '<span class="badge badge-rejected">رفض سحب</span>',
        'withdrawal_auto_rejected': '<span class="badge badge-rejected">رفض تلقائي</span>',
        'pending_withdrawal': '<span class="badge badge-pending">سحب معلق</span>',
        'pending_code_verification': '<span class="badge badge-pending">بانتظار الكود</span>',
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
        toast(this.soundEnabled ? '🔊 ' + tr('connected') : '🔇 Muted', 'info');
    },
    async check() {
        try {
            const res = await fetch('/api/stats');
            if (res.status === 401 || res.status === 403) {
                // Not an authenticated admin page — stop polling (avoids 401 spam)
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
                // First check after page load: record the baseline silently so
                // pre-existing pending items don't re-trigger the big popup on
                // every navigation. Only NEW events (count increases) notify.
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
        if (Notification.permission === 'granted') { const n = new Notification('🔔 Boterx', { body: message, tag: type }); setTimeout(() => n.close(), 4000); }
        const container = document.getElementById('notificationsList');
        if (container) {
            const item = document.createElement('div');
            item.className = 'flex items-center gap-2 p-2 rounded-lg bg-slate-700/50 text-sm';
            item.innerHTML = '<span>' + message + '</span> <span class="text-xs text-slate-500">' + new Date().toLocaleTimeString() + '</span>';
            container.prepend(item);
            if (container.children.length > 20) container.lastElementChild.remove();
        }
        this.showPopup(message, type);
        this.playSound(type === 'new_match' || type === 'new_complaint' ? 'alert' : 'notification');
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
        popup.innerHTML = '<div class="text-4xl mb-2">' + c.icon + '</div><div class="text-lg font-bold">' + message + '</div><div class="text-xs mt-2 opacity-50">Click to go ←</div>';
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
                    gain.gain.setValueAtTime(0.3, now + i * 0.3);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.3 + 0.25);
                    osc.start(now + i * 0.3); osc.stop(now + i * 0.3 + 0.25);
                }
            } else if (type === 'success') {
                [523, 659, 784, 1047].forEach((freq, i) => {
                    const osc = ctx.createOscillator(), gain = ctx.createGain();
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.frequency.value = freq; osc.type = 'sine';
                    gain.gain.setValueAtTime(0.3, now + i * 0.25);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.25 + 0.2);
                    osc.start(now + i * 0.25); osc.stop(now + i * 0.25 + 0.2);
                });
            } else {
                for (let i = 0; i < 2; i++) {
                    const osc = ctx.createOscillator(), gain = ctx.createGain();
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.frequency.value = 740; osc.type = 'sine';
                    gain.gain.setValueAtTime(0.3, now + i * 0.5);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.5 + 0.4);
                    osc.start(now + i * 0.5); osc.stop(now + i * 0.5 + 0.4);
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
    };
}

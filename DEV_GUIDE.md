# دليل التطوير — Boterx

> قواعد الكود، الأنماط، مرجع الحالات، وقواعد المساهمة.

---

## 1. قواعد الكود

### 1.1 الترميز واللغة
- Python 3.12+
- كل ملفات CSV تستخدم `utf-8-sig`
- النصوص العربية في علامات اقتباس مزدوجة

### 1.2 نمط API
```python
def api_call(self, method, data=None):
    url = f"{self.api_url}/{method}"
    # urllib.request خام، timeout=10
```

### 1.3 قراءة/كتابة CSV
```python
# آمن مع قفل
rows = self.safe_csv_read('file.csv')
self.safe_csv_write('file.csv', rows, fieldnames=[...], mode='w')

# مباشر (للإلحاق)
with open('file.csv', 'a', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow([val1, val2, ...])
```

### 1.4 نظام الحالات (FSM)
```python
# تعيين
self.user_states[user_id] = 'state_name_param1_param2'

# فحص — الأكثر تحديداً أولاً!
if state.startswith('svrp_enter_account_'):  # ← قبل العام
    ...
if state.startswith('svrp_'):  # ← العام أخيراً
    ...

# تنظيف
if user_id in self.user_states: del self.user_states[user_id]
```

### 1.5 الإدخال خطوة بخطوة
كل تدفق يطلب **بيان واحد** في كل مرة:
1. اطلب البيان + اعرض زر `❌ إلغاء`
2. تحقق من الإدخال
3. اعرض `✅ القيمة: <code>القيمة</code> 👈 اضغط للنسخ`
4. انتقل للخطوة التالية

### 1.6 البيانات الزرقاء القابلة للنسخ
كل رقم عملية/محفظة/معرف/كود/مبلغ في `<code>`:
```python
f"🆔 رقم العملية: <code>{trans_id}</code> 👈 اضغط للنسخ"
```

---

## 2. عند إضافة ميزة جديدة

### تدفق مستخدم جديد:
1. أضف اسم الحالة في `user_states`
2. أضف فحص الحالة في `process_message()` **قبل** الفحص العام و rate limiter
3. أضف تنظيف الحالة في نهاية التدفق
4. أضف ترجمات لكل النصوص
5. أضف إشعارات الأدمن إن لزم

### ملف CSV جديد:
1. أضف تهيئة في `init_files()`
2. أضف للترحيل إن كان تطور عمود جديد
3. استخدم `safe_csv_write`/`safe_csv_read`
4. أضف للنسخ الاحتياطي

---

## 3. أنماط حرجة للحفاظ عليها

### 3.1 ترتيب فحوص الحالات
```
svrp_enter_account_*  ← محدد، أولاً
svrp_bonus_amount_*   ← محدد
svrp_waiting_screenshot ← محدد
svrp_send_customer    ← محدد
svrp_send_amount_*    ← محدد
svrp_approve_amount_* ← محدد
svrp_dep_balance_*    ← محدد
svrp_edit_intro_*    ← محدد
svrp_                 ← عام، أخيراً (أكواد ترويجية)
```

### 3.2 عدم انتهاء الصلاحية
- `cleanup_old_transactions()` → معطل (pass)
- `expire_old_credits()` → معطل (pass)
- لا تضف أي auto-expiry جديد

### 3.3 شروط المكافأة
العميل يجب: تسجيل حساب + إيداع مرفوض. أظهر أزرار تنقل عند عدم الاستيفاء.

### 3.4 روابط الإفيليت
- عمود `affiliate_link` في `companies.csv`
- تُحرر من لوحة الأدمن (🔗 تعديل رابط الإحالة)
- تظهر كزر URL للعميل

### 3.5 العملة
استخدم `format_amount_with_currency()` — لا تكتب "ريال" يدوياً.

### 3.6 الأزرار
استخدم `transform_keyboard()`/`normalize_button_text()`.

### 3.7 Broadcasts
بدون keyboard.

---

## 4. قائمة الاختبار

- [ ] البوت يبدأ بدون أخطاء
- [ ] `/start` يعمل للمستخدم الجديد والقديم
- [ ] الإيداع: شركة ← وسيلة ← محفظة ← مبلغ ← تأكيد
- [ ] السحب: شركة ← مبلغ ← محفظة ← معرف ← كود ← تأكيد
- [ ] لوحة الأدمن تفتح
- [ ] الموافقة/الرفض على المعاملات
- [ ] تعويض: تسجيل حساب + إفيليت + رقم حساب
- [ ] تعويض: شروط المكافأة تظهر مع أزرار تنقل
- [ ] مطابقة P2P: كل خطوة منفصلة
- [ ] كل البيانات تظهر زرقاء قابلة للنسخ
- [ ] الطلبات لا تنتهي صلاحيتها

## Tailwind CSS (pre-built)
اللوحة تستخدم ملف CSS مبني مسبقاً `dashboard/static/css/tailwind.build.css` بدل سكربت Tailwind runtime. عند إضافة فئات Tailwind جديدة في القوالب أو ملفات JS شغّل `./build_css.sh` من جذر المشروع ثم حدّث رقم `?v=` في وسم `<link>` داخل `base.html` و `home.html`.

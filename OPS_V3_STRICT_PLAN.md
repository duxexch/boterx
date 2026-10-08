# OPS V3 - Strict Matching x Agents Plan

## 1) الهدف
- تحويل المطابقة إلى نظام صارم يقوده الوكلاء تحت تحكم كامل من الأدمن.
- حماية المستخدم من أي تلاعب: لا تنفيذ بدون تتبع، لا خطوة بدون دليل عند اللزوم، ولا غلق بدون أثر تدقيقي.
- تمكين الوكيل من العمل من الويب + البوت، مع نفس القواعد والقيود.

## 2) مبادئ الأمان (Non-Negotiable)
- Single source of truth: كل الحالات في SQLite (بدون تضارب CSV).
- Least privilege: الوكيل لا يصل إلا للطلبات المخصصة له.
- Append-only audit: كل تغيير حساس يسجل ولا يمكن تعديله لاحقا.
- Explicit ownership: أي خطوة تنفيذ/تأكيد مرتبطة بمالك العملية الحالي.
- Failsafe defaults: عند الشك -> Escalate/Admin review.

## 3) نموذج التهديد
- انتحال وكيل عبر Telegram ID.
- وكيل ينفذ على طلب غير مخصص له.
- وكيل يلتف على limits (عدد/مبلغ/نوع عمليات).
- وكيل يفتح نزاعات عبثية لتجميد الطلبات.
- إعادة تعيين وكيل دون ضبط escrow أو audit.

## 4) متطلبات النظام الصارم
- Policy per agent:
  - السماح لكل نوع عملية: deposit/withdraw/buy_usdt/sell_usdt.
  - سقف يومي بالمبلغ + سقف يومي بالعدد.
  - cap_per_txn + max_concurrent + max_open_disputes.
- Traffic control:
  - توزيع ديناميكي حسب weight + الحالة + limits.
  - Routing rules + pin/drain + block.
- Complaint pipeline:
  - فتح شكوى مرتبط بطلب فقط.
  - توجيه الشكوى تلقائيا للوكيل المسؤول (أو admin queue).
  - إعادة توزيع الشكوى من الأدمن + حل نهائي موثق.
- Admin super-control:
  - Claim/Takeover/Reassign.
  - تعديل سياسات الوكيل.
  - قائمة نزاعات مركزية + مؤشرات SLA.

## 5) التنفيذ المقترح (Back-end)
- تعزيز جدول `agent_bots` بسياسات تشغيل إضافية:
  - `allow_deposit`, `allow_withdraw`, `allow_buy_usdt`, `allow_sell_usdt`
  - `max_amount_daily`, `current_daily_amount`, `max_open_disputes`
- إضافة جدول نزاعات OPS مخصص:
  - `op_disputes(id, req_id, opened_by_type/id, assigned_to_type/id, status, reason, evidence, admin_note, opened_at, resolved_at, resolved_by)`
- قواعد تحقق صارمة داخل المحرك:
  - فحص eligibility قبل assignment/claim/reassign.
  - منع فتح شكوى من طرف غير مخول.
  - منع claim إذا الوكيل متجاوز limits أو غير مسموح بالنوع.

## 6) التنفيذ المقترح (Web/Bot)
- Web:
  - APIs لإدارة نزاعات OPS (list/assign/resolve).
  - APIs لوكيل: قائمة نزاعاته.
- Bot:
  - لوحة وكيل مطابقة داخل البوت:
    - قائمة الطلبات المخصصة.
    - Claim + Step Action/Confirm + Open Dispute.
  - نفس checks السيرفرية (لا منطق أمني في الواجهة فقط).

## 7) الرصد والجودة
- Health checks: dashboard + bot health ports.
- Smoke E2E على DB معزولة.
- Log scanning منذ وقت restart للخدمات.
- قياس latency endpoints الأساسية.

## 8) خطة الترحيل
- Migration additive only (أعمدة/جداول جديدة بدون كسر القديم).
- تفعيل تدريجي عبر defaults آمنة.
- Backups قبل النشر + rollback path.

## 9) مراجعة أولى للخطة (Hardening Pass #1)
- إضافة check إلزامي على `open_request_dispute` للتأكد من الصلاحية.
- ربط dispute assignment تلقائيا بـ `assigned_agent_id` عند وجوده.
- إدخال limit `max_open_disputes` لمنع إساءة فتح الشكاوى.

## 10) مراجعة ثانية للخطة (Hardening Pass #2)
- توحيد eligibility check في helper واحدة لمنع تناقضات المسارات.
- احتساب daily amount ضمن قرارات التوزيع لتفادي انحياز load.
- إضافة audit events واضحة لأي Claim/Reassign/Dispute Assign/Resolve.
- فرض source-of-truth واحد في كل واجهات البوت/الويب عبر `agent_db` فقط.

## 11) Definition of Done
- الوكيل لا يستطيع تنفيذ أو فتح شكوى أو claim خارج صلاحياته.
- الأدمن يتحكم في كل الطلبات/الشكاوى/التوجيه.
- توزيع الحركة يحترم limits والنوع والسعة.
- لا أخطاء runtime بعد النشر (logs clean منذ restart).
- الاختبارات + smoke + health + performance snapshot ناجحة.

# LangSense / DUX Bot — Render Deployment Guide

## 📋 المتطلبات

- حساب على Render.com
- GitHub repo فيه كود البوت
- ملف `.env` ببيانات التوكن (موجود)

---

## 🚀 خطوات النشر على Render

### 1️⃣ ارفع الكود لـ GitHub

```bash
cd C:\Users\gnz\Downloads\bot2\bot
git init
git add .
git commit -m "LangSense Bot - Production Ready"
git remote add origin https://github.com/USERNAME/langsense-bot.git
git push -u origin main
```

### 2️⃣ أنشئ Web Service على Render

1. ادخل [render.com](https://render.com) → Sign In
2. اضغط **New +** → **Web Service**
3. اربط حساب GitHub → اختر الـ repo
4. املأ البيانات:

| الحقل | القيمة |
|-------|--------|
| **Name** | `langsense-bot` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python comprehensive_bot.py` |
| **Instance Type** | `Free` أو `Starter` |

### 3️⃣ أضف Environment Variables

في قسم **Environment** على Render أضف:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | `8360806450:AAHDyURl-PazLfzqHP1ZTiP1frEc7e7eL4o` |
| `ADMIN_USER_IDS` | `7146701713` |

### 4️rm اضبط الـ Disk (لتخزين CSV)

> ⚠️ مهم جداً — Render Free Tier يحيي القرص عند كل restart

1. في **Settings** → **Disks**
2. أضف Disk:
   - **Name**: `bot-data`
   - **Mount Path**: `/opt/render/src`
   - **Size**: `1 GB`

### 5️⃣ أطلق البوت

1. اضغط **Create Web Service**
2. انتظر Build ينتهي
3. شوف الـ Logs — لازم تشوف:
```
BOT_TOKEN loaded successfully ✓
Loaded i18n translations for 17 languages
✅ نظام DUX الشامل يعمل
```

---

## ⚠️ مشاكل محتملة وحلولها

### المشكلة: Render يطفئ البوت على Free Tier
- **السبب**: Render Free ينام بعد 15 دقيقة بدون نشاط
- **الحل**: استخدم **UptimeRobot** لتنبيه البوت كل 10 دقائق
  1. أنشئ حساب على [uptimerobot.com](https://uptimerobot.com)
  2. أضف Monitor من نوع **HTTP**
  3. ضع رابط الـ Web Service من Render

### المشكلة: ملفات CSV تُحذف عند الـ restart
- **السبب**: Render Free لا يحتفظ بالملفات
- **الحل**: استخدم Disk دائم (Starter plan بـ $7/شهر) أو:
  - اربط البوت بقاعدة بيانات PostgreSQL من Render
  - عدّل الكود لاستخدام PostgreSQL بدل CSV

### المشكلة: البوت لا يستقبل الرسائل
- **تأكد**: BOT_TOKEN صحيح في Environment Variables
- **تأكد**: الـ Logs لا يوجد أخطاء
- **تأكد**: البوت يعمل (status: Live في Render)

---

## 📁 ملفات النشر (جاهزة)

| الملف | الغرض |
|------|-------|
| `.env` | متغيرات البيئة (توكن + أدمن) |
| `Procfile` | `web: python comprehensive_bot.py` |
| `requirements.txt` | `python-dotenv` + `openpyxl` |
| `runtime.txt` | `python` |

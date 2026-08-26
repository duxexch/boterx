# Auto-posting engine code (to be injected into app.py)
# Do not run directly

AUTO_POST_ENGINE_CODE = '''
# ===== Auto-Posting Engine =====
_CONTENT_TEMPLATES = {
    "info": [
        "📊 إحصائيات اليوم: فريقك سجّل {stats_today}. تابع التحديثات معنا!",
        "📈 أرقام مميزة: {stat_highlight}. ما رأيك في هذه الأرقام؟",
        "💡 هل تعلم؟ {fun_fact}. شاركنا رأيك!",
        "🏆 إنجاز تاريخي: {achievement}. فريقنا يستحق التصفيق!",
    ],
    "question": [
        "🤔 سؤال اليوم: {question}? اكتب رأيك في التعليقات!",
        "💭 ما توقعكم لنتيجة مباراة {upcoming_match}؟",
        "⚽ من أحسن لاعب في المباراة الأخيرة برأيك؟",
        "🎯 هل توافق على هذا التحليل؟ اكتب نعم أو لا!",
    ],
    "prediction": [
        "🔮 توقعاتنا: {prediction_details}. ما رأيك؟",
        "📊 التحليل يشير إلى {prediction}. انتظروا النتيجة!",
        "🎯 picks اليوم: {picks}. هل توافق؟",
    ],
    "analysis": [
        "📋 تحليل مباراة {match_name}:\\n{analysis_details}",
        "🔍 تقرير مفصل: {report_summary}",
        "📝 تقييم أداء اللاعبين: {player_ratings}",
    ],
    "live": [
        "🔴 مباشر | {live_event}",
        "⚡ تحديث مباشر: {live_update}",
        "🏟️ أحداث المباراة الحية: {live_details}",
    ],
    "result": [
        "🏁 نتيجة المباراة: {result}",
        "✅ خلاصة المباراة: {match_summary}",
        "📊 النتيجة النهائية: {final_result}",
    ],
}


def _get_branding_suffix(channel):
    parts = []
    cn = str(channel.get("company_name") or "").strip()
    dl = str(channel.get("download_link") or "").strip()
    pc = str(channel.get("promo_code") or "").strip()
    al = str(channel.get("affiliate_link") or "").strip()
    if cn:
        parts.append("🏢 " + cn)
    if dl:
        parts.append("📱 تحميل: " + dl)
    if pc:
        parts.append("🎁 كود الخصم: " + pc)
    if al:
        parts.append("🔗 " + al)
    return "\\n\\n" + "\\n".join(parts) if parts else ""


def _apply_placeholders(text, channel, extra=None):
    cn = str(channel.get("company_name") or "VEX Games")
    dl = str(channel.get("download_link") or "")
    pc = str(channel.get("promo_code") or "")
    al = str(channel.get("affiliate_link") or "")
    text = text.replace("{company_name}", cn)
    text = text.replace("{download_link}", dl)
    text = text.replace("{promo_code}", pc)
    text = text.replace("{affiliate_link}", al)
    if extra:
        for k, v in extra.items():
            text = text.replace("{" + k + "}", str(v))
    return text


@app.route("/api/content-templates", methods=["GET", "POST"])
@api_auth
@permission_required("send_broadcast")
def api_content_templates():
    if request.method == "GET":
        return jsonify({"templates": _CONTENT_TEMPLATES, "types": list(_CONTENT_TEMPLATES.keys())})
    data = request.json or {}
    content_type = (data.get("type") or "").strip()
    text = (data.get("text") or "").strip()
    if not content_type or not text:
        return jsonify({"error": "type and text required"}), 400
    if content_type not in _CONTENT_TEMPLATES:
        _CONTENT_TEMPLATES[content_type] = []
    _CONTENT_TEMPLATES[content_type].append(text)
    return jsonify({"success": True, "count": len(_CONTENT_TEMPLATES[content_type])})


@app.route("/api/auto-post/run", methods=["POST"])
@api_auth
@permission_required("send_broadcast")
def api_auto_post_run():
    channels = read_csv("bot_channels.csv")
    active = [c for c in channels if c.get("auto_post_enabled") == "yes" and c.get("is_active") == "yes"]
    if not active:
        return jsonify({"error": "لا توجد قنوات مفعّلة للنشر التلقائي"}), 400
    queued = 0
    now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
    for ch in active:
        types_raw = str(ch.get("auto_post_types") or "info|question|prediction|analysis")
        allowed_types = [t.strip() for t in types_raw.split("|") if t.strip()]
        if not allowed_types:
            allowed_types = ["info", "question"]
        chosen_type = random.choice(allowed_types)
        templates = _CONTENT_TEMPLATES.get(chosen_type, [])
        if not templates:
            continue
        template = random.choice(templates)
        text = _apply_placeholders(template, ch)
        suffix = _get_branding_suffix(ch)
        full_text = text + suffix
        entry = {
            "id": "AUTO" + secrets.token_hex(4).upper(),
            "message": full_text,
            "type": "channel",
            "platform": str(ch.get("platform", "telegram") or "telegram").lower(),
            "target_chat_id": str(ch.get("chat_id", "") or ""),
            "platform_account_id": str(ch.get("platform_account_id", "") or ""),
            "target_channel_id": ch.get("id", ""),
            "created_at": now_s,
            "created_by": "auto_post_engine",
            "status": "pending",
            "target": "channel",
            "recipient": "single",
            "priority": "normal",
            "country": "all",
            "media_urls": "",
            "target_user": "",
            "target_name": "",
            "scheduled_at": "",
            "cron_expr": "",
        }
        fieldnames = get_fieldnames("broadcast_queue.csv", [
            "id", "message", "type", "platform", "target_chat_id",
            "platform_account_id", "target_channel_id", "created_at",
            "created_by", "status", "target", "recipient", "priority",
            "country", "media_urls", "target_user", "target_name",
            "scheduled_at", "cron_expr"
        ])
        append_csv("broadcast_queue.csv", entry, fieldnames)
        queued += 1
    log_action("auto_post_run", str(queued) + " channels queued")
    return jsonify({"success": True, "queued": queued})


@app.route("/api/auto-post/scheduler-status")
@api_auth
def api_auto_post_scheduler():
    channels = read_csv("bot_channels.csv")
    enabled = [c for c in channels if c.get("auto_post_enabled") == "yes"]
    status = []
    for ch in enabled:
        status.append({
            "id": ch.get("id"),
            "title": ch.get("title"),
            "interval_min": ch.get("auto_post_interval_min", "120"),
            "types": ch.get("auto_post_types", "info|question"),
            "chat_id": ch.get("chat_id"),
        })
    return jsonify({"enabled_count": len(enabled), "channels": status})
'''

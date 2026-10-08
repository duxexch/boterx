import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\company_detail.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add I18N_TRANSLATIONS and applyTranslations before closing </script> or before </body>
# Find the last </script> tag and insert before it
i18n_block = '''
<script>
window.I18N_TRANSLATIONS = {
  ar: {
    back_to_home: "العودة للرئيسية",
    detail_badge: "شريك معتمد VEX",
    detail_founded: "تأسست",
    detail_stars: "نجوم",
    detail_promo_title: "كود البرومو الحصري",
    detail_promo_hint: "استخدم هذا الكود عند التسجيل",
    detail_copy_btn: "نسخ الكود",
    detail_copied: "تم النسخ",
    detail_cta_register: "سجّل في",
    detail_cta_app: "تحميل التطبيق",
    detail_overview: "نظرة عامة",
    detail_table_title: "تفاصيل الشركة",
    detail_label_name: "الاسم",
    detail_label_license: "الترخيص",
    detail_label_hq: "المقر",
    detail_label_founded: "التأسيس",
    detail_label_rating: "التقييم",
    detail_label_promo: "كود البرومو",
    detail_pros_cons: "المميزات والعيوب",
    detail_pros: "المميزات",
    detail_cons: "العيوب",
    detail_why_title: "لماذا تسجل عبر VEX؟",
    detail_why_desc: "VEX شريك معتمد مباشر مع {company}. كل تسجيل عبر روابطنا محسوب لك بشكل مباشر. نوفر لك كود البرومو الحصري ورابط التسجيل المباشر بدون أي عمولات إضافية عليك.",
    detail_similar: "شركات مشابهة",
    detail_footer_partner: "شريك معتمد",
    detail_footer_responsible: "18+ - العب بمسؤولية",
    footer_copyright: "© 2026 VEX Games — شريك معتمد • 8 شركات مرخصة • 17 لغة • Provably Fair"
  },
  en: {
    back_to_home: "Back to Home",
    detail_badge: "VEX Verified Partner",
    detail_founded: "Founded",
    detail_stars: "stars",
    detail_promo_title: "Exclusive Promo Code",
    detail_promo_hint: "Use this code when registering",
    detail_copy_btn: "Copy Code",
    detail_copied: "Copied!",
    detail_cta_register: "Register at",
    detail_cta_app: "Download App",
    detail_overview: "Overview",
    detail_table_title: "Company Details",
    detail_label_name: "Name",
    detail_label_license: "License",
    detail_label_hq: "Headquarters",
    detail_label_founded: "Founded",
    detail_label_rating: "Rating",
    detail_label_promo: "Promo Code",
    detail_pros_cons: "Pros & Cons",
    detail_pros: "Pros",
    detail_cons: "Cons",
    detail_why_title: "Why Register via VEX?",
    detail_why_desc: "VEX is a verified direct partner with {company}. Every registration through our links counts directly for you. We provide the exclusive promo code and direct registration link with no extra cost to you.",
    detail_similar: "Similar Companies",
    detail_footer_partner: "Verified Partner",
    detail_footer_responsible: "18+ - Play Responsibly",
    footer_copyright: "© 2026 VEX Games — Verified Partner • 8 Licensed Companies • 17 Languages • Provably Fair"
  },
  fr: {
    back_to_home: "Retour à l'Accueil",
    detail_badge: "Partenaire VEX Vérifié",
    detail_founded: "Fondée",
    detail_stars: "étoiles",
    detail_promo_title: "Code Promo Exclusif",
    detail_promo_hint: "Utilisez ce code lors de l'inscription",
    detail_copy_btn: "Copier le Code",
    detail_copied: "Copié!",
    detail_cta_register: "S'inscrire sur",
    detail_cta_app: "Télécharger l'App",
    detail_overview: "Aperçu",
    detail_table_title: "Détails de l'Entreprise",
    detail_label_name: "Nom",
    detail_label_license: "Licence",
    detail_label_hq: "Siège",
    detail_label_founded: "Fondée",
    detail_label_rating: "Note",
    detail_label_promo: "Code Promo",
    detail_pros_cons: "Avantages & Inconvénients",
    detail_pros: "Avantages",
    detail_cons: "Inconvénients",
    detail_why_title: "Pourquoi S'inscrire via VEX?",
    detail_why_desc: "VEX est un partenaire vérifié direct avec {company}. Chaque inscription via nos liens compte directement pour vous. Nous fournissons le code promo exclusif et le lien d'inscription direct sans coût supplémentaire.",
    detail_similar: "Entreprises Similaires",
    detail_footer_partner: "Partenaire Vérifié",
    detail_footer_responsible: "18+ - Jouez de Manière Responsable",
    footer_copyright: "© 2026 VEX Games — Partenaire Vérifié • 8 Entreprises Licenciées • 17 Langues • Provably Fair"
  },
  es: {
    back_to_home: "Volver al Inicio",
    detail_badge: "Socio VEX Verificado",
    detail_founded: "Fundada",
    detail_stars: "estrellas",
    detail_promo_title: "Código Promo Exclusivo",
    detail_promo_hint: "Usa este código al registrarte",
    detail_copy_btn: "Copiar Código",
    detail_copied: "Copiado!",
    detail_cta_register: "Registrarse en",
    detail_cta_app: "Descargar App",
    detail_overview: "Descripción General",
    detail_table_title: "Detalles de la Empresa",
    detail_label_name: "Nombre",
    detail_label_license: "Licencia",
    detail_label_hq: "Sede",
    detail_label_founded: "Fundación",
    detail_label_rating: "Calificación",
    detail_label_promo: "Código Promo",
    detail_pros_cons: "Pros y Contras",
    detail_pros: "Pros",
    detail_cons: "Contras",
    detail_why_title: "¿Por Qué Registrarse via VEX?",
    detail_why_desc: "VEX es socio verificado directo con {company}. Cada registro a través de nuestros enlaces cuenta directamente para ti. Proporcionamos el código promo exclusivo y el enlace de registro directo sin costo adicional.",
    detail_similar: "Empresas Similares",
    detail_footer_partner: "Socio Verificado",
    detail_footer_responsible: "18+ - Juega Responsablemente",
    footer_copyright: "© 2026 VEX Games — Socio Verificado • 8 Empresas Licenciadas • 17 Idiomas • Provably Fair"
  },
  de: {
    back_to_home: "Zurück zur Startseite",
    detail_badge: "VEX Verifizierter Partner",
    detail_founded: "Gegründet",
    detail_stars: "Sterne",
    detail_promo_title: "Exklusiver Promo-Code",
    detail_promo_hint: "Verwende diesen Code bei der Registrierung",
    detail_copy_btn: "Code Kopieren",
    detail_copied: "Kopiert!",
    detail_cta_register: "Registrieren bei",
    detail_cta_app: "App Herunterladen",
    detail_overview: "Übersicht",
    detail_table_title: "Unternehmensdetails",
    detail_label_name: "Name",
    detail_label_license: "Lizenz",
    detail_label_hq: "Hauptsitz",
    detail_label_founded: "Gegründet",
    detail_label_rating: "Bewertung",
    detail_label_promo: "Promo-Code",
    detail_pros_cons: "Vorteile & Nachteile",
    detail_pros: "Vorteile",
    detail_cons: "Nachteile",
    detail_why_title: "Warum über VEX Registrieren?",
    detail_why_desc: "VEX ist ein verifizierter direkter Partner von {company}. Jede Registrierung über unsere Links zählt direkt für dich. Wir stellen den exklusiven Promo-Code und den direkten Registrierungslink ohne zusätzliche Kosten bereit.",
    detail_similar: "Ähnliche Unternehmen",
    detail_footer_partner: "Verifizierter Partner",
    detail_footer_responsible: "18+ - Spiele Verantwortungsvoll",
    footer_copyright: "© 2026 VEX Games — Verifizierter Partner • 8 Lizenzierte Unternehmen • 17 Sprachen • Provably Fair"
  },
  it: {
    back_to_home: "Torna alla Home",
    detail_badge: "Partner VEX Verificato",
    detail_founded: "Fondata",
    detail_stars: "stelle",
    detail_promo_title: "Codice Promo Esclusivo",
    detail_promo_hint: "Usa questo codice durante la registrazione",
    detail_copy_btn: "Copia Codice",
    detail_copied: "Copiato!",
    detail_cta_register: "Registrati su",
    detail_cta_app: "Scarica App",
    detail_overview: "Panoramica",
    detail_table_title: "Dettagli Azienda",
    detail_label_name: "Nome",
    detail_label_license: "Licenza",
    detail_label_hq: "Sede",
    detail_label_founded: "Fondata",
    detail_label_rating: "Valutazione",
    detail_label_promo: "Codice Promo",
    detail_pros_cons: "Pro & Contro",
    detail_pros: "Pro",
    detail_cons: "Contro",
    detail_why_title: "Perché Registrarsi via VEX?",
    detail_why_desc: "VEX è un partner verificato diretto con {company}. Ogni registrazione attraverso i nostri link conta direttamente per te. Forniamo il codice promo esclusivo e il link di registrazione diretta senza costi aggiuntivi.",
    detail_similar: "Aziende Simili",
    detail_footer_partner: "Partner Verificato",
    detail_footer_responsible: "18+ - Gioca in Modo Responsabile",
    footer_copyright: "© 2026 VEX Games — Partner Verificato • 8 Aziende Licenziate • 17 Lingue • Provably Fair"
  },
  pt: {
    back_to_home: "Voltar ao Início",
    detail_badge: "Parceiro VEX Verificado",
    detail_founded: "Fundada",
    detail_stars: "estrelas",
    detail_promo_title: "Código Promocional Exclusivo",
    detail_promo_hint: "Use este código ao se registrar",
    detail_copy_btn: "Copiar Código",
    detail_copied: "Copiado!",
    detail_cta_register: "Registrar em",
    detail_cta_app: "Baixar App",
    detail_overview: "Visão Geral",
    detail_table_title: "Detalhes da Empresa",
    detail_label_name: "Nome",
    detail_label_license: "Licença",
    detail_label_hq: "Sede",
    detail_label_founded: "Fundação",
    detail_label_rating: "Avaliação",
    detail_label_promo: "Código Promo",
    detail_pros_cons: "Prós & Contras",
    detail_pros: "Prós",
    detail_cons: "Contras",
    detail_why_title: "Por Que Registrar via VEX?",
    detail_why_desc: "VEX é parceiro verificado direto com {company}. Cada registro através dos nossos links conta diretamente para você. Fornecemos o código promocional exclusivo e o link de registro direto sem custo adicional.",
    detail_similar: "Empresas Semelhantes",
    detail_footer_partner: "Parceiro Verificado",
    detail_footer_responsible: "18+ - Jogue de Forma Responsável",
    footer_copyright: "© 2026 VEX Games — Parceiro Verificado • 8 Empresas Licenciadas • 17 Idiomas • Provably Fair"
  },
  ru: {
    back_to_home: "На Главную",
    detail_badge: "Проверенный Партнёр VEX",
    detail_founded: "Основана",
    detail_stars: "звезд",
    detail_promo_title: "Эксклюзивный Промокод",
    detail_promo_hint: "Используйте этот код при регистрации",
    detail_copy_btn: "Скопировать Код",
    detail_copied: "Скопировано!",
    detail_cta_register: "Зарегистрироваться в",
    detail_cta_app: "Скачать Приложение",
    detail_overview: "Обзор",
    detail_table_title: "Данные Компании",
    detail_label_name: "Название",
    detail_label_license: "Лицензия",
    detail_label_hq: "Штаб-квартира",
    detail_label_founded: "Основана",
    detail_label_rating: "Рейтинг",
    detail_label_promo: "Промокод",
    detail_pros_cons: "Плюсы & Минусы",
    detail_pros: "Плюсы",
    detail_cons: "Минусы",
    detail_why_title: "Почему Регистрироваться через VEX?",
    detail_why_desc: "VEX — проверенный прямой партнёр {company}. Каждая регистрация через наши ссылки засчитывается вам напрямую. Мы предоставляем эксклюзивный промокод и прямую ссылку на регистрацию без дополнительных затрат.",
    detail_similar: "Похожие Компании",
    detail_footer_partner: "Проверенный Партнёр",
    detail_footer_responsible: "18+ - Играйте Ответственно",
    footer_copyright: "© 2026 VEX Games — Проверенный Партнёр • 8 Лицензированных Компаний • 17 Языков • Provably Fair"
  },
  zh: {
    back_to_home: "返回首页",
    detail_badge: "VEX 认证合作伙伴",
    detail_founded: "成立于",
    detail_stars: "星",
    detail_promo_title: "专属推广码",
    detail_promo_hint: "注册时使用此代码",
    detail_copy_btn: "复制代码",
    detail_copied: "已复制!",
    detail_cta_register: "注册",
    detail_cta_app: "下载应用",
    detail_overview: "概览",
    detail_table_title: "公司详情",
    detail_label_name: "名称",
    detail_label_license: "许可证",
    detail_label_hq: "总部",
    detail_label_founded: "成立年份",
    detail_label_rating: "评分",
    detail_label_promo: "推广码",
    detail_pros_cons: "优缺点",
    detail_pros: "优点",
    detail_cons: "缺点",
    detail_why_title: "为什么通过 VEX 注册?",
    detail_why_desc: "VEX 是 {company} 的认证直接合作伙伴。通过我们链接的每次注册都直接为您计数。我们提供独家推广码和直接注册链接，无需额外费用。",
    detail_similar: "相似公司",
    detail_footer_partner: "认证合作伙伴",
    detail_footer_responsible: "18+ - 负责任游戏",
    footer_copyright: "© 2026 VEX Games — 认证合作伙伴 • 8 家持牌公司 • 17 种语言 • Provably Fair"
  },
  tr: {
    back_to_home: "Ana Sayfaya Dön",
    detail_badge: "VEX Doğrulanmış Partner",
    detail_founded: "Kuruluş",
    detail_stars: "yıldız",
    detail_promo_title: "Özel Promosyon Kodu",
    detail_promo_hint: "Kayıt olurken bu kodu kullanın",
    detail_copy_btn: "Kodu Kopyala",
    detail_copied: "Kopyalandı!",
    detail_cta_register: "Kayıt Ol",
    detail_cta_app: "Uygulamayı İndir",
    detail_overview: "Genel Bakış",
    detail_table_title: "Şirket Detayları",
    detail_label_name: "İsim",
    detail_label_license: "Lisans",
    detail_label_hq: "Merkez",
    detail_label_founded: "Kuruluş",
    detail_label_rating: "Puan",
    detail_label_promo: "Promosyon Kodu",
    detail_pros_cons: "Artıları & Eksileri",
    detail_pros: "Artılar",
    detail_cons: "Eksiler",
    detail_why_title: "Neden VEX Üzerinden Kayıt Olmalısınız?",
    detail_why_desc: "VEX, {company} ile doğrulanmış doğrudan bir partnerdir. Linklerimiz üzerinden yapılan her kayıt doğrudan size yansıtılır. Ekstra maliyet olmadan özel promosyon kodu ve doğrudan kayıt linki sunuyoruz.",
    detail_similar: "Benzer Şirketler",
    detail_footer_partner: "Doğrulanmış Partner",
    detail_footer_responsible: "18+ - Sorumlu Oynayın",
    footer_copyright: "© 2026 VEX Games — Doğrulanmış Partner • 8 Lisanslı Şirket • 17 Dil • Provably Fair"
  },
  ur: {
    back_to_home: "ہوم پیج پر واپس",
    detail_badge: "VEX تصدیق شدہ پارٹنر",
    detail_founded: "قائم",
    detail_stars: "ستارے",
    detail_promo_title: "خاص پرومو کوڈ",
    detail_promo_hint: "رجسٹر کرتے وقت یہ کوڈ استعمال کریں",
    detail_copy_btn: "کوڈ کاپی کریں",
    detail_copied: "کاپی ہو گیا!",
    detail_cta_register: "رجسٹر کریں",
    detail_cta_app: "ایپ ڈاؤن لوڈ کریں",
    detail_overview: "جائزہ",
    detail_table_title: "کمپنی کی تفصیلات",
    detail_label_name: "نام",
    detail_label_license: "لائسنس",
    detail_label_hq: "ہیڈ کوارٹر",
    detail_label_founded: "قائم",
    detail_label_rating: "درجہ بندی",
    detail_label_promo: "پرومو کوڈ",
    detail_pros_cons: "فوائد & نقصانات",
    detail_pros: "فوائد",
    detail_cons: "نقصانات",
    detail_why_title: "VEX کے ذریعے کیوں رجسٹر کریں؟",
    detail_why_desc: "VEX {company} کا تصدیق شدہ براہ راست پارٹنر ہے۔ ہمارے لنکس کے ذریعے ہر رجسٹریشن براہ راست آپ کے لیے گنتی جاتی ہے۔ ہم خاص پرومو کوڈ اور براہ راست رجسٹریشن لنک فراہم کرتے ہیں بغیر کسی اضافی لاگت کے۔",
    detail_similar: "مشابہ کمپنیاں",
    detail_footer_partner: "تصدیق شدہ پارٹنر",
    detail_footer_responsible: "18+ - ذمہ داری سے کھیلیں",
    footer_copyright: "© 2026 VEX Games — تصدیق شدہ پارٹنر • 8 لائسنس یافتہ کمپنیاں • 17 زبانیں • Provably Fair"
  },
  fa: {
    back_home: "بازگشت به خانه",
    detail_badge: "شریک تأیید شده VEX",
    detail_founded: "تأسیس",
    detail_stars: "ستاره",
    detail_promo_title: "کد پرومو اختصاصی",
    detail_promo_hint: "این کد را هنگام ثبت‌نام استفاده کنید",
    detail_copy_btn: "کپی کد",
    detail_copied: "کپی شد!",
    detail_cta_register: "ثبت‌نام در",
    detail_cta_app: "دانلود اپلیکیشن",
    detail_overview: "نمای کلی",
    detail_table_title: "جزئیات شرکت",
    detail_label_name: "نام",
    detail_label_license: "مجوز",
    detail_label_hq: "دفتر مرکزی",
    detail_label_founded: "تاسیس",
    detail_label_rating: "امتیاز",
    detail_label_promo: "کد پرومو",
    detail_pros_cons: "مزایا & معایب",
    detail_pros: "مزایا",
    detail_cons: "معایب",
    detail_why_title: "چرا از طریق VEX ثبت‌نام کنیم؟",
    detail_why_desc: "VEX شریک تأیید شده مستقیم با {company} است. هر ثبت‌نام از طریق لینک‌های ما مستقیماً برای شما محاسبه می‌شود. ما کد پرومو اختصاصی و لینک ثبت‌نام مستقیم را بدون هیچ هزینه اضافی ارائه می‌دهیم.",
    detail_similar: "شرکت‌های مشابه",
    detail_footer_partner: "شریک تأیید شده",
    detail_footer_responsible: "18+ - مسئولانه بازی کنید",
    footer_copyright: "© 2026 VEX Games — شریک تأیید شده • 8 شرکت مجوز دار • 17 زبان • Provably Fair"
  },
  hi: {
    back_home: "होम पेज पर वापस",
    detail_badge: "VEX सत्यापित पार्टनर",
    detail_founded: "स्थापित",
    detail_stars: "सितारे",
    detail_promo_title: "विशेष प्रोमो कोड",
    detail_promo_hint: "पंजीकरण के समय इस कोड का उपयोग करें",
    detail_copy_btn: "कोड कॉपी करें",
    detail_copied: "कॉपी हो गया!",
    detail_cta_register: "पंजीकरण करें",
    detail_cta_app: "ऐप डाउनलोड करें",
    detail_overview: "अवलोकन",
    detail_table_title: "कंपनी विवरण",
    detail_label_name: "नाम",
    detail_label_license: "लाइसेंस",
    detail_label_hq: "मुख्यालय",
    detail_label_founded: "स्थापित",
    detail_label_rating: "रेटिंग",
    detail_label_promo: "प्रोमो कोड",
    detail_pros_cons: "फायदे & नुकसान",
    detail_pros: "फायदे",
    detail_cons: "नुकसान",
    detail_why_title: "VEX के माध्यम से क्यों पंजीकरण करें?",
    detail_why_desc: "VEX {company} का सत्यापित सीधा पार्टनर है। हमारे लिंक्स के माध्यम से हर पंजीकरण सीधे आपके लिए गिना जाता है। हम बिना किसी अतिरिक्त लागत के विशेष प्रोमो कोड और सीधा पंजीकरण लिंक प्रदान करते हैं।",
    detail_similar: "समान कंपनियां",
    detail_footer_partner: "सत्यापित पार्टनर",
    detail_footer_responsible: "18+ - जिम्मेदारी से खेलें",
    footer_copyright: "© 2026 VEX Games — सत्यापित पार्टनर • 8 लाइसेंस प्राप्त कंपनियां • 17 भाषाएं • Provably Fair"
  },
  id: {
    back_home: "Kembali ke Beranda",
    detail_badge: "Mitra Terverifikasi VEX",
    detail_founded: "Didirikan",
    detail_stars: "bintang",
    detail_promo_title: "Kode Promo Eksklusif",
    detail_promo_hint: "Gunakan kode ini saat mendaftar",
    detail_copy_btn: "Salin Kode",
    detail_copied: "Tersalin!",
    detail_cta_register: "Daftar di",
    detail_cta_app: "Unduh Aplikasi",
    detail_overview: "Ringkasan",
    detail_table_title: "Detail Perusahaan",
    detail_label_name: "Nama",
    detail_label_license: "Lisensi",
    detail_label_hq: "Kantor Pusat",
    detail_label_founded: "Didirikan",
    detail_label_rating: "Penilaian",
    detail_label_promo: "Kode Promo",
    detail_pros_cons: "Kelebihan & Kekurangan",
    detail_pros: "Kelebihan",
    detail_cons: "Kekurangan",
    detail_why_title: "Mendaftar via VEX?",
    detail_why_desc: "VEX adalah mitra terverifikasi langsung dengan {company}. Setiap pendaftaran melalui link kami langsung dihitung untuk Anda. Kami menyediakan kode promo eksklusif dan link pendaftaran langsung tanpa biaya tambahan.",
    detail_similar: "Perusahaan Serupa",
    detail_footer_partner: "Mitra Terverifikasi",
    detail_footer_responsible: "18+ - Bermain dengan Bertanggung Jawab",
    footer_copyright: "© 2026 VEX Games — Mitra Terverifikasi • 8 Perusahaan Berlisensi • 17 Bahasa • Provably Fair"
  },
  ja: {
    back_home: "ホームに戻る",
    detail_badge: "VEX認定パートナー",
    detail_founded: "設立",
    detail_stars: "星",
    detail_promo_title: "限定プロモコード",
    detail_promo_hint: "登録時にこのコードを使用してください",
    detail_copy_btn: "コードをコピー",
    detail_copied: "コピー済み!",
    detail_cta_register: "登録する",
    detail_cta_app: "アプリをダウンロード",
    detail_overview: "概要",
    detail_table_title: "会社詳細",
    detail_label_name: "名前",
    detail_label_license: "ライセンス",
    detail_label_hq: "本社",
    detail_label_founded: "設立",
    detail_label_rating: "評価",
    detail_label_promo: "プロモコード",
    detail_pros_cons: "長所 & 短所",
    detail_pros: "長所",
    detail_cons: "短所",
    detail_why_title: "VEX経由で登録する理由?",
    detail_why_desc: "VEXは{company}の認定直接パートナーです。当社のリンクを通じた登録はすべて直接あなたにカウントされます。限定プロモコードと直接登録リンクを追加費用なしで提供します。",
    detail_similar: "類似の会社",
    detail_footer_partner: "認定パートナー",
    detail_footer_responsible: "18+ - 責任を持ってプレイ",
    footer_copyright: "© 2026 VEX Games — 認定パートナー • 8社ライセンス保有 • 17言語 • Provably Fair"
  },
  ko: {
    back_home: "홈으로 돌아가기",
    detail_badge: "VEX 인증 파트너",
    detail_founded: "설립",
    detail_stars: "별점",
    detail_promo_title: "독점 프로모 코드",
    detail_promo_hint: "등록 시 이 코드를 사용하세요",
    detail_copy_btn: "코드 복사",
    detail_copied: "복사됨!",
    detail_cta_register: "등록하기",
    detail_cta_app: "앱 다운로드",
    detail_overview: "개요",
    detail_table_title: "회사 상세정보",
    detail_label_name: "이름",
    detail_label_license: "라이선스",
    detail_label_hq: "본사",
    detail_label_founded: "설립",
    detail_label_rating: "평점",
    detail_label_promo: "프로모 코드",
    detail_pros_cons: "장점 & 단점",
    detail_pros: "장점",
    detail_cons: "단점",
    detail_why_title: "VEX를 통해 등록하는 이유?",
    detail_why_desc: "VEX는 {company}의 인증 직접 파트너입니다. 당사 링크를 통한 등록은 모두 귀하에게 직접 카운트됩니다. 독점 프로모 코드와 직접 등록 링크를 추가 비용 없이 제공합니다.",
    detail_similar: "유사 회사",
    detail_footer_partner: "인증 파트너",
    detail_footer_responsible: "18+ - 책임감 있게 플레이",
    footer_copyright: "© 2026 VEX Games — 인증 파트너 • 8개 라이선스 회사 • 17개 언어 • Provably Fair"
  },
  th: {
    back_home: "กลับไปหน้าแรก",
    detail_badge: "พันธมิตรที่ผ่านการยืนยัน VEX",
    detail_founded: "ก่อตั้ง",
    detail_stars: "ดาว",
    detail_promo_title: "รหัสโปรโมชั่นพิเศษ",
    detail_promo_hint: "ใช้รหัสนี้เมื่อลงทะเบียน",
    detail_copy_btn: "คัดลอกรหัส",
    detail_copied: "คัดลอกแล้ว!",
    detail_cta_register: "ลงทะเบียนที่",
    detail_cta_app: "ดาวน์โหลดแอป",
    detail_overview: "ภาพรวม",
    detail_table_title: "รายละเอียดบริษัท",
    detail_label_name: "ชื่อ",
    detail_label_license: "ใบอนุญาต",
    detail_label_hq: "สำนักงานใหญ่",
    detail_label_founded: "ก่อตั้ง",
    detail_label_rating: "คะแนน",
    detail_label_promo: "รหัสโปรโมชั่น",
    detail_pros_cons: "ข้อดี & ข้อเสีย",
    detail_pros: "ข้อดี",
    detail_cons: "ข้อเสีย",
    detail_why_title: "ทำไมต้องลงทะเบียนผ่าน VEX?",
    detail_why_desc: "VEX เป็นพันธมิตรที่ผ่านการยืนยันโดยตรงกับ {company} การลงทะเบียนผ่านลิงก์ของเราทุกครั้งจะนับโดยตรงสำหรับคุณ เราให้รหัสโปรโมชั่นพิเศษและลิงก์ลงทะเบียนโดยตรงโดยไม่มีค่าใช้จ่ายเพิ่มเติม",
    detail_similar: "บริษัทที่คล้ายกัน",
    detail_footer_partner: "พันธมิตรที่ผ่านการยืนยัน",
    detail_footer_responsible: "18+ - เล่นอย่างรับผิดชอบ",
    footer_copyright: "© 2026 VEX Games — พันธมิตรที่ผ่านการยืนยัน • 8 บริษัทที่ได้รับอนุญาต • 17 ภาษา • Provably Fair"
  }
};

function applyTranslations(companyName){
  var params=new URLSearchParams(window.location.search);
  var lang=params.get('lang')||localStorage.getItem('vex_lang');
  if(!lang||lang==='ar')return;
  var t=window.I18N_TRANSLATIONS[lang];
  if(!t)return;

  document.documentElement.setAttribute('lang',lang);

  document.querySelectorAll('[data-i18n]').forEach(function(el){
    var key=el.getAttribute('data-i18n');
    if(t[key]){
      if(key==='detail_cta_register'&&companyName){
        el.textContent=t[key]+' '+companyName;
      }else if(key==='detail_why_desc'&&companyName){
        el.textContent=t[key].replace('{company}',companyName);
      }else if(key==='detail_founded'){
        el.textContent=t[key]+' '+el.textContent.replace(t[key],'').trim();
      }else if(key==='detail_footer_partner'){
        el.textContent=t[key];
      }else if(key==='detail_footer_responsible'){
        el.textContent=t[key];
      }else{
        el.textContent=t[key];
      }
    }
  });
}

var companyName='{{ company.name }}';
applyTranslations(companyName);

function copyCode(btn,code){
  var params=new URLSearchParams(window.location.search);
  var lang=params.get('lang')||localStorage.getItem('vex_lang')||'ar';
  var t=window.I18N_TRANSLATIONS[lang]||window.I18N_TRANSLATIONS.ar;
  navigator.clipboard.writeText(code).then(function(){
    btn.textContent=t.detail_copied;
    btn.style.background='#16a34a';
    setTimeout(function(){btn.textContent=t.detail_copy_btn;btn.style.background='';},2000);
  }).catch(function(){
    var ta=document.createElement('textarea');
    ta.value=code;document.body.appendChild(ta);ta.select();
    document.execCommand('copy');document.body.removeChild(ta);
    btn.textContent=t.detail_copied;
    btn.style.background='#16a34a';
    setTimeout(function(){btn.textContent=t.detail_copy_btn;btn.style.background='';},2000);
  });
}
</script>
'''

# Insert before the closing </body> tag
content = content.replace('</body>', i18n_block + '</body>')

# Also remove the old inline copyCode function
old_copy_fn = '''<script>
function copyCode(btn,code){
  navigator.clipboard.writeText(code).then(function(){
    btn.textContent='تم النسخ';
    btn.style.background='#16a34a';
    setTimeout(function(){btn.textContent='نسخ الكود';btn.style.background='';},2000);
  }).catch(function(){
    var ta=document.createElement('textarea');
    ta.value=code;document.body.appendChild(ta);ta.select();
    document.execCommand('copy');document.body.removeChild(ta);
    btn.textContent='تم النسخ';
    btn.style.background='#16a34a';
    setTimeout(function(){btn.textContent='نسخ الكود';btn.style.background='';},2000);
  });
}
</script>'''
content = content.replace(old_copy_fn, '')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

i18n_count = content.count('data-i18n=')
print(f"File: {len(content)} chars, {content.count(chr(10))+1} lines")
print(f"data-i18n attributes: {i18n_count}")
print(f"I18N languages: {content.count('ar: {')}, {content.count('en: {')}, {content.count('fr: {')}, {content.count('es: {')}, {content.count('de: {')}")

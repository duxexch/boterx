#!/usr/bin/env python3
"""
Insert new translation keys into each language block of the I18N_TRANSLATIONS
object in landing.html, before the footer_responsible line.
"""

import re
import sys

FILE_PATH = r"C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html"

# Keys to insert, with translations for all 17 languages.
# Format: { lang_code: { key: value, ... }, ... }
TRANSLATIONS = {
    "ar": {
        "pros_title": "المميزات",
        "pros_instant": "دفع فوري",
        "pros_arabic": "دعم عربي",
        "pros_licensed": "مرخص رسمياً",
        "why_vex_pros_title": "لماذا VEX؟",
        "why_vex_bonus": "بونص حصري",
        "why_vex_verified": "شريك معتمد",
        "why_vex_wallet": "محفظة آمنة",
        "vex_meta_info": "Curacao 8048/JAZ • Cyprus • منذ 2024 • 4.9/5 ★ • 5000+ لاعب",
        "vex_desc": "VEX Games منصة ألعاب مالية مرخصة تعمل عبر تيليغرام والويب بـ 17 لغة. نوفر محفظة متكاملة (إيداع/سحب فوري)، نظام تعويض ذكي SVRP (100% رصيد مجمد يُفك عبر الأصدقاء)، Provably Fair بـ HMAC-SHA256، وشراكة مباشرة مع 1xPartners و MelPartners — كل تسجيل عبرنا محسوب لك، وكل إيداع محمي.",
        "vex_services_val": "8 ألعاب (مناجم/كراش/أفياتور/بلينكو/عجلة/يانصيب/نرد/سناتش)",
        "vex_support_val": "24/7 عربي/إنجليزي عبر @vex_wallet_bot",
        "vex_security_val": "تشفير كامل + حماية من التلاعب + سحب/إيداع بإشراف",
        "comp_desc_1xbet": "1xBet عملاق المراهنات العالمي بترخيص كوراساو — 1000+ سوق يومياً، بث مباشر، كازينو ضخم وسحب فوري. مع VEX تحصل على تسجيل مباشر وكود <b>VEX</b> وبونص ترحيبي حتى 130%.",
        "comp_desc_melbet": "Melbet مرخصة وموثوقة — واجهة عربية ممتازة، احتمالات عالية، دفع فوري عبر فودافون كاش وSTC Pay. سجّل عبر VEX بكود VEX.",
        "comp_desc_default": "شركة مراهنة مرخصة — مقرها في أوروبا، تأسست حديثاً، تقدم بونص ترحيبي، دفع فوري ودعم عربي. سجّل عبر VEX الآن.",
    },
    "en": {
        "pros_title": "Pros",
        "pros_instant": "Instant deposit",
        "pros_arabic": "Arabic support",
        "pros_licensed": "Licensed",
        "why_vex_pros_title": "Why VEX?",
        "why_vex_bonus": "Exclusive bonus",
        "why_vex_verified": "Verified partner",
        "why_vex_wallet": "Secure wallet",
        "vex_meta_info": "Curacao 8048/JAZ • Cyprus • Since 2024 • 4.9/5 ★ • 5000+ Players",
        "vex_desc": "VEX Games is a licensed financial gaming platform operating via Telegram and the Web in 17 languages. We provide an integrated wallet (instant deposit/withdrawal), a smart SVRP compensation system (100% frozen balance unlocked via friends), Provably Fair with HMAC-SHA256, and direct partnerships with 1xPartners and MelPartners — every registration through us is tracked for you, and every deposit is protected.",
        "vex_services_val": "8 games (Mines/Crash/Aviator/Plinko/Wheel/Lottery/Dice/Snatch)",
        "vex_support_val": "24/7 Arabic/English via @vex_wallet_bot",
        "vex_security_val": "Full encryption + anti-tampering + supervised deposit/withdrawal",
        "comp_desc_1xbet": "1xBet is a global betting giant licensed in Curacao — 1000+ daily markets, live streaming, a massive casino and instant withdrawals. With VEX you get direct registration, promo code <b>VEX</b>, and a welcome bonus up to 130%.",
        "comp_desc_melbet": "Melbet is licensed and trusted — excellent Arabic interface, high odds, instant payouts via Vodafone Cash and STC Pay. Register through VEX with code VEX.",
        "comp_desc_default": "Licensed betting company — headquartered in Europe, recently established, offering a welcome bonus, instant payouts and Arabic support. Register through VEX now.",
    },
    "fr": {
        "pros_title": "Avantages",
        "pros_instant": "Dépôt instantané",
        "pros_arabic": "Support arabe",
        "pros_licensed": "Licencié",
        "why_vex_pros_title": "Pourquoi VEX?",
        "why_vex_bonus": "Bonus exclusif",
        "why_vex_verified": "Partenaire vérifié",
        "why_vex_wallet": "Portefeuille sécurisé",
        "vex_meta_info": "Curacao 8048/JAZ • Chypre • Depuis 2024 • 4.9/5 ★ • 5000+ Joueurs",
        "vex_desc": "VEX Games est une plateforme de jeux financiers agréée opérant via Telegram et le Web en 17 langues. Nous offrons un portefeuille intégré (dépôt/retrait instantané), un système de compensation SVRP intelligent (100% de solde gelé libéré via les amis), Provably Fair avec HMAC-SHA256, et des partenariats directs avec 1xPartners et MelPartners — chaque inscription via nous est comptabilisée pour vous, et chaque dépôt est protégé.",
        "vex_services_val": "8 jeux (Mines/Crash/Aviator/Plinko/Roue/Loterie/Dés/Snatch)",
        "vex_support_val": "24/7 arabe/anglais via @vex_wallet_bot",
        "vex_security_val": "Chiffrement complet + protection anti-altération + dépôt/retrait supervisé",
        "comp_desc_1xbet": "1xBet est un géant mondial des paris agréé à Curaçao — plus de 1000 marchés quotidiens, streaming en direct, casino massif et retraits instantanés. Avec VEX, obtenez une inscription directe, le code promo <b>VEX</b> et un bonus de bienvenue jusqu'à 130%.",
        "comp_desc_melbet": "Melbet est agréé et fiable — interface arabe excellente, cotes élevées, paiements instantanés via Vodafone Cash et STC Pay. Inscrivez-vous via VEX avec le code VEX.",
        "comp_desc_default": "Société de paris agréée — basée en Europe, récemment fondée, offrant un bonus de bienvenue, des paiements instantanés et un support arabe. Inscrivez-vous via VEX maintenant.",
    },
    "es": {
        "pros_title": "Ventajas",
        "pros_instant": "Depósito instantáneo",
        "pros_arabic": "Soporte en árabe",
        "pros_licensed": "Licenciado",
        "why_vex_pros_title": "¿Por qué VEX?",
        "why_vex_bonus": "Bono exclusivo",
        "why_vex_verified": "Socio verificado",
        "why_vex_wallet": "Billetera segura",
        "vex_meta_info": "Curacao 8048/JAZ • Chipre • Desde 2024 • 4.9/5 ★ • 5000+ Jugadores",
        "vex_desc": "VEX Games es una plataforma de juegos financieros con licencia que opera a través de Telegram y la Web en 17 idiomas. Ofrecemos una billetera integrada (depósito/retiro instantáneo), un sistema de compensación SVRP inteligente (100% de saldo congelado liberado a través de amigos), Provably Fair con HMAC-SHA256, y alianzas directas con 1xPartners y MelPartners — cada registro a través de nosotros se contabiliza para ti, y cada depósito está protegido.",
        "vex_services_val": "8 juegos (Mines/Crash/Aviator/Plinko/Rueda/Lotería/Dados/Snatch)",
        "vex_support_val": "24/7 árabe/inglés vía @vex_wallet_bot",
        "vex_security_val": "Cifrado completo + protección contra manipulación + depósito/retiro supervisado",
        "comp_desc_1xbet": "1xBet es un gigante global de las apuestas con licencia de Curazao — más de 1000 mercados diarios, transmisión en vivo, casino masivo y retiros instantáneos. Con VEX obtienes registro directo, código promo <b>VEX</b> y bono de bienvenida hasta 130%.",
        "comp_desc_melbet": "Melbet está licenciada y es confiable — excelente interfaz en árabe, cuotas altas, pagos instantáneos vía Vodafone Cash y STC Pay. Regístrate a través de VEX con código VEX.",
        "comp_desc_default": "Empresa de apuestas con licencia — con sede en Europa, establecida recientemente, ofrece bono de bienvenida, pagos instantáneos y soporte en árabe. Regístrate a través de VEX ahora.",
    },
    "de": {
        "pros_title": "Vorteile",
        "pros_instant": "Sofortige Einzahlung",
        "pros_arabic": "Arabischer Support",
        "pros_licensed": "Lizenziert",
        "why_vex_pros_title": "Warum VEX?",
        "why_vex_bonus": "Exklusiver Bonus",
        "why_vex_verified": "Verifizierter Partner",
        "why_vex_wallet": "Sicheres Wallet",
        "vex_meta_info": "Curacao 8048/JAZ • Zypern • Seit 2024 • 4.9/5 ★ • 5000+ Spieler",
        "vex_desc": "VEX Games ist eine lizenzierte Finanz-Gaming-Plattform, die über Telegram und das Web in 17 Sprachen operiert. Wir bieten ein integriertes Wallet (Sofort-Einzahlung/Auszahlung), ein intelligentes SVRP-Kompensationssystem (100% eingefrorenes Guthaben wird über Freunde freigeschaltet), Provably Fair mit HMAC-SHA256 und direkte Partnerschaften mit 1xPartners und MelPartners — jede Registrierung über uns wird für Sie gezählt und jede Einzahlung ist geschützt.",
        "vex_services_val": "8 Spiele (Mines/Crash/Aviator/Plinko/Rad/Lotto/Würfel/Snatch)",
        "vex_support_val": "24/7 Arabisch/Englisch über @vex_wallet_bot",
        "vex_security_val": "Volle Verschlüsselung + Manipulationsschutz + überwachte Ein-/Auszahlung",
        "comp_desc_1xbet": "1xBet ist ein globales Wettunternehmen mit Curacao-Lizenz — über 1000 tägliche Märkte, Live-Streaming, riesiges Casino und sofortige Auszahlungen. Mit VEX erhalten Sie direkte Registrierung, Promo-Code <b>VEX</b> und Willkommensbonus bis zu 130%.",
        "comp_desc_melbet": "Melbet ist lizenziert und vertrauenswürdig — ausgezeichnete arabische Benutzeroberfläche, hohe Quoten, sofortige Auszahlungen über Vodafone Cash und STC Pay. Registrieren Sie sich über VEX mit Code VEX.",
        "comp_desc_default": "Lizenziertes Wettunternehmen — mit Sitz in Europa, kürzlich gegründet, bietet Willkommensbonus, sofortige Auszahlungen und arabischen Support. Registrieren Sie sich jetzt über VEX.",
    },
    "it": {
        "pros_title": "Vantaggi",
        "pros_instant": "Deposito istantaneo",
        "pros_arabic": "Supporto in arabo",
        "pros_licensed": "Con licenza",
        "why_vex_pros_title": "Perché VEX?",
        "why_vex_bonus": "Bonus esclusivo",
        "why_vex_verified": "Partner verificato",
        "why_vex_wallet": "Wallet sicuro",
        "vex_meta_info": "Curacao 8048/JAZ • Cipro • Dal 2024 • 4.9/5 ★ • 5000+ Giocatori",
        "vex_desc": "VEX Games è una piattaforma di giochi finanziari con licenza che opera tramite Telegram e il Web in 17 lingue. Offriamo un portafoglio integrato (deposito/prelievo istantaneo), un sistema di compensazione SVRP intelligente (100% del saldo congelato sbloccato tramite gli amici), Provably Fair con HMAC-SHA256 e partnership dirette con 1xPartners e MelPartners — ogni registrazione tramite noi è contata per te e ogni deposito è protetto.",
        "vex_services_val": "8 giochi (Mines/Crash/Aviator/Plinko/Ruota/Lotteria/Dadi/Snatch)",
        "vex_support_val": "24/7 arabo/inglese via @vex_wallet_bot",
        "vex_security_val": "Crittografia completa + protezione contro manomissioni + deposito/prelievo supervisionato",
        "comp_desc_1xbet": "1xBet è un colosso globale delle scommesse con licenza di Curaçao — oltre 1000 mercati giornalieri, streaming live, casinò immenso e prelievi istantanei. Con VEX ottieni registrazione diretta, codice promo <b>VEX</b> e bonus di benvenuto fino al 130%.",
        "comp_desc_melbet": "Melbet è licenziata e affidabile — eccellente interfaccia araba, quote alte, pagamenti istantanei tramite Vodafone Cash e STC Pay. Registrati tramite VEX con codice VEX.",
        "comp_desc_default": "Società di scommesse con licenza — con sede in Europa, fondata di recente, offre bonus di benvenuto, pagamenti istantanei e supporto in arabo. Registrati tramite VEX ora.",
    },
    "pt": {
        "pros_title": "Vantagens",
        "pros_instant": "Depósito instantâneo",
        "pros_arabic": "Suporte em árabe",
        "pros_licensed": "Licenciado",
        "why_vex_pros_title": "Por que VEX?",
        "why_vex_bonus": "Bônus exclusivo",
        "why_vex_verified": "Parceiro verificado",
        "why_vex_wallet": "Carteira segura",
        "vex_meta_info": "Curacao 8048/JAZ • Chipre • Desde 2024 • 4.9/5 ★ • 5000+ Jogadores",
        "vex_desc": "VEX Games é uma plataforma de jogos financeiros licenciada que opera via Telegram e Web em 17 idiomas. Oferecemos uma carteira integrada (depósito/saque instantâneo), um sistema inteligente de compensação SVRP (100% do saldo congelado desbloqueado via amigos), Provably Fair com HMAC-SHA256 e parcerias diretas com 1xPartners e MelPartners — todo registro feito por meio de nós é contabilizado para você, e cada depósito é protegido.",
        "vex_services_val": "8 jogos (Mines/Crash/Aviator/Plinko/Roleta/Loteria/Dados/Snatch)",
        "vex_support_val": "24/7 árabe/inglês via @vex_wallet_bot",
        "vex_security_val": "Criptografia completa + proteção contra adulteração + depósito/saque supervisionado",
        "comp_desc_1xbet": "1xBet é uma gigante global de apostas licenciada em Curacao — mais de 1000 mercados diários, transmissão ao vivo, cassino massivo e saques instantâneos. Com VEX você obtém registro direto, código promo <b>VEX</b> e bônus de boas-vindas até 130%.",
        "comp_desc_melbet": "Melbet é licenciada e confiável — excelente interface árabe, odds altas, pagamentos instantâneos via Vodafone Cash e STC Pay. Registre-se via VEX com código VEX.",
        "comp_desc_default": "Empresa de apostas licenciada — sediada na Europa, fundada recentemente, oferece bônus de boas-vindas, pagamentos instantâneos e suporte em árabe. Registre-se via VEX agora.",
    },
    "ru": {
        "pros_title": "Преимущества",
        "pros_instant": "Мгновенный депозит",
        "pros_arabic": "Арабская поддержка",
        "pros_licensed": "Лицензирован",
        "why_vex_pros_title": "Почему VEX?",
        "why_vex_bonus": "Эксклюзивный бонус",
        "why_vex_verified": "Проверенный партнёр",
        "why_vex_wallet": "Безопасный кошелёк",
        "vex_meta_info": "Curacao 8048/JAZ • Кипр • С 2024 • 4.9/5 ★ • 5000+ игроков",
        "vex_desc": "VEX Games — лицензированная платформа финансовых игр, работающая через Telegram и Веб на 17 языках. Мы предлагаем интегрированный кошелёк (мгновенный депозит/вывод), умную систему компенсации SVRP (100% замороженный баланс разблокируется через друзей), Provably Fair с HMAC-SHA256 и прямые партнёрства с 1xPartners и MelPartners — каждая регистрация через нас засчитывается вам, и каждый депозит защищён.",
        "vex_services_val": "8 игр (Mines/Crash/Aviator/Plinko/Колесо/Лотерея/Кости/Snatch)",
        "vex_support_val": "24/7 арабский/английский через @vex_wallet_bot",
        "vex_security_val": "Полное шифрование + защита от подделки + контролируемые депозит/вывод",
        "comp_desc_1xbet": "1xBet — мировой гигант ставок с лицензией Кюрасао — более 1000 рынков в день, прямые трансляции, огромное казино и мгновенные выплаты. С VEX вы получаете прямую регистрацию, промокод <b>VEX</b> и приветственный бонус до 130%.",
        "comp_desc_melbet": "Melbet лицензирована и надёжна — отличный арабский интерфейс, высокие коэффициенты, мгновенные выплаты через Vodafone Cash и STC Pay. Регистрируйтесь через VEX с кодом VEX.",
        "comp_desc_default": "Лицензированная букмекерская компания — штаб-квартира в Европе, основана недавно, предлагает приветственный бонус, мгновенные выплаты и арабскую поддержку. Регистрируйтесь через VEX сейчас.",
    },
    "zh": {
        "pros_title": "优势",
        "pros_instant": "即时存款",
        "pros_arabic": "阿拉伯语支持",
        "pros_licensed": "持牌经营",
        "why_vex_pros_title": "为什么选择VEX？",
        "why_vex_bonus": "独家奖金",
        "why_vex_verified": "认证合作伙伴",
        "why_vex_wallet": "安全钱包",
        "vex_meta_info": "Curacao 8048/JAZ • 塞浦路斯 • 成立于2024年 • 4.9/5 ★ • 5000+玩家",
        "vex_desc": "VEX Games 是一个持牌金融游戏平台，通过Telegram和网页在17种语言中运营。我们提供集成钱包（即时存取款）、智能SVRP补偿系统（100%冻结余额通过朋友解锁）、基于HMAC-SHA256的Provably Fair公平验证，以及与1xPartners和MelPartners的直接合作——通过我们注册的每一次都被为您计算，每一笔存款都受到保护。",
        "vex_services_val": "8款游戏（Mines/Crash/Aviator/Plinko/轮盘/彩票/骰子/Snatch）",
        "vex_support_val": "24/7阿拉伯语/英语通过@vex_wallet_bot",
        "vex_security_val": "完全加密+防篡改+监督存款/取款",
        "comp_desc_1xbet": "1xBet是全球博彩巨头，持有库拉索牌照——每天1000+市场、直播、大型赌场和即时取款。通过VEX您可直接注册，使用优惠码<b>VEX</b>，享受高达130%的迎新奖金。",
        "comp_desc_melbet": "Melbet持牌且可信——优秀的阿拉伯语界面、高赔率、通过Vodafone Cash和STC Pay即时支付。通过VEX注册，使用代码VEX。",
        "comp_desc_default": "持牌博彩公司——总部位于欧洲，新近成立，提供迎新奖金、即时支付和阿拉伯语支持。立即通过VEX注册。",
    },
    "tr": {
        "pros_title": "Avantajlar",
        "pros_instant": "Anında yatırım",
        "pros_arabic": "Arapça destek",
        "pros_licensed": "Lisanslı",
        "why_vex_pros_title": "Neden VEX?",
        "why_vex_bonus": "Özel bonus",
        "why_vex_verified": "Doğrulanmış partner",
        "why_vex_wallet": "Güvenli cüzdan",
        "vex_meta_info": "Curacao 8048/JAZ • Kıbrıs • 2024'ten beri • 4.9/5 ★ • 5000+ Oyuncu",
        "vex_desc": "VEX Games, Telegram ve Web üzerinden 17 dilde faaliyet gösteren lisanslı bir finansal oyun platformudur. Entegre bir cüzdan (anında yatırım/çekme), akıllı SVRP tazminat sistemi (arkadaşlar aracılığıyla açılan %100 dondurulmuş bakiye), HMAC-SHA256 ile Provably Fair ve 1xPartners ile MelPartners ile doğrudan ortaklıklar sunuyoruz — bizim üzerimizden yapılan her kayıt sizin için sayılır ve her yatırım korunur.",
        "vex_services_val": "8 oyun (Mines/Crash/Aviator/Plinko/Çarkı/ Piyango/Zar/Snatch)",
        "vex_support_val": "24/7 Arapça/İngilizce @vex_wallet_bot üzerinden",
        "vex_security_val": "Tam şifreleme + manipülasyon koruması + denetimli yatırım/çekme",
        "comp_desc_1xbet": "1xBet, Curacao lisanslı küresel bir bahis devi — günlük 1000+ pazar, canlı yayın, devasa casino ve anında çekimler. VEX ile doğrudan kayıt, promosyon kodu <b>VEX</b> ve %130'a varan hoş geldin bonusu alırsınız.",
        "comp_desc_melbet": "Melbet lisanslı ve güvenilir — mükemmel Arapça arayüz, yüksek oranlar, Vodafone Cash ve STC Pay ile anında ödemeler. VEX üzerinden kod VEX ile kayıt olun.",
        "comp_desc_default": "Lisanslı bahis şirketi — Avrupa merkezli, yakın zamanda kurulmuş, hoş geldin bonusu, anında ödemeler ve Arapça destek sunuyor. Şimdi VEX üzerinden kayıt olun.",
    },
    "ur": {
        "pros_title": "فوائد",
        "pros_instant": "فوری ڈپازٹ",
        "pros_arabic": "عربی سپورٹ",
        "pros_licensed": "لائسنس یافتہ",
        "why_vex_pros_title": "VEX کیوں؟",
        "why_vex_bonus": "خصوصی بونس",
        "why_vex_verified": "تصدیق شدہ پارٹنر",
        "why_vex_wallet": "محفوظ والیٹ",
        "vex_meta_info": "Curacao 8048/JAZ • قبرص • 2024 سے • 4.9/5 ★ • 5000+ کھلاڑی",
        "vex_desc": "VEX Games ایک لائسنس یافتہ مالی گیمز پلیٹ فارم ہے جو 17 زبانوں میں ٹیلیگرام اور ویب کے ذریعے کام کرتی ہے۔ ہم مربوط والیٹ (فوری ڈپازٹ/واپسی)، ذہین SVRP کمپنسیشن سسٹم (100% منجمد بیلنس دوستوں کے ذریعے کھلتا ہے)، HMAC-SHA256 کے ساتھ Provably Fair، اور 1xPartners اور MelPartners کے ساتھ براہ راست شراکتداری فراہم کرتے ہیں — ہمارے ذریعے ہر رجسٹریشن آپ کے لیے گنتی ہے، اور ہر ڈپازٹ محفوظ ہے۔",
        "vex_services_val": "8 گیمز (Mines/Crash/Aviator/Plinko/چرخ/لٹری/پسے/Snatch)",
        "vex_support_val": "24/7 عربی/انگریزی @vex_wallet_bot کے ذریعے",
        "vex_security_val": "مکمل خفیہ کاری + چھیڑ چھاڑ سے حفاظت + نگرانی والے ڈپازٹ/واپسی",
        "comp_desc_1xbet": "1xBet کوراساو لائسنس کے ساتھ ایک عالمی بیٹنگ کاچھا — روزانہ 1000+ مارکیٹس، لائیو اسٹریمنگ، وسیع کیزینو اور فوری واپسیاں۔ VEX کے ساتھ آپ کو براہ راست رجسٹریشن، پرومو کوڈ <b>VEX</b> اور 130% تک خوش آمدید بونس ملتا ہے۔",
        "comp_desc_melbet": "Melbet لائسنس یافتہ اور قابل اعتماد ہے — بہترین عربی انٹرفیس، اونچے امکانات، Vodafone Cash اور STC Pay کے ذریعے فوری ادائیگیاں۔ VEX کے ذریعے کوڈ VEX کے ساتھ رجسٹر کریں۔",
        "comp_desc_default": "لائسنس یافتہ بیٹنگ کمپنی — یورپ میں مرکز، حال ہی میں قائم، خوش آمدید بونس، فوری ادائیگیاں اور عربی سپورٹ فراہم کرتی ہے۔ اب VEX کے ذریعے رجسٹر کریں۔",
    },
    "hi": {
        "pros_title": "फ़ायदे",
        "pros_instant": "तत्काल जमा",
        "pros_arabic": "अरबी सहायता",
        "pros_licensed": "लाइसेंस प्राप्त",
        "why_vex_pros_title": "VEX क्यों?",
        "why_vex_bonus": "विशेष बोनस",
        "why_vex_verified": "सत्यापित पार्टनर",
        "why_vex_wallet": "सुरक्षित वॉलेट",
        "vex_meta_info": "Curacao 8048/JAZ • साइप्रस • 2024 से • 4.9/5 ★ • 5000+ खिलाड़ी",
        "vex_desc": "VEX Games एक लाइसेंस प्राप्त वित्तीय गेमिंग प्लेटफ़ॉर्म है जो टेलीग्राम और वेब के माध्यम से 17 भाषाओं में संचालित होता है। हम एक एकीकृत वॉलेट (तत्काल जमा/निकासी), एक स्मार्ट SVRP क्षतिपूर्ति प्रणाली (100% फ़्रीज़ किया गया बैलेंस दोस्तों के माध्यम से अनलॉक होता है), HMAC-SHA256 के साथ Provably Fair, और 1xPartners और MelPartners के साथ सीधी साझेदारी प्रदान करते हैं — हमारे माध्यम से हर पंजीकरण आपके लिए गिना जाता है, और हर जमा सुरक्षित है।",
        "vex_services_val": "8 गेम्स (Mines/Crash/Aviator/Plinko/पहिया/लॉटरी/पासे/Snatch)",
        "vex_support_val": "24/7 अरबी/अंग्रेज़ी @vex_wallet_bot के माध्यम से",
        "vex_security_val": "पूर्ण एन्क्रिप्शन + छेड़छाड़ से सुरक्षा + देखरेख वाला जमा/निकासी",
        "comp_desc_1xbet": "1xBet कोरासाओ लाइसेंस वाली वैश्विक बेटिंग दिग्गज — रोज़ाना 1000+ बाज़ार, लाइव स्ट्रीमिंग, विशाल कैसीनो और तत्काल निकासी। VEX के साथ आपको सीधा पंजीकरण, प्रोमो कोड <b>VEX</b> और 130% तक स्वागत बोनस मिलता है।",
        "comp_desc_melbet": "Melbet लाइसेंस प्राप्त और विश्वसनीय है — उत्कृष्ट अरबी इंटरफ़ेस, उच्च ऑड्स, Vodafone Cash और STC Pay के माध्यम से तत्काल भुगतान। VEX के माध्यम से कोड VEX के साथ पंजीकरण करें।",
        "comp_desc_default": "लाइसेंस प्राप्त बेटिंग कंपनी — यूरोप में मुख्यालय, हाल ही में स्थापित, स्वागत बोनस, तत्काल भुगतान और अरबी सहायता प्रदान करती है। अब VEX के माध्यम से पंजीकरण करें।",
    },
    "fa": {
        "pros_title": "مزایا",
        "pros_instant": "واریز فوری",
        "pros_arabic": "پشتیبانی عربی",
        "pros_licensed": "دارای مجوز",
        "why_vex_pros_title": "چرا VEX؟",
        "why_vex_bonus": "جایزه انحصاری",
        "why_vex_verified": "شریک تأیید شده",
        "why_vex_wallet": "کیف پول امن",
        "vex_meta_info": "Curacao 8048/JAZ • قبرس • از 2024 • 4.9/5 ★ • 5000+ بازیکن",
        "vex_desc": "بازی‌های VEX یک پلتفرم بازی مالی دارای مجوز است که از طریق تلگرام و وب در 17 زبان فعالیت می‌کند. ما یک کیف پول یکپارچه (واریز/برداشت فوری)، سیستم جبران خسارت هوشمند SVRP (100% موجودی منجمد از طریق دوستان آزاد می‌شود)، Provably Fair با HMAC-SHA256 و مشارکت‌های مستقیم با 1xPartners و MelPartners ارائه می‌دهیم — هر ثبت‌نام از طریق ما برای شما محاسبه می‌شود و هر واریز محافظت شده است.",
        "vex_services_val": "8 بازی (Mines/Crash/Aviator/Plinko/چرخ/لاتاری/تاس/Snatch)",
        "vex_support_val": "24/7 عربی/انگلیسی از طریق @vex_wallet_bot",
        "vex_security_val": "رمزنگاری کامل + محافظت در برابر دستکاری + واریز/برداشت تحت نظارت",
        "comp_desc_1xbet": "1xBet غول جهانی شرط‌بندی با مجوز کوراسائو — بیش از 1000 بازار روزانه، پخش زنده، کازینوی عظیم و برداشت‌های فوری. با VEX ثبت‌نام مستقیم، کد تبلیغاتی <b>VEX</b> و جایزه خوش‌آمدگویی تا 130% دریافت کنید.",
        "comp_desc_melbet": "Melbet دارای مجوز و قابل اعتماد — رابط کاربری عربی عالی، شانس‌های بالا، پرداخت‌های فوری از طریق Vodafone Cash و STC Pay. از طریق VEX با کد VEX ثبت‌نام کنید.",
        "comp_desc_default": "شرکت شرط‌بندی دارای مجوز — دفتر مرکزی در اروپا، اخیراً تأسیس شده، ارائه جایزه خوش‌آمدگویی، پرداخت‌های فوری و پشتیبانی عربی. همین حالا از طریق VEX ثبت‌نام کنید.",
    },
    "id": {
        "pros_title": "Keunggulan",
        "pros_instant": "Deposit instan",
        "pros_arabic": "Dukungan bahasa Arab",
        "pros_licensed": "Berslisensi",
        "why_vex_pros_title": "Mengapa VEX?",
        "why_vex_bonus": "Bonus eksklusif",
        "why_vex_verified": "Mitra terverifikasi",
        "why_vex_wallet": "Dompet aman",
        "vex_meta_info": "Curacao 8048/JAZ • Siprus • Sejak 2024 • 4.9/5 ★ • 5000+ Pemain",
        "vex_desc": "VEX Games adalah platform game keuangan berlisensi yang beroperasi melalui Telegram dan Web dalam 17 bahasa. Kami menyediakan dompet terintegrasi (deposit/penarikan instan), sistem kompensasi SVRP cerdas (100% saldo beku dibuka melalui teman), Provably Fair dengan HMAC-SHA256, dan kemitraan langsung dengan 1xPartners dan MelPartners — setiap pendaftaran melalui kami dihitung untuk Anda, dan setiap deposit dilindungi.",
        "vex_services_val": "8 game (Mines/Crash/Aviator/Plinko/Roda/Lotere/Dadu/Snatch)",
        "vex_support_val": "24/7 bahasa Arab/Inggris melalui @vex_wallet_bot",
        "vex_security_val": "Enkripsi penuh + perlindungan anti-pengubahan + deposit/penarikan terawasi",
        "comp_desc_1xbet": "1xBet adalah raksasa taruhan global berlisensi Curacao — 1000+ pasar harian, streaming langsung, kasino masif dan penarikan instan. Dengan VEX Anda mendapatkan pendaftaran langsung, kode promo <b>VEX</b> dan bonus sambutan hingga 130%.",
        "comp_desc_melbet": "Melbet berslisensi dan tepercaya — antarmuka Arab yang sangat baik, odds tinggi, pembayaran instan melalui Vodafone Cash dan STC Pay. Daftar melalui VEX dengan kode VEX.",
        "comp_desc_default": "Perusahaan taruhan berlisensi — berkantor pusat di Eropa, baru didirikan, menawarkan bonus sambutan, pembayaran instan dan dukungan bahasa Arab. Daftar melalui VEX sekarang.",
    },
    "ja": {
        "pros_title": "メリット",
        "pros_instant": "即時入金",
        "pros_arabic": "アラビア語サポート",
        "pros_licensed": "ライセンス取得",
        "why_vex_pros_title": "なぜVEX？",
        "why_vex_bonus": "限定ボーナス",
        "why_vex_verified": "認証パートナー",
        "why_vex_wallet": "安全なウォレット",
        "vex_meta_info": "Curacao 8048/JAZ • キプロス • 2024年〜 • 4.9/5 ★ • 5000+プレイヤー",
        "vex_desc": "VEX Gamesは、TelegramとWebで17言語で運営されているライセンス取得済みの金融ゲームプラットフォームです。統合ウォレット（即時入金/出金）、スマートなSVRP補償システム（100%の凍結残高が友人を通じて解除）、HMAC-SHA256を備えたProvably Fair、1xPartnersおよびMelPartnersとの直接提携を提供しています — 当社を通じたすべての登録はお客様のためにカウントされ、すべての入金は保護されます。",
        "vex_services_val": "8ゲーム（Mines/Crash/Aviator/Plinko/ルーレット/宝くじ/サイコロ/Snatch）",
        "vex_support_val": "24/7アラビア語/英語 @vex_wallet_bot経由",
        "vex_security_val": "完全暗号化 + 改ざん防止 + 監視付き入金/出金",
        "comp_desc_1xbet": "1xBetはキュラソーのライセンスを持つ世界的なベッティングの巨頭 — 1000以上の日間市場、ライブストリーミング、大規模なカジノと即時出金。VEXを通じて直接登録、プロモーションコード<b>VEX</b>、最大130%のウェルカムボーナスが得られます。",
        "comp_desc_melbet": "Melbetはライセンス取得済みで信頼できる — 優れたアラビア語インターフェース、高オッズ、Vodafone CashとSTC Payによる即時払い。VEXを通じてコードVEXで登録してください。",
        "comp_desc_default": "ライセンス取得済みベッティング会社 — ヨーロッパに本社を置き、最近設立、ウェルカムボーナス、即時払いとアラビア語サポートを提供。今すぐVEXを通じて登録してください。",
    },
    "ko": {
        "pros_title": "장점",
        "pros_instant": "즉시 입금",
        "pros_arabic": "아랍어 지원",
        "pros_licensed": "라이선스 보유",
        "why_vex_pros_title": "왜 VEX인가?",
        "why_vex_bonus": "독점 보너스",
        "why_vex_verified": "인증 파트너",
        "why_vex_wallet": "안전한 지갑",
        "vex_meta_info": "Curacao 8048/JAZ • 키프로스 • 2024년 이후 • 4.9/5 ★ • 5000+ 플레이어",
        "vex_desc": "VEX Games는 텔레그램과 웹을 통해 17개 언어로 운영되는 라이선스 보유 금융 게임 플랫폼입니다. 통합 지갑(즉시 입금/출금), 스마트 SVRP 보상 시스템(100% 동결 잔액이 친구를 통해 해제), HMAC-SHA256 기반 Provably Fair, 1xPartners 및 MelPartners와의 직접 파트너십을 제공합니다 — 우리를 통해 등록한 모든 것이 귀하에게 계산되며, 모든 입금이 보호됩니다.",
        "vex_services_val": "8개 게임 (Mines/Crash/Aviator/Plinko/휠/복권/주사위/Snatch)",
        "vex_support_val": "24/7 아랍어/영어 @vex_wallet_bot를 통해",
        "vex_security_val": "완전 암호화 + 변조 방지 + 감독하의 입금/출금",
        "comp_desc_1xbet": "1xBet은 퀴라소 라이선스를 보유한 글로벌 베팅 거물 — 매일 1000+ 마켓, 라이브 스트리밍, 대규모 카지노와 즉시 출금. VEX를 통해 직접 등록, 프로모션 코드 <b>VEX</b>, 최대 130% 환영 보너스를 받으세요.",
        "comp_desc_melbet": "Melbet은 라이선스를 보유하고 신뢰할 수 있습니다 — 우수한 아랍어 인터페이스, 높은 배당률, Vodafone Cash와 STC Pay를 통한 즉시 지급. VEX를 통해 코드 VEX로 등록하세요.",
        "comp_desc_default": "라이선스 보유 베팅 회사 — 유럽에 본사를 두고 최근 설립, 환영 보너스, 즉시 지급 및 아랍어 지원을 제공합니다. 지금 VEX를 통해 등록하세요.",
    },
    "th": {
        "pros_title": "ข้อดี",
        "pros_instant": "ฝากเงินทันที",
        "pros_arabic": "รองรับภาษาอาหรับ",
        "pros_licensed": "ได้รับอนุญาต",
        "why_vex_pros_title": "ทำไมต้อง VEX?",
        "why_vex_bonus": "โบนัสพิเศษ",
        "why_vex_verified": "พันธมิตรที่ผ่านการตรวจสอบ",
        "why_vex_wallet": "กระเป๋าเงินปลอดภัย",
        "vex_meta_info": "Curacao 8048/JAZ • ไซปรัส • ตั้งแต่ 2024 • 4.9/5 ★ • 5000+ ผู้เล่น",
        "vex_desc": "VEX Games เป็นแพลตฟอร์มเกมการเงินที่ได้รับอนุญาตซึ่งดำเนินการผ่าน Telegram และ Web ใน 17 ภาษา เรามีกระเป๋าเงินแบบบูรณาการ (ฝาก/ถอนทันที) ระบบชดเชย SVRP อัจฉริยะ (ยอดเงินที่ถูกแช่แข็ง 100% จะถูกปลดล็อกผ่านเพื่อน) Provably Fair ด้วย HMAC-SHA256 และความร่วมมือโดยตรงกับ 1xPartners และ MelPartners — การลงทะเบียนทุกครั้งผ่านเราจะถูกนับสำหรับคุณ และการฝากทุกครั้งได้รับการคุ้มครอง",
        "vex_services_val": "8 เกม (Mines/Crash/Aviator/Plinko/วงล้อ/ลอตเตอรี/ลูกเต๋า/Snatch)",
        "vex_support_val": "24/7 ภาษาอาหรับ/อังกฤษ ผ่าน @vex_wallet_bot",
        "vex_security_val": "การเข้ารหัสเต็มรูปแบบ + ป้องกันการดัดแปลง + ฝาก/ถอนภายใต้การดูแล",
        "comp_desc_1xbet": "1xBet เป็นยักษ์ใหญ่ระดับโลกด้านการเดิมพันที่ได้รับอนุญาตจากคูราเซา — ตลาดมากกว่า 1000 แห่งต่อวัน สตรีมมิงแบบสด คาสิโนขนาดใหญ่และการถอนเงินทันที ผ่าน VEX คุณจะได้รับการลงทะเบียนโดยตรง รหัสโปรโมชั่น <b>VEX</b> และโบนัสต้อนรับสูงสุด 130%",
        "comp_desc_melbet": "Melbet ได้รับอนุญาตและน่าเชื่อถือ — อินเทอร์เฟซภาษาอาหรับที่ยอดเยี่ยม อัตราต่อรองสูง การจ่ายเงินทันทีผ่าน Vodafone Cash และ STC Pay ลงทะเบียนผ่าน VEX ด้วยรหัส VEX",
        "comp_desc_default": "บริษัทเดิมพันที่ได้รับอนุญาต — สำนักงานใหญ่ในยุโรป ก่อตั้งเมื่อเร็วๆ นี้ เสนอโบนัสต้อนรับ การจ่ายเงินทันทีและการสนับสนุนภาษาอาหรับ ลงทะเบียนผ่าน VEX ตอนนี้",
    },
}

# Keys in insertion order
KEY_ORDER = [
    "pros_title",
    "pros_instant",
    "pros_arabic",
    "pros_licensed",
    "why_vex_pros_title",
    "why_vex_bonus",
    "why_vex_verified",
    "why_vex_wallet",
    "vex_meta_info",
    "vex_desc",
    "vex_services_val",
    "vex_support_val",
    "vex_security_val",
    "comp_desc_1xbet",
    "comp_desc_melbet",
    "comp_desc_default",
]


def escape_js_string(s):
    """Escape a string for use in a JavaScript single-quoted string literal."""
    # Replace backslash first, then single quotes and newlines
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    return s


def build_insert_block(lang_code):
    """Build the JavaScript lines to insert before footer_responsible."""
    trans = TRANSLATIONS[lang_code]
    lines = []
    for key in KEY_ORDER:
        val = trans[key]
        escaped = escape_js_string(val)
        lines.append(f"    {key}: '{escaped}',")
    return "\n".join(lines)


def main():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    for lang_code in TRANSLATIONS:
        insert_block = build_insert_block(lang_code)

        # Find the pattern: inside the lang block, find footer_responsible
        # We look for the first occurrence of `    footer_responsible:` after the lang block start
        # and insert before it.
        # The pattern in the file looks like:
        #   footer_copyright: "...",
        #     footer_responsible: "..."
        #
        # We need to find "footer_responsible" within each language block.
        # A reliable approach: find `    footer_responsible:` and insert before it,
        # but only once per language.

        # Search for the lang block start marker
        lang_start_pattern = f"  {lang_code}: {{"
        lang_start_idx = content.find(lang_start_pattern)
        if lang_start_idx == -1:
            # Try without spaces (some blocks may have different formatting)
            lang_start_pattern = f"  {lang_code}:{{"
            lang_start_idx = content.find(lang_start_pattern)
            if lang_start_idx == -1:
                print(f"WARNING: Could not find language block '{lang_code}'")
                continue

        # Find footer_responsible after the lang block start
        footer_pattern = "    footer_responsible:"
        footer_idx = content.find(footer_pattern, lang_start_idx)
        if footer_idx == -1:
            print(f"WARNING: Could not find footer_responsible in lang '{lang_code}'")
            continue

        # Make sure we haven't gone past the end of this lang block
        # by checking that there's no next lang block before footer_idx
        all_langs = ['ar', 'en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'zh', 'tr', 'ur', 'hi', 'fa', 'id', 'ja', 'ko', 'th']
        current_lang_idx = all_langs.index(lang_code)
        if current_lang_idx < len(all_langs) - 1:
            next_lang = all_langs[current_lang_idx + 1]
            next_lang_pattern = f"  {next_lang}: {{"
            next_lang_idx = content.find(next_lang_pattern, lang_start_idx)
            if next_lang_idx != -1 and footer_idx > next_lang_idx:
                print(f"WARNING: footer_responsible for '{lang_code}' appears after next lang block")
                continue

        # Insert the new keys before footer_responsible
        content = content[:footer_idx] + insert_block + "\n" + content[footer_idx:]
        print(f"Inserted keys for lang '{lang_code}'")

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("Done! File updated successfully.")


if __name__ == "__main__":
    main()

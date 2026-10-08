import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the I18N_TRANSLATIONS block and replace it entirely
start_marker = 'window.I18N_TRANSLATIONS = {'
end_marker = '};'

start_idx = content.find(start_marker)
if start_idx == -1:
    print("Could not find I18N_TRANSLATIONS start")
    sys.exit(1)

# Find the closing };
depth = 0
idx = start_idx + len(start_marker) - 1
while idx < len(content):
    if content[idx] == '{':
        depth += 1
    elif content[idx] == '}':
        depth -= 1
        if depth == 0:
            end_idx = idx + 1
            break
    idx += 1

old_block = content[start_idx:end_idx]
print(f"Old I18N block: {len(old_block)} chars")

new_i18n = r'''window.I18N_TRANSLATIONS = {
  ar: {
    hero_badge: "\u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f \u2014 \u062a\u0631\u062e\u064a\u0635 \u0643\u0648\u0631\u0627\u0633\u0627\u0648 8048/JAZ",
    hero_title: "\u062f\u0644\u064a\u0644\u0643 \u0627\u0644\u0639\u0627\u0644\u0645\u064a <span>\u0644\u0623\u0641\u0636\u0644 \u0634\u0631\u0643\u0627\u062a \u0627\u0644\u0645\u0631\u0627\u0647\u0646\u0627\u0629</span> \u0627\u0644\u0645\u0631\u062e\u0635\u0629",
    hero_subtitle: "\u0645\u0631\u0627\u062c\u0639\u0627\u062a \u062e\u0628\u064a\u0631\u0629\u060c \u062a\u0631\u0627\u062e\u064a\u0635 \u062d\u0642\u064a\u0642\u064a\u0629\u060c \u0623\u0643\u0648\u0627\u062f \u0628\u0631\u0648\u0645\u0648 \u062d\u0635\u0631\u064a\u0629 \u0648\u0631\u0648\u0627\u0628\u0637 \u062a\u0633\u062c\u064a\u0644 \u0645\u0628\u0627\u0634\u0631\u0629 \u2014 VEX \u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f \u0645\u0639 1xBet \u0648 Melbet \u0648 6 \u0634\u0631\u0643\u0627\u062a \u0643\u0628\u0631\u0649. \u0627\u062e\u062a\u0631 \u0627\u0644\u0623\u0641\u0636\u0644\u060c \u0633\u062c\u0651\u0644 \u0641\u064a \u062b\u0648\u0627\u0646\u064a\u0645\u060c \u0648\u0627\u0644\u0639\u0628 \u0628\u062b\u0642\u0629.",
    cta_companies: "\u0627\u0633\u062a\u0639\u0631\u0636 \u0627\u0644\u0634\u0631\u0643\u0627\u062a",
    cta_games: "\u0623\u0644\u0639\u0627\u0628\u064a \u0639\u0644\u0649 \u0627\u0644\u0648\u064a\u0628",
    cta_bot: "@vex_wallet_bot",
    trust_licensed: "8 \u0634\u0631\u0643\u0627\u062a \u0645\u0631\u062e\u0635\u0629",
    trust_langs: "17 \u0644\u063a\u0629",
    trust_fair: "Provably Fair",
    trust_instant: "\u0625\u064a\u062f\u0627\u0639 \u0641\u0648\u0631\u064a",
    companies_title: "\u0623\u0641\u0636\u0644 \u0627\u0644\u0634\u0631\u0643\u0627\u062a \u0627\u0644\u0645\u0631\u062e\u0635\u0629 \u2014 \u0645\u0631\u0627\u062c\u0639\u0629 \u0634\u0627\u0645\u0644\u0629",
    companies_sub: "\u0643\u0644 \u0634\u0631\u0643\u0629 \u0646\u0631\u0627\u062c\u0639\u0647\u0627 \u0643\u0623\u0646\u0647\u0627 \u0645\u0646\u062a\u062c\u0646\u0627 \u2014 \u0627\u0644\u062a\u0631\u062e\u064a\u0635\u060c \u0627\u0644\u0645\u0642\u0631\u060c \u0633\u0646\u0629 \u0627\u0644\u062a\u0623\u0633\u064a\u0633\u060c \u0627\u0644\u0645\u0645\u064a\u0632\u0627\u062a \u0648\u0627\u0644\u0639\u064a\u0648\u0628\u060c \u0643\u0648\u062f \u0627\u0644\u0628\u0631\u0648\u0645\u0648 \u0648\u0631\u0627\u0628\u0637 \u0627\u0644\u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u0645\u0628\u0627\u0634\u0631",
    comp_license: "\u0627\u0644\u062a\u0631\u062e\u064a\u0635",
    comp_headquarters: "\u0627\u0644\u0645\u0642\u0631",
    comp_founded: "\u0627\u0644\u062a\u0623\u0633\u064a\u0633",
    comp_promo: "\u0643\u0648\u062f \u0627\u0644\u0628\u0631\u0648\u0645\u0648",
    comp_cta_register: "\u0633\u062c\u0651\u0644 \u0641\u064a",
    comp_cta_details: "\u062a\u0641\u0627\u0635\u064a\u0644",
    badge_trusted: "\u0645\u0648\u062b\u0648\u0642",
    download_app: "\u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u062a\u0637\u0628\u064a\u0642",
    features_title: "\u0627\u0644\u0645\u0645\u064a\u0632\u0627\u062a",
    why_vex_title: "\u0644\u0645\u0627\u0630\u0627 VEX\u061f",
    vex_title: "VEX Games \u2014 \u0634\u0631\u064a\u0643\u0643 \u0627\u0644\u0645\u0639\u062a\u0645\u062f",
    vex_subtitle: "\u0644\u0633\u0646\u0627 \u0645\u062c\u0631\u062f \u062f\u0644\u064a\u0644 \u2014 \u0646\u062d\u0646 \u0634\u0631\u0643\u0629 \u0645\u0631\u0627\u0647\u0646\u0627\u062a \u0648\u0623\u0644\u0639\u0627\u0628 \u0645\u0631\u062e\u0635\u0629 \u0628\u062d\u062f \u062b\u062f\u0647\u0627",
    vex_badge: "\u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f",
    vex_license: "\u0627\u0644\u062a\u0631\u062e\u064a\u0635",
    vex_services: "\u0627\u0644\u062e\u062f\u0645\u0627\u062a",
    vex_support: "\u0627\u0644\u062f\u0639\u0645",
    vex_security: "\u0627\u0644\u0623\u0645\u0627\u0646",
    vex_start: "\u0627\u0628\u062f\u0623 \u0645\u0639 VEX",
    vex_how: "\u0643\u064a\u0641 \u0646\u0639\u0645\u0644\u061f",
    how_title: "\u0643\u064a\u0641 \u062a\u0628\u062f\u0623 \u0641\u064a 3 \u062e\u0637\u0648\u0627\u062a",
    how_subtitle: "\u0627\u062e\u062a\u0631 \u0634\u0631\u0643\u0629\u060c \u0633\u062c\u0651\u0644 \u0628\u0631\u0627\u0628\u0637 VEX\u060c \u0623\u0648\u062f\u0639 \u0648\u0627\u0644\u0639\u0628 \u2014 \u0643\u0644 \u062e\u0637\u0648\u0629 \u0645\u062d\u0633\u0648\u0628\u0629",
    step1_title: "\u0627\u062e\u062a\u0631 \u0634\u0631\u0643\u0629",
    step1_desc: "\u0642\u0627\u0631\u0646 \u0627\u0644\u062a\u0631\u0627\u062e\u064a\u0635 \u0648\u0627\u0644\u062a\u0642\u064a\u064a\u0645\u0627\u062a \u0623\u0639\u0644\u0627\u0647",
    step2_title: "\u0633\u062c\u0651\u0644 \u0639\u0628\u0631 VEX",
    step2_desc: "\u0627\u0636\u063a\u0637 <b>\u0633\u062c\u0651\u0644</b> \u2192 \u0631\u0627\u0628\u0637 \u0625\u062d\u0627\u0644\u062a\u0643 \u0627\u0644\u062e\u0627\u0635 \u064a\u0641\u062a\u062d",
    step3_title: "\u0623\u0648\u062f\u0639 \u0648\u0627\u0644\u0639\u0628",
    step3_desc: "\u0645\u062d\u0641\u0638\u0629 VEX + \u062a\u0639\u0648\u064a\u0636 100% + Provably Fair",
    faq_title: "\u0623\u0633\u0626\u0644\u0629 \u0634\u0627\u0626\u0639\u0629 \u2014 \u062f\u0644\u064a\u0644 \u0627\u0644\u0645\u0631\u0627\u0647\u0646\u0629 \u0627\u0644\u0639\u0627\u0644\u0645\u064a",
    faq_q1: "\u0647\u0644 \u0627\u0644\u0634\u0631\u0643\u0627\u062a \u0645\u0631\u062e\u0635\u0629\u061f",
    faq_a1: "\u0646\u0639\u0645 \u2014 \u0643\u0644 \u0627\u0644\u0634\u0631\u0643\u0627\u062a \u0627\u0644\u0645\u0639\u0631\u0648\u0636\u0629 \u0645\u0631\u062e\u0635\u0629 \u0643\u0648\u0631\u0627\u0633\u0627\u0648 8048/JAZ \u0623\u0648 \u0645\u0627 \u064a\u0639\u0627\u062f\u0644\u0647\u0627\u060c \u0648\u0645\u0642\u0631\u0627\u062a\u0647\u0627 \u0641\u064a \u0642\u0628\u0631\u0635/\u0645\u0627\u0644\u0637\u0627. VEX \u062a\u0639\u0631\u0636 \u0641\u0642\u0637 \u0627\u0644\u0645\u0631\u062e\u0635.",
    faq_q2: "\u0645\u0627 \u0647\u0648 \u0643\u0648\u062f \u0627\u0644\u0628\u0631\u0648\u0645\u0648\u061f",
    faq_a2: "\u0643\u0648\u062f \u062e\u0627\u0635 \u0645\u0646 VEX \u064a\u0639\u0637\u064a\u0643 \u0628\u0648\u0646\u0635 \u0625\u0636\u0627\u0641\u064a \u0639\u0646\u062f \u0627\u0644\u062a\u0633\u062c\u064a\u0644 (\u0645\u062b\u0627\u0644 1XBET: <code>VEX</code>). \u0627\u0633\u062a\u062e\u062f\u0645\u0647 \u0641\u064a \u062d\u0642\u0644 \u0627\u0644\u0628\u0631\u0648\u0645\u0648 \u0639\u0646\u062f \u0627\u0644\u062a\u0633\u062c\u064a\u0644.",
    faq_q3: "\u0647\u0644 VEX \u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f\u061f",
    faq_a3: "\u0646\u0639\u0645 \u2014 VEX \u0634\u0631\u064a\u0643 \u0645\u0628\u0627\u0634\u0631 \u0645\u0639 1xPartners \u0648 MelPartners \u06486 \u0634\u0628\u0643\u0627\u062a \u0623\u062e\u0631\u0649. \u0643\u0644 \u062a\u0633\u062c\u064a\u0644 \u0639\u0628\u0631 <code>vex.deals/go/*</code> \u0645\u062d\u0633\u0648\u0628 \u0644\u0643.",
    faq_q4: "\u0643\u064a\u0641 \u0623\u0636\u0645\u0646 \u0627\u0644\u0633\u062d\u0628\u061f",
    faq_a4: "\u0645\u062d\u0641\u0638\u0629 VEX \u0645\u0646\u0641\u0635\u0644\u0629 \u2014 \u062a\u0648\u062f\u0639 \u0639\u0628\u0631 \u0641\u0648\u062f\u0627\u0641\u0648\u0646 \u0643\u0627\u0634/\u0633\u062a\u0633\u064a \u0628\u064a/\u0628\u0646\u0643\u064a\u060c \u062a\u0644\u0639\u0628\u060c \u062a\u0633\u062d\u0628 \u0628\u0646\u0641\u0633 \u0627\u0644\u0648\u0633\u064a\u0644\u0629 \u0628\u0625\u0634\u0631\u0627\u0641 24/7. \u0627\u0644\u062a\u0639\u0648\u064a\u0636 \u0639\u0628\u0631 SVRP \u064a\u0636\u0645\u0646 100%.",
    nav_companies: "\u0627\u0644\u0634\u0631\u0643\u0627\u062a",
    nav_games: "\u0623\u0644\u0639\u0627\u0628\u064a",
    nav_login: "\u062f\u062e\u0648\u0644",
    nav_bot: "@vex_wallet_bot",
    mobile_menu_title: "\u0627\u0644\u0642\u0627\u0626\u0645\u0629",
    mobile_lang_label: "\u0627\u0644\u0644\u063a\u0629",
    copy_code_btn: "\u0646\u0633\u062e \u0627\u0644\u0643\u0648\u062f",
    footer_copyright: "\u00a9 2026 VEX Games \u2014 \u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f \u2022 8 \u0634\u0631\u0643\u0627\u062a \u0645\u0631\u062e\u0635\u0629 \u2022 17 \u0644\u063a\u0629 \u2022 Provably Fair",
    footer_responsible: "18+ \u2014 \u0627\u0644\u0639\u0628 \u0628\u0645\u0633\u0624\u0648\u0644\u064a\u0629"
  },
  en: {
    hero_badge: "Verified Partner \u2014 Cura\u00e7ao 8048/JAZ License",
    hero_title: "Your Global Guide <span>to the Best Licensed</span> Betting Companies",
    hero_subtitle: "Expert reviews, real licenses, exclusive promo codes and direct registration links \u2014 VEX is a verified partner with 1xBet, Melbet and 6 major companies. Choose the best, register in seconds, play with confidence.",
    cta_companies: "Browse Companies",
    cta_games: "My Web Games",
    cta_bot: "@vex_wallet_bot",
    trust_licensed: "8 Licensed Companies",
    trust_langs: "17 Languages",
    trust_fair: "Provably Fair",
    trust_instant: "Instant Deposit",
    companies_title: "Best Licensed Companies \u2014 Full Review",
    companies_sub: "We review each company like our own product \u2014 license, headquarters, year founded, pros & cons, promo code and direct registration link via VEX",
    comp_license: "License",
    comp_headquarters: "Headquarters",
    comp_founded: "Founded",
    comp_promo: "Promo Code",
    comp_cta_register: "Register at",
    comp_cta_details: "Details",
    badge_trusted: "Trusted",
    download_app: "Download App",
    features_title: "Features",
    why_vex_title: "Why VEX?",
    vex_title: "VEX Games \u2014 Your Verified Partner",
    vex_subtitle: "We are not just a directory \u2014 we are a licensed betting and gaming company, a verified partner of all the companies above",
    vex_badge: "Verified Partner",
    vex_license: "License",
    vex_services: "Services",
    vex_support: "Support",
    vex_security: "Security",
    vex_start: "Start with VEX",
    vex_how: "How it Works",
    how_title: "How to Start in 3 Steps",
    how_subtitle: "Choose a company, register via VEX, deposit and play \u2014 every step optimized",
    step1_title: "Choose a Company",
    step1_desc: "Compare licenses and ratings above",
    step2_title: "Register via VEX",
    step2_desc: "Click <b>Register</b> \u2192 your referral link opens",
    step3_title: "Deposit and Play",
    step3_desc: "VEX Wallet + 100% Compensation + Provably Fair",
    faq_title: "FAQ \u2014 Global Betting Guide",
    faq_q1: "Are the companies licensed?",
    faq_a1: "Yes \u2014 all displayed companies hold a Cura\u00e7ao 8048/JAZ license or equivalent, headquartered in Cyprus/Malta. VEX only lists licensed operators.",
    faq_q2: "What is a promo code?",
    faq_a2: "A special VEX code that gives you an extra bonus upon registration (e.g. 1XBET: <code>VEX</code>). Use it in the promo field when registering.",
    faq_q3: "Is VEX a verified partner?",
    faq_a3: "Yes \u2014 VEX is a direct partner with 1xPartners, MelPartners and 6 other networks. Every registration via <code>vex.deals/go/*</code> counts for you.",
    faq_q4: "How do I guarantee withdrawals?",
    faq_a4: "The VEX wallet is separate \u2014 deposit via Vodafone Cash/STC Pay/Bank, play, withdraw via the same method with 24/7 supervision. SVRP compensation guarantees 100%.",
    nav_companies: "Companies",
    nav_games: "My Games",
    nav_login: "Login",
    nav_bot: "@vex_wallet_bot",
    mobile_menu_title: "Menu",
    mobile_lang_label: "Language",
    copy_code_btn: "Copy Code",
    footer_copyright: "\u00a9 2026 VEX Games \u2014 Verified Partner \u2022 8 Licensed Companies \u2022 17 Languages \u2022 Provably Fair",
    footer_responsible: "18+ \u2014 Play Responsibly"
  },
  fr: {
    hero_badge: "Partenaire V\u00e9rifi\u00e9 \u2014 Licence Cura\u00e7ao 8048/JAZ",
    hero_title: "Votre Guide Mondial <span>des Meilleures Plates-formes</span> de Paris Sous Licence",
    hero_subtitle: "Avis d'experts, licences r\u00e9elles, codes promo exclusifs et liens d'inscription directe \u2014 VEX est partenaire v\u00e9rifi\u00e9 avec 1xBet, Melbet et 6 grandes entreprises. Choisissez la meilleure, inscrivez-vous en quelques secondes, jouez en confiance.",
    cta_companies: "Voir les Entreprises",
    cta_games: "Mes Jeux Web",
    cta_bot: "@vex_wallet_bot",
    trust_licensed: "8 Entreprises Licenci\u00e9es",
    trust_langs: "17 Langues",
    trust_fair: "Provably Fair",
    trust_instant: "D\u00e9p\u00f4t Instantan\u00e9",
    companies_title: "Meilleurs Op\u00e9rateurs Sous Licence \u2014 Avis Complets",
    companies_sub: "Nous \u00e9valuons chaque entreprise comme notre propre produit \u2014 licence, si\u00e8ge, ann\u00e9e de cr\u00e9ation, avantages/inconv\u00e9nients, code promo et lien d'inscription direct via VEX",
    comp_license: "Licence",
    comp_headquarters: "Si\u00e8ge",
    comp_founded: "Fond\u00e9e",
    comp_promo: "Code Promo",
    comp_cta_register: "S'inscrire sur",
    comp_cta_details: "D\u00e9tails",
    badge_trusted: "V\u00e9rifi\u00e9",
    download_app: "T\u00e9l\u00e9charger l'App",
    features_title: "Fonctionnalit\u00e9s",
    why_vex_title: "Pourquoi VEX\u061f",
    vex_title: "VEX Games \u2014 Votre Partenaire V\u00e9rifi\u00e9",
    vex_subtitle: "Nous ne sommes pas qu'un annuaire \u2014 nous sommes une entreprise de paris et de jeux sous licence, partenaire v\u00e9rifi\u00e9 de toutes les entreprises ci-dessus",
    vex_badge: "Partenaire V\u00e9rifi\u00e9",
    vex_license: "Licence",
    vex_services: "Services",
    vex_support: "Support",
    vex_security: "S\u00e9curit\u00e9",
    vex_start: "Commencer avec VEX",
    vex_how: "Comment \u00e7a Marche",
    how_title: "Comment Commencer en 3 \u00c9tapes",
    how_subtitle: "Choisissez une entreprise, inscrivez-vous via VEX, d\u00e9posez et jouez \u2014 chaque \u00e9tape optimis\u00e9e",
    step1_title: "Choisissez une Entreprise",
    step1_desc: "Comparez les licences et notes ci-dessus",
    step2_title: "Inscrivez-vous via VEX",
    step2_desc: "Cliquez sur <b>S'inscrire</b> \u2192 votre lien de parrainage s'ouvre",
    step3_title: "D\u00e9posez et Jouez",
    step3_desc: "Portefeuille VEX + Compensation 100% + Provably Fair",
    faq_title: "FAQ \u2014 Guide de Paris Mondial",
    faq_q1: "Les entreprises sont-elles licenci\u00e9es\u061f",
    faq_a1: "Oui \u2014 toutes les entreprises affich\u00e9es d\u00e9tiennent une licence Cura\u00e7ao 8048/JAZ ou \u00e9quivalente, bas\u00e9es \u00e0 Chypre/Malte. VEX ne liste que des op\u00e9rateurs licenci\u00e9s.",
    faq_q2: "Qu'est-ce qu'un code promo\u061f",
    faq_a2: "Un code sp\u00e9cial VEX qui vous donne un bonus suppl\u00e9mentaire \u00e0 l'inscription (ex: 1XBET: <code>VEX</code>). Entrez-le dans le champ promo lors de l'inscription.",
    faq_q3: "VEX est-il un partenaire v\u00e9rifi\u00e9\u061f",
    faq_a3: "Oui \u2014 VEX est un partenaire direct de 1xPartners, MelPartners et 6 autres r\u00e9seaux. Chaque inscription via <code>vex.deals/go/*</code> compte pour vous.",
    faq_q4: "Comment garantir les retraits\u061f",
    faq_a4: "Le portefeuille VEX est s\u00e9par\u00e9 \u2014 d\u00e9posez via Vodafone Cash/STC Pay/Banque, jouez, retirez via la m\u00eame m\u00e9thode avec supervision 24/7. La compensation SVRP garantit 100%.",
    nav_companies: "Entreprises",
    nav_games: "Mes Jeux",
    nav_login: "Connexion",
    nav_bot: "@vex_wallet_bot",
    mobile_menu_title: "Menu",
    mobile_lang_label: "Langue",
    copy_code_btn: "Copier le Code",
    footer_copyright: "\u00a9 2026 VEX Games \u2014 Partenaire V\u00e9rifi\u00e9 \u2022 8 Entreprises Licenci\u00e9es \u2022 17 Langues \u2022 Provably Fair",
    footer_responsible: "18+ \u2014 Jouez de Mani\u00e8re Responsable"
  },
  es: {
    hero_badge: "Socio Verificado \u2014 Licencia Curazao 8048/JAZ",
    hero_title: "Tu Gu\u00eda Global <span>de las Mejores Plataformas</span> de Apuestas con Licencia",
    hero_subtitle: "Rese\u00f1as de expertos, licencias reales, c\u00f3digos promo exclusivos y enlaces de registro directo \u2014 VEX es socio verificado con 1xBet, Melbet y 6 marcas importantes. Elige la mejor, reg\u00edstrate en segundos, juega con confianza.",
    cta_companies: "Explorar Empresas",
    cta_games: "Mis Juegos Web",
    cta_bot: "@vex_wallet_bot",
    trust_licensed: "8 Empresas Licenciadas",
    trust_langs: "17 Idiomas",
    trust_fair: "Provably Fair",
    trust_instant: "Dep\u00f3sito Instant\u00e1neo",
    companies_title: "Mejores Operadores con Licencia \u2014 Rese\u00f1as Detalladas",
    companies_sub: "Revisamos cada empresa como si fuera nuestro propio producto \u2014 licencia, sede, a\u00f1o de fundaci\u00f3n, pros y contras, c\u00f3digo promo y enlace de registro directo con VEX",
    comp_license: "Licencia",
    comp_headquarters: "Sede",
    comp_founded: "Fundaci\u00f3n",
    comp_promo: "C\u00f3digo Promo",
    comp_cta_register: "Registrarse en",
    comp_cta_details: "Detalles",
    badge_trusted: "Verificado",
    download_app: "Descargar App",
    features_title: "Caracter\u00edsticas",
    why_vex_title: "\u00bfPor qu\u00e9 VEX\u061f",
    vex_title: "VEX Games \u2014 Tu Socio Verificado",
    vex_subtitle: "No somos solo un directorio \u2014 somos una empresa de apuestas y juegos con licencia, socio verificado de todas las empresas arriba",
    vex_badge: "Socio Verificado",
    vex_license: "Licencia",
    vex_services: "Servicios",
    vex_support: "Soporte",
    vex_security: "Seguridad",
    vex_start: "Empezar con VEX",
    vex_how: "C\u00f3mo Funciona",
    how_title: "C\u00f3mo Empezar en 3 Pasos",
    how_subtitle: "Elige una empresa, reg\u00edstrate v\u00eda VEX, deposita y juega \u2014 cada paso optimizado",
    step1_title: "Elige una Empresa",
    step1_desc: "Compara licencias y calificaciones arriba",
    step2_title: "Reg\u00edstrate v\u00eda VEX",
    step2_desc: "Haz clic en <b>Registrarse</b> \u2192 se abre tu enlace de referido",
    step3_title: "Deposita y Juega",
    step3_desc: "Billetera VEX + Compensaci\u00f3n 100% + Provably Fair",
    faq_title: "Preguntas Frecuentes \u2014 Gu\u00eda Global de Apuestas",
    faq_q1: "\u00bfLas empresas tienen licencia\u061f",
    faq_a1: "S\u00ed \u2014 todas las empresas mostradas tienen licencia Curazao 8048/JAZ o equivalente, con sede en Chipre/Malta. VEX solo lista operadores licenciados.",
    faq_q2: "\u00bfQu\u00e9 es un c\u00f3digo promo\u061f",
    faq_a2: "Un c\u00f3digo especial de VEX que te da un bono extra al registrarte (ej: 1XBET: <code>VEX</code>). \u00daalo en el campo promo al registrarte.",
    faq_q3: "\u00bfVEX es socio verificado\u061f",
    faq_a3: "S\u00ed \u2014 VEX es socio directo con 1xPartners, MelPartners y 6 redes m\u00e1s. Cada registro v\u00eda <code>vex.deals/go/*</code> cuenta para ti.",
    faq_q4: "\u00bfC\u00f3mo aseguro los retiros\u061f",
    faq_a4: "La billetera VEX es separada \u2014 depositas v\u00eda Vodafone Cash/STC Pay/Banco, juegas, retiras mismo m\u00e9todo con supervisi\u00f3n 24/7. La compensaci\u00f3n SVRP garantiza 100%.",
    nav_companies: "Empresas",
    nav_games: "Mis Juegos",
    nav_login: "Acceso",
    nav_bot: "@vex_wallet_bot",
    mobile_menu_title: "Men\u00fa",
    mobile_lang_label: "Idioma",
    copy_code_btn: "Copiar C\u00f3digo",
    footer_copyright: "\u00a9 2026 VEX Games \u2014 Socio Verificado \u2022 8 Empresas Licenciadas \u2022 17 Idiomas \u2022 Provably Fair",
    footer_responsible: "18+ \u2014 Juega Responsablemente"
  }
};'''

content = content[:start_idx] + new_i18n + content[end_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Count keys per language
for lang in ['ar', 'en', 'fr', 'es']:
    block_start = content.find(lang + ': {')
    if block_start != -1:
        block = content[block_start:block_start+5000]
        keys = block.count(':')
        print(f"{lang}: ~{keys} keys")

i18n_count = content.count('data-i18n=')
print(f"\ndata-i18n attributes: {i18n_count}")
print(f"File lines: {content.count(chr(10))+1}")

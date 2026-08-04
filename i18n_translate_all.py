#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
i18n Multi-Language Translator
يترجم ملفات اللغات الـ 15 من الإنجليزية باستخدام قاموس شامل
"""

import json
import re
import os
import copy

I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
SOURCE_FILE = os.path.join(I18N_DIR, 'en.json')

LANGUAGES = ['de', 'es', 'fa', 'fr', 'hi', 'id', 'it', 'ja', 'ko', 'pt', 'ru', 'th', 'tr', 'ur', 'zh']

# Master dictionary: English phrase → {lang_code: translation}
# Covers common UI terms used throughout the bot
DICT = {
    # Core actions
    'Deposit': {'de':'Einzahlung','es':'Depósito','fa':'واریز','fr':'Dépôt','hi':'जमा','id':'Setoran','it':'Deposito','ja':'入金','ko':'입금','pt':'Depósito','ru':'Депозит','th':'ฝาก','tr':'Para Yatırma','ur':'جمع','zh':'存款'},
    'Withdrawal': {'de':'Auszahlung','es':'Retiro','fa':'برداشت','fr':'Retrait','hi':'निकासी','id':'Penarikan','it':'Prelievo','ja':'出金','ko':'출금','pt':'Saque','ru':'Вывод','th':'ถอน','tr':'Para Çekme','ur':'نکلوانا','zh':'提款'},
    'Withdraw': {'de':'Auszahlung','es':'Retiro','fa':'برداشت','fr':'Retrait','hi':'निकासी','id':'Penarikan','it':'Prelievo','ja':'出金','ko':'출금','pt':'Saque','ru':'Вывод','th':'ถอน','tr':'Para Çekme','ur':'نکلوانا','zh':'提款'},
    'Request': {'de':'Anfrage','es':'Solicitud','fa':'درخواست','fr':'Demande','hi':'अनुरोध','id':'Permintaan','it':'Richiesta','ja':'リクエスト','ko':'요청','pt':'Solicitação','ru':'Запрос','th':'คำขอ','tr':'Talep','ur':'درخواست','zh':'请求'},
    'Balance': {'de':'Guthaben','es':'Saldo','fa':'موجودی','fr':'Solde','hi':'शेष','id':'Saldo','it':'Saldo','ja':'残高','ko':'잔액','pt':'Saldo','ru':'Баланс','th':'ยอดคงเหลือ','tr':'Bakiye','ur':'بیلنس','zh':'余额'},
    'Profile': {'de':'Profil','es':'Perfil','fa':'پروفایل','fr':'Profil','hi':'प्रोफ़ाइल','id':'Profil','it':'Profilo','ja':'プロフィール','ko':'프로필','pt':'Perfil','ru':'Профиль','th':'โปรไฟล์','tr':'Profil','ur':'پروفائل','zh':'个人资料'},
    'Settings': {'de':'Einstellungen','es':'Configuración','fa':'تنظیمات','fr':'Paramètres','hi':'सेटिंग्स','id':'Pengaturan','it':'Impostazioni','ja':'設定','ko':'설정','pt':'Configurações','ru':'Настройки','th':'การตั้งค่า','tr':'Ayarlar','ur':'ترتیبات','zh':'设置'},
    'Support': {'de':'Support','es':'Soporte','fa':'پشتیبانی','fr':'Support','hi':'सहायता','id':'Dukungan','it':'Supporto','ja':'サポート','ko':'지원','pt':'Suporte','ru':'Поддержка','th':'การสนับสนุน','tr':'Destek','ur':'سپورٹ','zh':'支持'},
    'Complaint': {'de':'Beschwerde','es':'Queja','fa':'شکایت','fr':'Plainte','hi':'शिकायत','id':'Keluhan','it':'Reclamo','ja':'苦情','ko':'불만','pt':'Reclamação','ru':'Жалоба','th':'ร้องเรียน','tr':'Şikayet','ur':'شکایت','zh':'投诉'},
    'Cancel': {'de':'Abbrechen','es':'Cancelar','fa':'لغو','fr':'Annuler','hi':'रद्द करें','id':'Batal','it':'Annulla','ja':'キャンセル','ko':'취소','pt':'Cancelar','ru':'Отмена','th':'ยกเลิก','tr':'İptal','ur':'منسوخ','zh':'取消'},
    'Confirm': {'de':'Bestätigen','es':'Confirmar','fa':'تأیید','fr':'Confirmer','hi':'पुष्टि करें','id':'Konfirmasi','it':'Conferma','ja':'確認','ko':'확인','pt':'Confirmar','ru':'Подтвердить','th':'ยืนยัน','tr':'Onayla','ur':'تصدیق','zh':'确认'},
    'Approve': {'de':'Genehmigen','es':'Aprobar','fa':'تأیید','fr':'Approuver','hi':'स्वीकृत करें','id':'Setujui','it':'Approva','ja':'承認','ko':'승인','pt':'Aprovar','ru':'Одобрить','th':'อนุมัติ','tr':'Onayla','ur':'منظور','zh':'批准'},
    'Reject': {'de':'Ablehnen','es':'Rechazar','fa':'رد','fr':'Rejeter','hi':'अस्वीकार करें','id':'Tolak','it':'Rifiuta','ja':'拒否','ko':'거절','pt':'Rejeitar','ru':'Отклонить','th':'ปฏิเสธ','tr':'Reddet','ur':'مسترد','zh':'拒绝'},
    'Pending': {'de':'Ausstehend','es':'Pendiente','fa':'در انتظار','fr':'En attente','hi':'लंबित','id':'Menunggu','it':'In attesa','ja':'保留中','ko':'대기 중','pt':'Pendente','ru':'Ожидание','th':'รอดำเนินการ','tr':'Beklemede','ur':'زیر التواء','zh':'待处理'},
    'Approved': {'de':'Genehmigt','es':'Aprobado','fa':'تأیید شد','fr':'Approuvé','hi':'स्वीकृत','id':'Disetujui','it':'Approvato','ja':'承認済み','ko':'승인됨','pt':'Aprovado','ru':'Одобрено','th':'อนุมัติแล้ว','tr':'Onaylandı','ur':'منظور شدہ','zh':'已批准'},
    'Rejected': {'de':'Abgelehnt','es':'Rechazado','fa':'رد شد','fr':'Rejeté','hi':'अस्वीकृत','id':'Ditolak','it':'Rifiutato','ja':'拒否されました','ko':'거절됨','pt':'Rejeitado','ru':'Отклонено','th':'ถูกปฏิเสธ','tr':'Reddedildi','ur':'مسترد شدہ','zh':'已拒绝'},
    'Success': {'de':'Erfolg','es':'Éxito','fa':'موفقیت','fr':'Succès','hi':'सफलता','id':'Berhasil','it':'Successo','ja':'成功','ko':'성공','pt':'Sucesso','ru':'Успех','th':'สำเร็จ','tr':'Başarılı','ur':'کامیابی','zh':'成功'},
    'Error': {'de':'Fehler','es':'Error','fa':'خطا','fr':'Erreur','hi':'त्रुटि','id':'Kesalahan','it':'Errore','ja':'エラー','ko':'오류','pt':'Erro','ru':'Ошибка','th':'ข้อผิดพลาด','tr':'Hata','ur':'خرابی','zh':'错误'},
    'Loading': {'de':'Laden','es':'Cargando','fa':'بارگذاری','fr':'Chargement','hi':'लोड हो रहा है','id':'Memuat','it':'Caricamento','ja':'読み込み中','ko':'로딩 중','pt':'Carregando','ru':'Загрузка','th':'กำลังโหลด','tr':'Yükleniyor','ur':'لوڈ ہو رہا ہے','zh':'加载中'},
    'Save': {'de':'Speichern','es':'Guardar','fa':'ذخیره','fr':'Enregistrer','hi':'सहेजें','id':'Simpan','it':'Salva','ja':'保存','ko':'저장','pt':'Salvar','ru':'Сохранить','th':'บันทึก','tr':'Kaydet','ur':'محفوظ','zh':'保存'},
    'Delete': {'de':'Löschen','es':'Eliminar','fa':'حذف','fr':'Supprimer','hi':'हटाएं','id':'Hapus','it':'Elimina','ja':'削除','ko':'삭제','pt':'Excluir','ru':'Удалить','th':'ลบ','tr':'Sil','ur':'حذف','zh':'删除'},
    'Edit': {'de':'Bearbeiten','es':'Editar','fa':'ویرایش','fr':'Modifier','hi':'संपादित करें','id':'Edit','it':'Modifica','ja':'編集','ko':'편집','pt':'Editar','ru':'Изменить','th':'แก้ไข','tr':'Düzenle','ur':'ترمیم','zh':'编辑'},
    'Search': {'de':'Suchen','es':'Buscar','fa':'جستجو','fr':'Rechercher','hi':'खोजें','id':'Cari','it':'Cerca','ja':'検索','ko':'검색','pt':'Pesquisar','ru':'Поиск','th':'ค้นหา','tr':'Ara','ur':'تلاش','zh':'搜索'},
    'Close': {'de':'Schließen','es':'Cerrar','fa':'بستن','fr':'Fermer','hi':'बंद करें','id':'Tutup','it':'Chiudi','ja':'閉じる','ko':'닫기','pt':'Fechar','ru':'Закрыть','th':'ปิด','tr':'Kapat','ur':'بند','zh':'关闭'},
    'Back': {'de':'Zurück','es':'Atrás','fa':'بازگشت','fr':'Retour','hi':'वापस','id':'Kembali','it':'Indietro','ja':'戻る','ko':'뒤로','pt':'Voltar','ru':'Назад','th':'ย้อนกลับ','tr':'Geri','ur':'واپس','zh':'返回'},
    'Next': {'de':'Weiter','es':'Siguiente','fa':'بعدی','fr':'Suivant','hi':'अगला','id':'Berikutnya','it':'Avanti','ja':'次へ','ko':'다음','pt':'Próximo','ru':'Далее','th':'ถัดไป','tr':'İleri','ur':'اگلا','zh':'下一个'},
    'Yes': {'de':'Ja','es':'Sí','fa':'بله','fr':'Oui','hi':'हां','id':'Ya','it':'Sì','ja':'はい','ko':'예','pt':'Sim','ru':'Да','th':'ใช่','tr':'Evet','ur':'ہاں','zh':'是'},
    'No': {'de':'Nein','es':'No','fa':'خیر','fr':'Non','hi':'नहीं','id':'Tidak','it':'No','ja':'いいえ','ko':'아니오','pt':'Não','ru':'Нет','th':'ไม่','tr':'Hayır','ur':'نہیں','zh':'否'},
    'Amount': {'de':'Betrag','es':'Monto','fa':'مبلغ','fr':'Montant','hi':'राशि','id':'Jumlah','it':'Importo','ja':'金額','ko':'금액','pt':'Valor','ru':'Сумма','th':'จำนวน','tr':'Tutar','ur':'رقم','zh':'金额'},
    'Currency': {'de':'Währung','es':'Moneda','fa':'ارز','fr':'Devise','hi':'मुद्रा','id':'Mata Uang','it':'Valuta','ja':'通貨','ko':'통화','pt':'Moeda','ru':'Валюта','th':'สกุลเงิน','tr':'Para Birimi','ur':'کرنسی','zh':'货币'},
    'Language': {'de':'Sprache','es':'Idioma','fa':'زبان','fr':'Langue','hi':'भाषा','id':'Bahasa','it':'Lingua','ja':'言語','ko':'언어','pt':'Idioma','ru':'Язык','th':'ภาษา','tr':'Dil','ur':'زبان','zh':'语言'},
    'Phone': {'de':'Telefon','es':'Teléfono','fa':'تلفن','fr':'Téléphone','hi':'फ़ोन','id':'Telepon','it':'Telefono','ja':'電話','ko':'전화','pt':'Telefone','ru':'Телефон','th':'โทรศัพท์','tr':'Telefon','ur':'فون','zh':'电话'},
    'Email': {'de':'E-Mail','es':'Correo','fa':'ایمیل','fr':'E-mail','hi':'ईमेल','id':'Email','it':'Email','ja':'メール','ko':'이메일','pt':'E-mail','ru':'Эл. почта','th':'อีเมล','tr':'E-posta','ur':'ای میل','zh':'邮箱'},
    'Name': {'de':'Name','es':'Nombre','fa':'نام','fr':'Nom','hi':'नाम','id':'Nama','it':'Nome','ja':'名前','ko':'이름','pt':'Nome','ru':'Имя','th':'ชื่อ','tr':'İsim','ur':'نام','zh':'姓名'},
    'Date': {'de':'Datum','es':'Fecha','fa':'تاریخ','fr':'Date','hi':'तारीख','id':'Tanggal','it':'Data','ja':'日付','ko':'날짜','pt':'Data','ru':'Дата','th':'วันที่','tr':'Tarih','ur':'تاریخ','zh':'日期'},
    'Time': {'de':'Zeit','es':'Hora','fa':'زمان','fr':'Heure','hi':'समय','id':'Waktu','it':'Ora','ja':'時間','ko':'시간','pt':'Hora','ru':'Время','th':'เวลา','tr':'Saat','ur':'وقت','zh':'时间'},
    'Status': {'de':'Status','es':'Estado','fa':'وضعیت','fr':'Statut','hi':'स्थिति','id':'Status','it':'Stato','ja':'ステータス','ko':'상태','pt':'Status','ru':'Статус','th':'สถานะ','tr':'Durum','ur':'حالت','zh':'状态'},
    'Active': {'de':'Aktiv','es':'Activo','fa':'فعال','fr':'Actif','hi':'सक्रिय','id':'Aktif','it':'Attivo','ja':'アクティブ','ko':'활성','pt':'Ativo','ru':'Активен','th':'ใช้งาน','tr':'Aktif','ur':'فعال','zh':'活跃'},
    'Inactive': {'de':'Inaktiv','es':'Inactivo','fa':'غیرفعال','fr':'Inactif','hi':'निष्क्रिय','id':'Tidak Aktif','it':'Inattivo','ja':'非アクティブ','ko':'비활성','pt':'Inativo','ru':'Неактивен','th':'ไม่ใช้งาน','tr':'Pasif','ur':'غیر فعال','zh':'非活跃'},
    'Welcome': {'de':'Willkommen','es':'Bienvenido','fa':'خوش آمدید','fr':'Bienvenue','hi':'स्वागत है','id':'Selamat Datang','it':'Benvenuto','ja':'ようこそ','ko':'환영합니다','pt':'Bem-vindo','ru':'Добро пожаловать','th':'ยินดีต้อนรับ','tr':'Hoş geldiniz','ur':'خوش آمدید','zh':'欢迎'},
    'Register': {'de':'Registrieren','es':'Registrar','fa':'ثبت‌نام','fr':'S\'inscrire','hi':'पंजीकरण करें','id':'Daftar','it':'Registrati','ja':'登録','ko':'등록','pt':'Registrar','ru':'Регистрация','th':'ลงทะเบียน','tr':'Kayıt Ol','ur':'رجسٹر','zh':'注册'},
    'Registration': {'de':'Registrierung','es':'Registro','fa':'ثبت‌نام','fr':'Inscription','hi':'पंजीकरण','id':'Pendaftaran','it':'Registrazione','ja':'登録','ko':'등록','pt':'Registro','ru':'Регистрация','th':'การลงทะเบียน','tr':'Kayıt','ur':'رجسٹریشن','zh':'注册'},
    'Account': {'de':'Konto','es':'Cuenta','fa':'حساب','fr':'Compte','hi':'खाता','id':'Akun','it':'Account','ja':'アカウント','ko':'계정','pt':'Conta','ru':'Аккаунт','th':'บัญชี','tr':'Hesap','ur':'اکاؤنٹ','zh':'账户'},
    'Admin': {'de':'Administrator','es':'Administrador','fa':'مدیر','fr':'Administrateur','hi':'व्यवस्थापक','id':'Admin','it':'Amministratore','ja':'管理者','ko':'관리자','pt':'Administrador','ru':'Админ','th':'ผู้ดูแล','tr':'Yönetici','ur':'ایڈمن','zh':'管理员'},
    'Panel': {'de':'Panel','es':'Panel','fa':'پنل','fr':'Panneau','hi':'पैनल','id':'Panel','it':'Pannello','ja':'パネル','ko':'패널','pt':'Painel','ru':'Панель','th':'แผงควบคุม','tr':'Panel','ur':'پینل','zh':'面板'},
    'Menu': {'de':'Menü','es':'Menú','fa':'منو','fr':'Menu','hi':'मेनू','id':'Menu','it':'Menu','ja':'メニュー','ko':'메뉴','pt':'Menu','ru':'Меню','th':'เมนู','tr':'Menü','ur':'مینو','zh':'菜单'},
    'Game': {'de':'Spiel','es':'Juego','fa':'بازی','fr':'Jeu','hi':'खेल','id':'Permainan','it':'Gioco','ja':'ゲーム','ko':'게임','pt':'Jogo','ru':'Игра','th':'เกม','tr':'Oyun','ur':'گیم','zh':'游戏'},
    'Games': {'de':'Spiele','es':'Juegos','fa':'بازی‌ها','fr':'Jeux','hi':'खेल','id':'Permainan','it':'Giochi','ja':'ゲーム','ko':'게임','pt':'Jogos','ru':'Игры','th':'เกม','tr':'Oyunlar','ur':'گیمز','zh':'游戏'},
    'Play': {'de':'Spielen','es':'Jugar','fa':'بازی','fr':'Jouer','hi':'खेलें','id':'Main','it':'Gioca','ja':'プレイ','ko':'플레이','pt':'Jogar','ru':'Играть','th':'เล่น','tr':'Oyna','ur':'کھیلیں','zh':'玩'},
    'Bet': {'de':'Einsatz','es':'Apuesta','fa':'شرط','fr':'Pari','hi':'दांव','id':'Taruhan','it':'Puntata','ja':'ベット','ko':'베팅','pt':'Aposta','ru':'Ставка','th':'เดิมพัน','tr':'Bahis','ur':'داؤ','zh':'下注'},
    'Win': {'de':'Gewinn','es':'Ganar','fa':'برد','fr':'Gagner','hi':'जीत','id':'Menang','it':'Vincita','ja':'勝利','ko':'승리','pt':'Ganhar','ru':'Выигрыш','th':'ชนะ','tr':'Kazanç','ur':'جیت','zh':'赢'},
    'Lose': {'de':'Verlust','es':'Perder','fa':'باخت','fr':'Perdre','hi':'हार','id':'Kalah','it':'Perdita','ja':'敗北','ko':'패배','pt':'Perder','ru':'Проигрыш','th':'แพ้','tr':'Kayıp','ur':'ہار','zh':'输'},
    'Payout': {'de':'Auszahlung','es':'Pago','fa':'پرداخت','fr':'Paiement','hi':'भुगतान','id':'Pembayaran','it':'Pagamento','ja':'配当','ko':'배당','pt':'Pagamento','ru':'Выплата','th':'การจ่าย','tr':'Ödeme','ur':'ادائیگی','zh':'赔付'},
    'Multiplier': {'de':'Multiplikator','es':'Multiplicador','fa':'ضریب','fr':'Multiplicateur','hi':'गुणक','id':'Pengali','it':'Moltiplicatore','ja':'倍率','ko':'배수','pt':'Multiplicador','ru':'Множитель','th':'ตัวคูณ','tr':'Çarpan','ur':'ضرب','zh':'倍数'},
    'Wallet': {'de':'Wallet','es':'Billetera','fa':'کیف پول','fr':'Portefeuille','hi':'वॉलेट','id':'Dompet','it':'Portafoglio','ja':'ウォレット','ko':'지갑','pt':'Carteira','ru':'Кошелек','th':'กระเป๋าเงิน','tr':'Cüzdan','ur':'والٹ','zh':'钱包'},
    'Company': {'de':'Unternehmen','es':'Empresa','fa':'شرکت','fr':'Entreprise','hi':'कंपनी','id':'Perusahaan','it':'Azienda','ja':'会社','ko':'회사','pt':'Empresa','ru':'Компания','th':'บริษัท','tr':'Şirket','ur':'کمپنی','zh':'公司'},
    'Companies': {'de':'Unternehmen','es':'Empresas','fa':'شرکت‌ها','fr':'Entreprises','hi':'कंपनियां','id':'Perusahaan','it':'Aziende','ja':'会社','ko':'회사','pt':'Empresas','ru':'Компании','th':'บริษัท','tr':'Şirketler','ur':'کمپنیاں','zh':'公司'},
    'Payment': {'de':'Zahlung','es':'Pago','fa':'پرداخت','fr':'Paiement','hi':'भुगतान','id':'Pembayaran','it':'Pagamento','ja':'支払い','ko':'결제','pt':'Pagamento','ru':'Платеж','th':'การชำระเงิน','tr':'Ödeme','ur':'ادائیگی','zh':'支付'},
    'Method': {'de':'Methode','es':'Método','fa':'روش','fr':'Méthode','hi':'विधि','id':'Metode','it':'Metodo','ja':'方法','ko':'방법','pt':'Método','ru':'Метод','th':'วิธี','tr':'Yöntem','ur':'طریقہ','zh':'方式'},
    'Transaction': {'de':'Transaktion','es':'Transacción','fa':'تراکنش','fr':'Transaction','hi':'लेनदेन','id':'Transaksi','it':'Transazione','ja':'取引','ko':'거래','pt':'Transação','ru':'Транзакция','th':'ธุรกรรม','tr':'İşlem','ur':'لین دین','zh':'交易'},
    'Transactions': {'de':'Transaktionen','es':'Transacciones','fa':'تراکنش‌ها','fr':'Transactions','hi':'लेनदेन','id':'Transaksi','it':'Transazioni','ja':'取引','ko':'거래','pt':'Transações','ru':'Транзакции','th':'ธุรกรรม','tr':'İşlemler','ur':'لین دین','zh':'交易'},
    'Users': {'de':'Benutzer','es':'Usuarios','fa':'کاربران','fr':'Utilisateurs','hi':'उपयोगकर्ता','id':'Pengguna','it':'Utenti','ja':'ユーザー','ko':'사용자','pt':'Usuários','ru':'Пользователи','th':'ผู้ใช้','tr':'Kullanıcılar','ur':'صارفین','zh':'用户'},
    'User': {'de':'Benutzer','es':'Usuario','fa':'کاربر','fr':'Utilisateur','hi':'उपयोगकर्ता','id':'Pengguna','it':'Utente','ja':'ユーザー','ko':'사용자','pt':'Usuário','ru':'Пользователь','th':'ผู้ใช้','tr':'Kullanıcı','ur':'صارف','zh':'用户'},
    'Total': {'de':'Gesamt','es':'Total','fa':'مجموع','fr':'Total','hi':'कुल','id':'Total','it':'Totale','ja':'合計','ko':'합계','pt':'Total','ru':'Всего','th':'รวม','tr':'Toplam','ur':'کل','zh':'总计'},
    'Available': {'de':'Verfügbar','es':'Disponible','fa':'موجود','fr':'Disponible','hi':'उपलब्ध','id':'Tersedia','it':'Disponibile','ja':'利用可能','ko':'사용 가능','pt':'Disponível','ru':'Доступно','th':'พร้อมใช้','tr':'Mevcut','ur':'دستیاب','zh':'可用'},
    'Frozen': {'de':'Eingefroren','es':'Congelado','fa':'مسدود','fr':'Gelé','hi':'जमे हुए','id':'Dibekukan','it':'Congelato','ja':'凍結','ko':'동결','pt':'Congelado','ru':'Заморожено','th':'ถูกแช่แข็ง','tr':'Donduruldu','ur':'منجمد','zh':'冻结'},
    'Bonus': {'de':'Bonus','es':'Bonificación','fa':'پاداش','fr':'Bonus','hi':'बोनस','id':'Bonus','it':'Bonus','ja':'ボーナス','ko':'보너스','pt':'Bônus','ru':'Бонус','th':'โบนัส','tr':'Bonus','ur':'بونس','zh':'奖金'},
    'Code': {'de':'Code','es':'Código','fa':'کد','fr':'Code','hi':'कोड','id':'Kode','it':'Codice','ja':'コード','ko':'코드','pt':'Código','ru':'Код','th':'รหัส','tr':'Kod','ur':'کوڈ','zh':'代码'},
    'Ticket': {'de':'Ticket','es':'Boleto','fa':'بلیت','fr':'Ticket','hi':'टिकट','id':'Tiket','it':'Biglietto','ja':'チケット','ko':'티켓','pt':'Bilhete','ru':'Билет','th':'ตั๋ว','tr':'Bilet','ur':'ٹکٹ','zh':'票'},
    'Prize': {'de':'Preis','es':'Premio','fa':'جایزه','fr':'Prix','hi':'पुरस्कार','id':'Hadiah','it':'Premio','ja':'賞品','ko':'상품','pt':'Prêmio','ru':'Приз','th':'รางวัล','tr':'Ödül','ur':'انعام','zh':'奖品'},
    'Winner': {'de':'Gewinner','es':'Ganador','fa':'برنده','fr':'Gagnant','hi':'विजेता','id':'Pemenang','it':'Vincitore','ja':'勝者','ko':'승자','pt':'Vencedor','ru':'Победитель','th':'ผู้ชนะ','tr':'Kazanan','ur':'فاتح','zh':'获胜者'},
    'Lottery': {'de':'Lotterie','es':'Lotería','fa':'لاتاری','fr':'Loterie','hi':'लॉटरी','id':'Lotere','it':'Lotteria','ja':'宝くじ','ko':'복권','pt':'Loteria','ru':'Лотерея','th':'ลอตเตอรี','tr':'Piyango','ur':'لاٹری','zh':'彩票'},
    'Channel': {'de':'Kanal','es':'Canal','fa':'کانال','fr':'Canal','hi':'चैनल','id':'Saluran','it':'Canale','ja':'チャンネル','ko':'채널','pt':'Canal','ru':'Канал','th':'ช่อง','tr':'Kanal','ur':'چینل','zh':'频道'},
    'Broadcast': {'de':'Rundfunk','es':'Difusión','fa':'پخش','fr':'Diffusion','hi':'प्रसारण','id':'Siaran','it':'Trasmissione','ja':'ブロードキャスト','ko':'방송','pt':'Transmissão','ru':'Рассылка','th':'กระจายเสียง','tr':'Yayın','ur':'نشریات','zh':'广播'},
    'Notification': {'de':'Benachrichtigung','es':'Notificación','fa':'اعلان','fr':'Notification','hi':'सूचना','id':'Notifikasi','it':'Notifica','ja':'通知','ko':'알림','pt':'Notificação','ru':'Уведомление','th':'การแจ้งเตือน','tr':'Bildirim','ur':'اطلاع','zh':'通知'},
    'Notifications': {'de':'Benachrichtigungen','es':'Notificaciones','fa':'اعلانات','fr':'Notifications','hi':'सूचनाएं','id':'Notifikasi','it':'Notifiche','ja':'通知','ko':'알림','pt':'Notificações','ru':'Уведомления','th':'การแจ้งเตือน','tr':'Bildirimler','ur':'اطلاعات','zh':'通知'},
    'Download': {'de':'Herunterladen','es':'Descargar','fa':'دانلود','fr':'Télécharger','hi':'डाउनलोड','id':'Unduh','it':'Scarica','ja':'ダウンロード','ko':'다운로드','pt':'Baixar','ru':'Скачать','th':'ดาวน์โหลด','tr':'İndir','ur':'ڈاؤن لوڈ','zh':'下载'},
    'Upload': {'de':'Hochladen','es':'Subir','fa':'آپلود','fr':'Télécharger','hi':'अपलोड','id':'Unggah','it':'Carica','ja':'アップロード','ko':'업로드','pt':'Enviar','ru':'Загрузить','th':'อัปโหลด','tr':'Yükle','ur':'اپلوڈ','zh':'上传'},
    'Copy': {'de':'Kopieren','es':'Copiar','fa':'کپی','fr':'Copier','hi':'कॉपी','id':'Salin','it':'Copia','ja':'コピー','ko':'복사','pt':'Copiar','ru':'Копировать','th':'คัดลอก','tr':'Kopyala','ur':'کاپی','zh':'复制'},
    'Select': {'de':'Auswählen','es':'Seleccionar','fa':'انتخاب','fr':'Sélectionner','hi':'चुनें','id':'Pilih','it':'Seleziona','ja':'選択','ko':'선택','pt':'Selecionar','ru':'Выбрать','th':'เลือก','tr':'Seç','ur':'منتخب','zh':'选择'},
    'Enter': {'de':'Eingeben','es':'Ingresar','fa':'وارد کنید','fr':'Entrer','hi':'दर्ज करें','id':'Masukkan','it':'Inserisci','ja':'入力','ko':'입력','pt':'Inserir','ru':'Введите','th':'ป้อน','tr':'Gir','ur':'داخل کریں','zh':'输入'},
    'Please': {'de':'Bitte','es':'Por favor','fa':'لطفاً','fr':'Veuillez','hi':'कृपया','id':'Silakan','it':'Per favore','ja':'してください','ko':'주세요','pt':'Por favor','ru':'Пожалуйста','th':'กรุณา','tr':'Lütfen','ur':'براہ کرم','zh':'请'},
    'Password': {'de':'Passwort','es':'Contraseña','fa':'رمز عبور','fr':'Mot de passe','hi':'पासवर्ड','id':'Kata Sandi','it':'Password','ja':'パスワード','ko':'비밀번호','pt':'Senha','ru':'Пароль','th':'รหัสผ่าน','tr':'Şifre','ur':'پاس ورڈ','zh':'密码'},
    'Login': {'de':'Anmelden','es':'Iniciar sesión','fa':'ورود','fr':'Connexion','hi':'लॉगिन','id':'Masuk','it':'Accedi','ja':'ログイン','ko':'로그인','pt':'Entrar','ru':'Вход','th':'เข้าสู่ระบบ','tr':'Giriş','ur':'لاگ ان','zh':'登录'},
    'Logout': {'de':'Abmelden','es':'Cerrar sesión','fa':'خروج','fr':'Déconnexion','hi':'लॉगआउट','id':'Keluar','it':'Esci','ja':'ログアウト','ko':'로그아웃','pt':'Sair','ru':'Выход','th':'ออกจากระบบ','tr':'Çıkış','ur':'لاگ آؤٹ','zh':'登出'},
    'Dashboard': {'de':'Übersicht','es':'Panel','fa':'داشبورد','fr':'Tableau de bord','hi':'डैशबोर्ड','id':'Dasbor','it':'Cruscotto','ja':'ダッシュボード','ko':'대시보드','pt':'Painel','ru':'Панель','th':'แดชบอร์ด','tr':'Panel','ur':'ڈیش بورڈ','zh':'仪表板'},
    'Statistics': {'de':'Statistiken','es':'Estadísticas','fa':'آمار','fr':'Statistiques','hi':'आंकड़े','id':'Statistik','it':'Statistiche','ja':'統計','ko':'통계','pt':'Estatísticas','ru':'Статистика','th':'สถิติ','tr':'İstatistikler','ur':'شماریات','zh':'统计'},
    'Report': {'de':'Bericht','es':'Informe','fa':'گزارش','fr':'Rapport','hi':'रिपोर्ट','id':'Laporan','it':'Report','ja':'レポート','ko':'보고서','pt':'Relatório','ru':'Отчет','th':'รายงาน','tr':'Rapor','ur':'رپورٹ','zh':'报告'},
    'Config': {'de':'Konfiguration','es':'Configuración','fa':'پیکربندی','fr':'Configuration','hi':'कॉन्फ़िग','id':'Konfigurasi','it':'Configurazione','ja':'設定','ko':'설정','pt':'Configuração','ru':'Конфиг','th':'การกำหนดค่า','tr':'Yapılandırma','ur':'ترتیب','zh':'配置'},
    'Risk': {'de':'Risiko','es':'Riesgo','fa':'ریسک','fr':'Risque','hi':'जोखिम','id':'Risiko','it':'Rischio','ja':'リスク','ko':'위험','pt':'Risco','ru':'Риск','th':'ความเสี่ยง','tr':'Risk','ur':'خطرہ','zh':'风险'},
    'Player': {'de':'Spieler','es':'Jugador','fa':'بازیکن','fr':'Joueur','hi':'खिलाड़ी','id':'Pemain','it':'Giocatore','ja':'プレイヤー','ko':'플레이어','pt':'Jogador','ru':'Игрок','th':'ผู้เล่น','tr':'Oyuncu','ur':'کھلاڑی','zh':'玩家'},
    'Session': {'de':'Sitzung','es':'Sesión','fa':'نشست','fr':'Session','hi':'सत्र','id':'Sesi','it':'Sessione','ja':'セッション','ko':'세션','pt':'Sessão','ru':'Сессия','th':'เซสชัน','tr':'Oturum','ur':'سیشن','zh':'会话'},
    'Deposit Request': {'de':'Einzahlungsanfrage','es':'Solicitud de depósito','fa':'درخواست واریز','fr':'Demande de dépôt','hi':'जमा अनुरोध','id':'Permintaan Setoran','it':'Richiesta di deposito','ja':'入金リクエスト','ko':'입금 요청','pt':'Solicitação de depósito','ru':'Запрос на депозит','th':'คำขอฝาก','tr':'Para Yatırma Talebi','ur':'جمع کی درخواست','zh':'存款请求'},
    'Withdrawal Request': {'de':'Auszahlungsanfrage','es':'Solicitud de retiro','fa':'درخواست برداشت','fr':'Demande de retrait','hi':'निकासी अनुरोध','id':'Permintaan Penarikan','it':'Richiesta di prelievo','ja':'出金リクエスト','ko':'출금 요청','pt':'Solicitação de saque','ru':'Запрос на вывод','th':'คำขอถอน','tr':'Para Çekme Talebi','ur':'نکلوانے کی درخواست','zh':'提款请求'},
    'Main Menu': {'de':'Hauptmenü','es':'Menú principal','fa':'منوی اصلی','fr':'Menu principal','hi':'मुख्य मेनू','id':'Menu Utama','it':'Menu principale','ja':'メインメニュー','ko':'메인 메뉴','pt':'Menu Principal','ru':'Главное меню','th':'เมนูหลัก','tr':'Ana Menü','ur':'مین مینو','zh':'主菜单'},
    'Admin Panel': {'de':'Admin-Panel','es':'Panel de administración','fa':'پنل مدیر','fr':'Panneau d\'administration','hi':'व्यवस्थापक पैनल','id':'Panel Admin','it':'Pannello amministratore','ja':'管理パネル','ko':'관리자 패널','pt':'Painel Administrativo','ru':'Админ-панель','th':'แผงผู้ดูแล','tr':'Yönetici Paneli','ur':'ایڈمن پینل','zh':'管理面板'},
    'No data': {'de':'Keine Daten','es':'Sin datos','fa':'بدون داده','fr':'Pas de données','hi':'कोई डेटा नहीं','id':'Tidak ada data','it':'Nessun dato','ja':'データなし','ko':'데이터 없음','pt':'Sem dados','ru':'Нет данных','th':'ไม่มีข้อมูล','tr':'Veri yok','ur':'کوئی ڈیٹا نہیں','zh':'无数据'},
    'Players': {'de':'Spieler','es':'Jugadores','fa':'بازیکنان','fr':'Joueurs','hi':'खिलाड़ी','id':'Pemain','it':'Giocatori','ja':'プレイヤー','ko':'플레이어','pt':'Jogadores','ru':'Игроки','th':'ผู้เล่น','tr':'Oyuncular','ur':'کھلاڑی','zh':'玩家'},
    'Cash Out': {'de':'Auszahlen','es':'Retirar','fa':'نقد کردن','fr':'Encaisser','hi':'नकद निकालें','id':'Tarik','it':'Incassa','ja':'換金','ko':'현금화','pt':'Sacar','ru':'Забрать','th':'ถอนเงิน','tr':'Parayı Çek','ur':'نکلوانا','zh':'兑现'},
    'History': {'de':'Verlauf','es':'Historial','fa':'تاریخچه','fr':'Historique','hi':'इतिहास','id':'Riwayat','it':'Cronologia','ja':'履歴','ko':'기록','pt':'Histórico','ru':'История','th':'ประวัติ','tr':'Geçmiş','ur':'تاریخ','zh':'历史'},
}

def build_lang_dict(lang_code):
    """Build a {english_phrase: translation} dict for a specific language."""
    result = {}
    for en_phrase, translations in DICT.items():
        if lang_code in translations:
            result[en_phrase] = translations[lang_code]
    return result

def translate_value(text, lang_dict):
    """Translate text using word-boundary regex matching."""
    if not text or not isinstance(text, str):
        return text
    result = text
    # Sort by length descending to match longer phrases first
    for en_phrase in sorted(lang_dict.keys(), key=len, reverse=True):
        translation = lang_dict[en_phrase]
        # Use word boundary matching (case-sensitive for proper nouns, case-insensitive for common words)
        pattern = re.compile(r'(?<![a-zA-Z])' + re.escape(en_phrase) + r'(?![a-zA-Z])', re.IGNORECASE)
        result = pattern.sub(translation, result)
    return result

def main():
    # Load source (English)
    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        en_data = json.load(f)

    stats = {}
    for lang in LANGUAGES:
        lang_dict = build_lang_dict(lang)
        target_file = os.path.join(I18N_DIR, f'{lang}.json')

        # Load existing file to preserve keys that might not be in en.json
        existing = {}
        if os.path.exists(target_file):
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                pass

        # Start with English as base, translate values
        translated = {}
        translated_count = 0
        total_count = 0
        for key, en_value in en_data.items():
            total_count += 1
            if isinstance(en_value, str):
                new_val = translate_value(en_value, lang_dict)
                translated[key] = new_val
                if new_val != en_value:
                    translated_count += 1
            else:
                translated[key] = en_value

        # Merge: keep translated values, add any keys from existing not in en
        for key, val in existing.items():
            if key not in translated:
                translated[key] = val

        # Write
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(translated, f, ensure_ascii=False, indent=2)

        stats[lang] = {'total': total_count, 'translated': translated_count, 'dict_size': len(lang_dict)}
        print(f"  {lang}: {translated_count}/{total_count} values translated (dict: {len(lang_dict)} entries)")

    print(f"\n✅ Done! {len(LANGUAGES)} languages updated.")
    return stats

if __name__ == '__main__':
    print("🌍 i18n Multi-Language Translator")
    print(f"   Source: en.json ({len(json.load(open(SOURCE_FILE, encoding='utf-8')))} keys)")
    print(f"   Target: {', '.join(LANGUAGES)}")
    print(f"   Dictionary: {len(DICT)} phrases × {len(LANGUAGES)} languages")
    print()
    main()

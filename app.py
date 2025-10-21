# ---------------- IMPORTS ----------------
from nicegui import ui
import gspread
from google.oauth2.service_account import Credentials
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from email.header import Header
import json
from datetime import datetime
import os
from dotenv import load_dotenv
import logging

# =========================
#   INITIALISIERUNG
# =========================
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
print('🧩 Logging initialisiert – Live Tail aktiv!')

# =========================
#   KONFIG LADEN
# =========================
def load_config():
    base_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_path, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

CFG = load_config()
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')

print('⚙️ GELADENE KONFIGURATION:')
print('SMTP Host:', CFG['smtp_host'])
print('SMTP Port:', CFG['smtp_port'])
print('SMTP User:', CFG['smtp_user'])
print('SMTP Passwort erkannt:' if SMTP_PASSWORD else '⚠️ Kein SMTP Passwort gefunden!')

# =========================
#   GOOGLE SHEETS VERBINDUNG
# =========================
SCOPE = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

try:
    if os.environ.get('GOOGLE_CREDENTIALS_JSON'):
        creds_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
        CREDS = Credentials.from_service_account_info(creds_info, scopes=SCOPE)
        print('🔑 Credentials: aus GOOGLE_CREDENTIALS_JSON geladen')
    else:
        cred_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
        with open(cred_path, 'r', encoding='utf-8') as f:
            CREDS = Credentials.from_service_account_info(json.load(f), scopes=SCOPE)
        print(f'🔑 Credentials: aus Datei {cred_path} geladen')

    CLIENT = gspread.authorize(CREDS)
    SPREADSHEET = CLIENT.open_by_key('1b26Bz5KfPo1tePKBJ7_3tCM4kpKP5PRCO2xdVr0MMOo')
    print('📄 Verbindung zu Google Spreadsheet erfolgreich hergestellt.')
except Exception as e:
    print('❌ Verbindung zu Google Sheets fehlgeschlagen:', e)
    raise SystemExit(1)

# =========================
#   CAMPS AUTOMATISCH LADEN (ohne Verwaltungsblätter)
# =========================
def get_camp_names():
    """Lädt automatisch alle Camp-Blätter, schließt aber Verwaltungsblätter wie 'Camp-Preise' aus."""
    try:
        worksheets = SPREADSHEET.worksheets()
        exclude = {'Camp-Preise', 'Preise', 'Config', 'Einstellungen'}
        camp_names = [
            ws.title.strip()
            for ws in worksheets
            if ws.title.strip() and ws.title.strip() not in exclude
        ]
        camp_names = sorted(set(camp_names))
        print(f'📋 Gefundene Camps: {camp_names}')
        return camp_names
    except Exception as e:
        print('❌ Fehler beim Laden der Camp-Namen:', e)
        return ['Camp-Auswahl']

# =========================
#   CAMP-PREISE LADEN UND BEREINIGEN
# =========================
def get_camp_prices():
    """Liest 'Camp-Preise' und konvertiert z. B. '1.140,00€' → 1140.00 (float)."""
    try:
        sheet = SPREADSHEET.worksheet('Camp-Preise')
        data = sheet.get_all_values()

        prices = {}
        for row in data[1:]:  # erste Zeile ist Überschrift
            if len(row) < 2:
                continue
            name = (row[0] or '').strip()
            preis_raw = (row[1] or '').strip()

            preis_clean = (
                preis_raw.replace('€', '')
                         .replace(' ', '')
                         .replace('.', '')
                         .replace(',', '.')
                         .strip()
            )
            try:
                preis = float(preis_clean)
            except ValueError:
                continue

            if name:
                prices[name] = preis

        print(f'💰 Camp-Preise korrekt geladen: {prices}')
        return prices

    except Exception as e:
        print('⚠️ Fehler beim Laden der Preisliste:', e)
        return {}

# =========================
#   E-MAIL SIGNATUR
# =========================
EMAIL_SIGNATURE = """\
#caprisonnewurstpanzenberg

Dein Team der BSV-Fußballschule
E-Mail: fussballschule@bremer-sv.de

Bremer Sport-Verein 1906 e.V.
Landwehrstraße 4
28217 Bremen

Vertreten durch:
Dr. Peter Warnecke // Präsident
Alfons van Werde // Vorstand Finanzen / Organisation
Jens Fröhlich // Vorstand Sport
Bastian Fritsch // Vorstand Marketing / Kommunikation
Horst Neugebauer // Vorstand Partnerbetreuung / Veranstaltungen

Telefon: +49(0) 421 396 1768
E-Mail: kontakt@bremer-sv.de
Internet: www.bremer-sv.de

Eintragung im Vereinsregister:
Amtsgericht Bremen VR 2286 HB

Unsere Überzeugung ist, dass der BSV nicht nur auf Mehrwegbecher im Stadion setzt,
sondern auch in der Verwaltung nahezu papierfrei agiert. Wir begrüßen daher gerne
E-Mails und PDFs, erhalten aber auch noch Post, die wir grundsätzlich einscannen.
"""

# =========================
#   E-MAIL FUNKTION
# =========================
def send_email(to_address: str, subject: str, body: str):
    if not SMTP_PASSWORD:
        raise RuntimeError('SMTP_PASSWORD fehlt – Versand nicht möglich.')

    from_email = CFG['smtp_user']
    from_name = CFG['from_name']
    encoded_from = formataddr((str(Header(from_name, 'utf-8')), from_email))

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = encoded_from
    msg['To'] = to_address
    msg['Subject'] = Header(subject, 'utf-8')
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=from_email.split('@')[-1])

    try:
        with smtplib.SMTP_SSL(CFG['smtp_host'], int(CFG['smtp_port']), context=ssl.create_default_context()) as server:
            server.login(from_email, SMTP_PASSWORD)
            server.sendmail(from_email, [to_address], msg.as_string())
        print(f'✅ E-Mail an {to_address} gesendet.')
    except Exception as e:
        print(f'❌ Fehler beim E-Mail-Versand an {to_address}: {e}')
        raise

# =========================
#   ANMELDUNG / SHEET
# =========================
def save_to_sheet(camp_name, vorname, nachname, alter, telefon, email, frueh, allergien, anmerkung):
    zeitstempel = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    try:
        worksheet = SPREADSHEET.worksheet(camp_name)
    except Exception:
        worksheet = SPREADSHEET.add_worksheet(title=camp_name, rows=100, cols=10)
        worksheet.append_row(["Vorname","Nachname","Alter","Telefon","E-Mail","Frühbetreuung","Allergien","Anmerkung","Zeitstempel"])
    worksheet.append_row([vorname,nachname,alter,telefon,email,frueh,allergien,anmerkung,zeitstempel])

# =========================
#   ANMELDUNGSPROZESS
# =========================
def anmelden():
    def valid_email(x): return '@' in x and '.' in x
    def valid_phone(x): return all(c.isdigit() or c in [' ', '+', '-', '(', ')'] for c in x) and len(x.strip()) >= 6

    if not all([camp.value, vorname.value, nachname.value, alter.value, telefon.value, email.value, frueh.value]):
        ui.notify('Bitte alle Pflichtfelder ausfüllen.', color='red'); return
    if not alter.value.isdigit():
        ui.notify('Alter bitte nur als Zahl angeben.', color='red'); return
    if not valid_phone(telefon.value):
        ui.notify('Ungültige Telefonnummer.', color='red'); return
    if not valid_email(email.value):
        ui.notify('Ungültige E-Mail-Adresse.', color='red'); return
    if not agb_checkbox.value:
        ui.notify('Bitte bestätige die AGB, bevor du fortfährst.', color='red'); return

    try:
        # --- Preisberechnung für E-Mail ---
        camp_prices = get_camp_prices()
        base_price = camp_prices.get(camp.value, 0.0)
        extra_price = 0.0
        if '15' in (frueh.value or ''):
            extra_price = 15.0
        total_price = base_price + extra_price

        # --- Daten speichern ---
        save_to_sheet(
            camp.value,
            vorname.value.strip(),
            nachname.value.strip(),
            alter.value.strip(),
            telefon.value.strip(),
            email.value.strip(),
            frueh.value,
            allergien.value.strip() or 'Keine',
            anmerkung.value.strip() or '-'
        )

        # --- BESTÄTIGUNGSMail MIT PREISZUSAMMENSETZUNG ---
        send_email(email.value, 'Anmeldebestätigung Fußballcamp',
f"""Hallo {vorname.value},

vielen Dank für deine Anmeldung zum Fußballcamp! ⚽
Wir haben deine Daten erhalten und freuen uns auf dich.

Hier nochmal deine Angaben zur Kontrolle:

📋 CAMP-DATEN
Camp: {camp.value}

👤 TEILNEHMER
Vorname: {vorname.value}
Nachname: {nachname.value}
Alter: {alter.value}

📞 KONTAKT
Telefon (Notfall): {telefon.value}
E-Mail: {email.value}

🕗 FRÜHBETREUUNG
{frueh.value}

⚕️ ALLERGIEN / BESONDERHEITEN
{allergien.value or 'Keine'}

🗒️ ANMERKUNG
{anmerkung.value or '-'}

💶 KOSTENÜBERSICHT
Grundpreis: {base_price:.2f} €
{'Frühbetreuung: +15,00 €' if extra_price else ''}
----------------------------
Gesamtbetrag: {total_price:.2f} €

📅 Eingegangen am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Sollte dir ein Fehler auffallen, antworte einfach auf diese Mail und teile uns die Korrektur mit.

Viele Grüße,
{CFG['from_name']}

💡 Hinweis: Sollte keine Bestätigungsmail eingehen, bitte auch im Spam-Ordner nachsehen.

{EMAIL_SIGNATURE}""")

        # --- INTERNER MAILVERSAND AN SCHULE ---
        send_email(CFG['school_notify_to'], f'Neue Anmeldung: {vorname.value} {nachname.value}',
f"""Neue Anmeldung für das Fußballcamp!

Vorname: {vorname.value}
Nachname: {nachname.value}
Camp: {camp.value}
Alter: {alter.value}
Telefon (Notfall): {telefon.value}
E-Mail: {email.value}
Frühbetreuung: {frueh.value}
Allergien/Besonderheiten: {allergien.value or 'Keine'}
Anmerkung: {anmerkung.value or '-'}

💶 Preisübersicht:
Grundpreis: {base_price:.2f} €
{'Frühbetreuung: +15,00 €' if extra_price else ''}
Gesamtbetrag: {total_price:.2f} €

Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

{EMAIL_SIGNATURE}""")

        ui.notify(f'✅ Anmeldung für {vorname.value} {nachname.value} gespeichert & Mails versendet.', color='green')
        vorname.value = nachname.value = alter.value = telefon.value = email.value = allergien.value = anmerkung.value = ''
        frueh.value = ''

    except Exception as e:
        ui.notify(f'❌ Fehler: {e}', color='red')
        print(e)

# =========================
#   DESIGN
# =========================
ui.add_head_html("""
<style>
body {
  background: linear-gradient(180deg, #002B7F 0%, #0044CC 100%);
  color: white;
  font-family: 'Inter', sans-serif;
  background-image: url('https://tmssl.akamaized.net//images/foto/stadionnormal/sportanlage-panzenberg-1433365489-9474.jpg?lm=1491209227');
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
  overflow-x: hidden;
}

/* Hauptblöcke */
.mainblock, .campblock {
  backdrop-filter: blur(10px);
  background-color: rgba(255,255,255,0.8);
  color: black;
  padding: 1.5rem 2rem;
  border-radius: 1rem;
  box-shadow: 0 4px 18px rgba(0,0,0,0.3);
  text-align: center;
  margin: 1rem auto;
  width: 100%;
  max-width: 600px;
  position: relative;
  z-index: 1;
  overflow: visible !important;
}

/* Pflichtfeld Sternchen */
.required::after {
  content: ' *';
  color: red;
  font-weight: bold;
}

/* Dropdown-Menü */
.q-menu, .q-select__dialog {
  z-index: 9999 !important;
  position: absolute !important;
  max-height: 300px !important;
  overflow-y: auto !important;
  background: white !important;
  color: #002B7F !important;
  font-weight: 500 !important;
  border-radius: 0.5rem !important;
  box-shadow: 0 4px 10px rgba(0,0,0,0.25) !important;
}
.q-item__label { color: #002B7F !important; }

/* Button */
.button {
  background-color: #002B7F;
  color: white;
  border-radius: 0.75rem;
  padding: 0.9rem;
  font-weight: bold;
  transition: all 0.3s ease;
  box-shadow: 0 3px 6px rgba(0,0,0,0.3);
}
.button:hover {
  background-color: #0044CC;
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 6px 12px rgba(0,0,0,0.4);
}

/* Trenner */
hr {
  border: 0;
  height: 3px;
  background: #FFD700;
  width: 100px;
  margin: 1rem auto;
  border-radius: 3px;
}

/* Notification */
.q-notification__bg--green { background-color: #008000 !important; }
.q-notification__bg--red { background-color: #b00020 !important; }

/* Responsive */
@media (max-width: 600px) {
  .mainblock, .campblock { padding: 1rem; max-width: 95%; }
  .button { font-size: 0.95rem; }
}

/* ===== AGB Accordion Styling ===== */
.q-expansion-item {
  background-color: rgba(255, 255, 255, 0.95) !important;
  color: #002B7F !important;
  border-radius: 0.5rem;
  margin-top: 0.75rem;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}
.q-expansion-item__header {
  font-weight: 600;
  color: #002B7F !important;
  background-color: rgba(255,255,255,0.9) !important;
}
.q-expansion-item__header:hover {
  background-color: #e6efff !important;
}
.q-expansion-item__content {
  background-color: rgba(255,255,255,0.9) !important;
  color: #000 !important;
}
</style>
""")

# =========================
#   UI
# =========================
with ui.column().classes('items-center w-full text-center mt-12'):
    ui.image('https://upload.wikimedia.org/wikipedia/en/f/fe/Bremer_SV_logo.png').style('width:150px; margin-bottom:10px;')

    with ui.column().classes('mainblock'):
        ui.label('⚽ Fußballcamp Anmeldung').classes('text-4xl font-bold')
        ui.html('<hr>', sanitize=False)
        ui.label('Bitte tragt eure Daten vollständig ein.').classes('text-lg')

    with ui.column().classes('campblock'):
        ui.label('🏕️ Camp-Auswahl').classes('text-3xl font-bold mb-2')
        camp_names = get_camp_names() or ['Camp-Auswahl']
        camp_prices = get_camp_prices()

        camp = ui.select(camp_names, value=camp_names[0], label='Camp').classes('w-full text-lg required')
        camp_preis_label = ui.label('').classes('text-lg mt-2 text-blue-800 font-bold')

        # --- Preisberechnung (inkl. Frühbetreuung) ---
        def update_total_price(_=None):
            base = camp_prices.get(camp.value)
            extra = 0.0
            if 'frueh' in globals() and frueh.value:
                if '15' in frueh.value:
                    extra = 15.0

            if base is not None:
                text = f'💰 Teilnahmegebühr: {base:.2f} €'
                if extra:
                    text += f' + 15,00 € Frühbetreuung = {(base + extra):.2f} €'
                camp_preis_label.text = text
            else:
                camp_preis_label.text = ''

        camp.on('update:model-value', update_total_price)
        update_total_price()
        ui.html('<hr>', sanitize=False)

    with ui.column().classes('mainblock mt-2'):
        with ui.row():
            vorname = ui.input('Vorname').classes('w-full required')
            nachname = ui.input('Nachname').classes('w-full required')
        with ui.row():
            alter = ui.input('Alter').classes('w-full required')
            telefon = ui.input('Telefonnummer (Notfall)').classes('w-full required')
        with ui.row():
            email = ui.input('E-Mail (für Bestätigung)').classes('w-full required')
            frueh = ui.select(
                ['', 'Keine', 'ab 08:00 Uhr (+ 15,00 €)'],
                value='',
                label='Frühbetreuung ab …'
            ).classes('w-full required')

        # Frühbetreuung wirkt sich auf den Preis aus
        frueh.on('update:model-value', update_total_price)
        update_total_price()

        allergien = ui.input('Allergien / Besonderheiten').classes('w-full')
        anmerkung = ui.input('Anmerkung').classes('w-full')

        # 🟩 Preis-Zusammenfassung direkt über dem Button
        gesamt_label = ui.label('').classes('text-lg font-bold text-green-700 mt-4')

        def update_summary(_=None):
            base = camp_prices.get(camp.value, 0.0)
            extra = 0.0
            if 'frueh' in globals() and frueh.value:
                if '15' in frueh.value:
                    extra = 15.0
            if base:
                gesamt_label.text = f'➡️ Gesamtbetrag: {(base + extra):.2f} €'
            else:
                gesamt_label.text = ''

        camp.on('update:model-value', update_summary)
        frueh.on('update:model-value', update_summary)
        update_summary()

        ui.label('* Pflichtfelder').style('color: red; font-size: 0.9rem; margin-top: 0.5rem;')

        # =========================
        #   AGB CHECKBOX + AUSKLAPPEN
        # =========================
        with ui.row().classes('items-start mt-4 w-full'):
            agb_checkbox = ui.checkbox('Ich habe die AGB gelesen und akzeptiere sie.').classes('required')

        agb_expansion = ui.expansion('📄 AGB ausklappen').classes('w-full mt-2 text-blue-900 font-semibold')
        with agb_expansion:
            ui.markdown("""
**für die Teilnahme an Fußballcamps der Fußballschule Bremer SV**

1. **Veranstalter**  
Veranstalter der Fußballcamps ist die Fußballschule Bremer SV, Hohweg 48–50, 28219 Bremen (nachfolgend „Veranstalter“ genannt).

2. **Anmeldung und Vertragsschluss**  
Die Anmeldung erfolgt über das Online-Formular oder schriftlich.  
Mit der Bestätigung durch den Veranstalter (per E-Mail) kommt der Teilnahmevertrag zustande.  
Die Teilnahmeplätze werden in der Reihenfolge der Anmeldungen vergeben.

3. **Teilnahmegebühr und Zahlung**  
Die Teilnahmegebühr ist dem jeweiligen Camp-Angebot zu entnehmen.  
Die Zahlung erfolgt gemäß der in der Anmeldebestätigung genannten Zahlungsweise (z. B. Barzahlung am ersten Camptag oder Überweisung vorab).  
Eine Teilnahme ist nur bei vollständiger Zahlung möglich.

4. **Rücktritt / Stornierung durch Teilnehmer**  
Ein Rücktritt ist bis 14 Tage vor Campbeginn kostenfrei möglich.  
Bei späterer Absage bis 7 Tage vor Beginn werden 50 % der Teilnahmegebühr fällig.  
Bei Absage innerhalb von 7 Tagen vor Campbeginn oder Nichterscheinen ist der volle Betrag zu zahlen.  
Eine Erstattung bei vorzeitigem Abbruch des Camps ist ausgeschlossen.

5. **Absage oder Änderung durch den Veranstalter**  
Der Veranstalter behält sich vor, das Camp aus wichtigen Gründen (z. B. zu geringe Teilnehmerzahl, Krankheit, höhere Gewalt, behördliche Anordnung) abzusagen oder zu verschieben.  
In diesem Fall wird die Teilnahmegebühr vollständig erstattet. Weitere Ansprüche bestehen nicht.

6. **Haftung**  
Die Teilnahme erfolgt auf eigene Gefahr.  
Der Veranstalter haftet nur für Schäden, die auf vorsätzliches oder grob fahrlässiges Verhalten seiner Mitarbeiter oder Erfüllungsgehilfen zurückzuführen sind.  
Für mitgebrachte Gegenstände, Kleidung oder Wertsachen wird keine Haftung übernommen.  
Eine private Unfall- und Haftpflichtversicherung wird empfohlen.

7. **Gesundheitszustand**  
Mit der Anmeldung bestätigen die Erziehungsberechtigten, dass das Kind körperlich gesund und sportlich belastbar ist.  
Eventuelle gesundheitliche Einschränkungen, Allergien oder notwendige Medikamente sind bei der Anmeldung anzugeben.

8. **Foto- und Videoaufnahmen**  
Während der Camps können Foto- und Videoaufnahmen gemacht werden.  
Diese dürfen vom Veranstalter für Vereinszwecke, Berichterstattung und Öffentlichkeitsarbeit (z. B. Website, Social Media, Printmedien) verwendet werden.  
Sollte dies nicht gewünscht sein, ist der Veranstalter vor Campbeginn schriftlich zu informieren.

9. **Datenschutz**  
Die erhobenen Daten werden ausschließlich zur Durchführung des Camps und zur Kommunikation im Rahmen der Veranstaltung genutzt.  
Eine Weitergabe an Dritte erfolgt nicht.  
Weitere Informationen zum Datenschutz sind in der Datenschutzerklärung unter www.bremer-sv.de/datenschutz abrufbar.

10. **Salvatorische Klausel**  
Sollten einzelne Bestimmungen dieser AGB unwirksam sein, bleibt die Wirksamkeit der übrigen Bestimmungen unberührt.

11. **Gerichtsstand**  
Es gilt deutsches Recht. Gerichtsstand ist – soweit zulässig – Bremen.

📅 *Stand: Oktober 2025*  
*Fußballschule Bremer SV – gemeinsam kicken, lernen, wachsen.*
            """).classes('text-sm leading-relaxed text-left')

        # =========================
        #   ABSENDEN
        # =========================
        submit_btn = ui.button('JETZT ANMELDEN', on_click=anmelden).classes('button w-full mt-4')
        # UX: Button nur aktiv, wenn AGB angehakt
        submit_btn.bind_enabled_from(agb_checkbox, 'value')

        ui.label('💡 Sollte keine Bestätigungsmail eingehen, bitte auch im Spam-Ordner nachsehen.').classes('hinweis text-center')
        ui.html(
            '✉️ Bei Problemen oder anderen Anfragen schreibt uns bitte direkt eine '
            '<a href="mailto:fussballschule@bremer-sv.de" style="color:#002B7F; text-decoration:underline;">E-Mail</a>.',
            sanitize=False
        ).classes('hinweis text-center').style('margin-top:0.5rem;')

# =========================
#   START SERVER
# =========================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    ui.run(title='Fußballcamp Anmeldung', host='0.0.0.0', port=port, reload=False)

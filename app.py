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
#   CAMP-BILDER LADEN
# =========================
def get_camp_images():
    """Liest Bildpfade oder URLs aus dem Sheet 'Camp-Preise' (Spalte 4).
    Unterstützt lokale Bilder im Ordner 'static/images' UND externe Links (z. B. https://...).
    """
    try:
        sheet = SPREADSHEET.worksheet('Camp-Preise')
        data = sheet.get_all_values()
        images = {}
        for row in data[1:]:
            if len(row) >= 4 and row[0].strip() and row[3].strip():
                camp_name = row[0].strip()
                img_url = row[3].strip()

                # Falls Google-Drive-Link, automatisch umwandeln
                if "drive.google.com/file/d/" in img_url:
                    try:
                        file_id = img_url.split("/d/")[1].split("/")[0]
                        img_url = f"https://drive.google.com/uc?export=view&id={file_id}"
                    except Exception:
                        pass

                # Falls kein https-Link: Lokale Datei in static/images/
                elif not img_url.startswith("http"):
                    img_url = f"static/images/{img_url}"

                images[camp_name] = img_url

        print(f"🖼️ Camp-Bilder geladen: {list(images.keys())}")
        return images
    except Exception as e:
        print("⚠️ Fehler beim Laden der Camp-Bilder:", e)
        return {}
    
# =========================
#   CAMP-KAPAZITÄTEN UND VERFÜGBARKEIT
# =========================
def get_camp_capacities():
    """Liest die maximale Teilnehmerzahl je Camp aus dem Sheet 'Camp-Preise'."""
    try:
        sheet = SPREADSHEET.worksheet('Camp-Preise')
        data = sheet.get_all_values()
        capacities = {}
        for row in data[1:]:
            if len(row) >= 3 and row[0].strip():
                camp_name = row[0].strip()
                try:
                    capacities[camp_name] = int(row[2])
                except ValueError:
                    capacities[camp_name] = None
        print(f'📈 Camp-Kapazitäten geladen: {capacities}')
        return capacities
    except Exception as e:
        print('⚠️ Fehler beim Laden der Kapazitäten:', e)
        return {}

def get_registered_count(camp_name):
    """Zählt, wie viele Teilnehmer bereits im jeweiligen Camp eingetragen sind."""
    try:
        worksheet = SPREADSHEET.worksheet(camp_name)
        data = worksheet.get_all_values()
        return max(0, len(data) - 1)  # minus Headerzeile
    except Exception:
        return 0

def is_camp_full(camp_name):
    """Prüft, ob das Camp ausgebucht ist."""
    caps = get_camp_capacities()
    max_cap = caps.get(camp_name)
    current = get_registered_count(camp_name)
    if not max_cap:
        return False
    return current >= max_cap

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
#   E-MAIL FUNKTION (BREVO API)
# =========================
import requests

def send_email(to_address: str, subject: str, body: str):
    """Versendet E-Mails über die Brevo API (sicher, portfrei, render-kompatibel)."""

    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise RuntimeError("BREVO_API_KEY fehlt – Versand nicht möglich.")

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    payload = {
        "sender": {"name": "BSV Fußballschule", "email": "fussballschule@bremer-sv.de"},
        "to": [{"email": to_address}],
        "subject": subject,
        "textContent": body,
        "replyTo": {"email": "fussballschule@bremer-sv.de"},
    }

    try:
        print(f"📨 Sende E-Mail an {to_address} über Brevo API...")
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code == 201:
            print(f"✅ E-Mail erfolgreich an {to_address} gesendet.")
        else:
            print(f"❌ Fehler beim Versand an {to_address}: {response.status_code} – {response.text}")
            response.raise_for_status()

    except Exception as e:
        print(f"❌ Ausnahme beim API-Versand an {to_address}: {e}")
        raise

# =========================
#   ANMELDUNG / SHEET
# =========================
def save_to_sheet(camp_name, vorname, nachname, alter, telefon, email, frueh, allergien, anmerkung):
    """Speichert Anmeldedaten im richtigen Spaltenformat."""
    zeitstempel = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    try:
        worksheet = SPREADSHEET.worksheet(camp_name)
    except Exception:
        worksheet = SPREADSHEET.add_worksheet(title=camp_name, rows=100, cols=10)
        worksheet.append_row([
            "Vorname", "Nachname", "Alter", "Telefon", "E-Mail",
            "Allergien", "Frühbetreuung", "Anmerkung", "Zeitstempel"
        ])
    worksheet.append_row([
        vorname,
        nachname,
        alter,
        telefon,
        email,
        allergien,
        frueh,
        anmerkung,
        zeitstempel
    ])

# =========================
#   ANMELDUNGSPROZESS
# =========================
def anmelden():
    def valid_email(x): return '@' in x and '.' in x
    def valid_phone(x): return all(c.isdigit() or c in [' ', '+', '-', '(', ')'] for c in x) and len(x.strip()) >= 6

    # Pflichtfelder prüfen
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

    # Teilnehmerbegrenzung prüfen
    if is_camp_full(camp.value):
        ui.notify(f'Das Camp "{camp.value}" ist bereits ausgebucht.', color='red')
        return

    try:
        # Frühbetreuung + Preis
        frueh_text = frueh.value if frueh.value else 'Keine'

        camp_prices = get_camp_prices()
        base_price = camp_prices.get(camp.value, 0.0)

        extra_price = 15.0 if '08:00' in frueh_text else 0.0
        total_price = base_price + extra_price

        # Speicherung in Sheet
        save_to_sheet(
            camp.value,
            vorname.value.strip(),
            nachname.value.strip(),
            alter.value.strip(),
            telefon.value.strip(),
            email.value.strip(),
            frueh_text,
            allergien.value.strip() or 'Keine',
            anmerkung.value.strip() or '-'
        )

        # Bestätigung an Teilnehmer
        send_email(
            email.value,
            'Anmeldebestätigung Fußballcamp',
f"""Hallo {vorname.value},

vielen Dank für deine Anmeldung zum Fußballcamp! ⚽
Wir haben deine Daten erhalten und freuen uns auf dich.

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
{frueh_text}

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

{EMAIL_SIGNATURE}"""
        )

        # Interne Benachrichtigung
        send_email(
            CFG['school_notify_to'],
            f'Neue Anmeldung: {vorname.value} {nachname.value}',
f"""Neue Anmeldung für das Fußballcamp!

Vorname: {vorname.value}
Nachname: {nachname.value}
Camp: {camp.value}
Alter: {alter.value}
Telefon (Notfall): {telefon.value}
E-Mail: {email.value}
Frühbetreuung: {frueh_text}
Allergien/Besonderheiten: {allergien.value or 'Keine'}
Anmerkung: {anmerkung.value or '-'}

💶 Preisübersicht:
Grundpreis: {base_price:.2f} €
{'Frühbetreuung: +15,00 €' if extra_price else ''}
Gesamtbetrag: {total_price:.2f} €

Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

{EMAIL_SIGNATURE}"""
        )

        ui.notify(
            f'✅ Anmeldung für {vorname.value} {nachname.value} gespeichert & Mails versendet.',
            color='green'
        )

        # Felder zurücksetzen
        vorname.value = ''
        nachname.value = ''
        alter.value = ''
        telefon.value = ''
        email.value = ''
        allergien.value = ''
        anmerkung.value = ''
        frueh.value = 'Keine'

        # Status neu berechnen (z. B. evtl. jetzt ausgebucht)
        update_camp_status()

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

    # Vereinslogo
    ui.image('https://upload.wikimedia.org/wikipedia/en/f/fe/Bremer_SV_logo.png').style(
        'width:150px; margin-bottom:10px;'
    )

    # Kopfbereich
    with ui.column().classes('mainblock'):
        ui.label('⚽ Fußballcamp Anmeldung').classes('text-4xl font-bold')
        ui.html('<hr>', sanitize=False)
        ui.label('Bitte tragt eure Daten vollständig ein.').classes('text-lg')

   # === CAMP-AUSWAHL ===
with ui.column().classes('campblock'):
    ui.label('🏕️ Camp-Auswahl').classes('text-3xl font-bold mb-2')

    camp_names = get_camp_names() or ['Camp-Auswahl']
    camp_prices = get_camp_prices()
    camp_caps = get_camp_capacities()
    camp_images = get_camp_images()  # <--- NEU: Bilder laden

    camp = ui.select(
        camp_names,
        value=camp_names[0] if camp_names else None,
        label='Camp'
    ).classes('w-full text-lg required')

    camp_status_label = ui.label('').classes('text-lg mt-2 font-bold text-red-700')
    camp_preis_label = ui.label('').classes('text-lg mt-1 text-blue-800 font-bold')

    # 🖼️ Camp-Bild (automatisch je nach Auswahl)
    camp_image = ui.image().classes('w-full rounded-xl shadow-lg mt-4').style(
        'max-width:500px; border-radius:1rem; display:block; margin:auto; transition:opacity 0.6s ease-in-out;'
    )
    camp_image.visible = False  # erst sichtbar, wenn Auswahl getroffen wurde

    ui.html('<hr>', sanitize=False)

    # === TEILNEHMERDATEN & AGB ===
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
                ['Keine', 'ab 08:00 Uhr (plus 15 Euro)'],
                value='Keine',
                label='Frühbetreuung'
            ).classes('w-full required')

        allergien = ui.input('Allergien / Besonderheiten').classes('w-full')
        anmerkung = ui.input('Anmerkung').classes('w-full')

        ui.label('* Pflichtfelder').style('color: red; font-size: 0.9rem; margin-top: 0.5rem;')

        # === AGB ===
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

        # === ABSENDEN ===
        submit_btn = ui.button('JETZT ANMELDEN', on_click=anmelden).classes('button w-full mt-4')
        submit_btn.bind_enabled_from(agb_checkbox, 'value')

        ui.label('💡 Sollte keine Bestätigungsmail eingehen, bitte auch im Spam-Ordner nachsehen.').classes('text-sm mt-2')

# === Preis-, Kapazitäts- & Bild-Update ===
def update_camp_status(_=None):
    selected = camp.value
    max_cap = camp_caps.get(selected)
    current = get_registered_count(selected)
    remaining = (max_cap - current) if max_cap else None

    # --- Verfügbarkeit ---
    if remaining is None:
        camp_status_label.text = ''
        submit_btn.enabled = True
    elif remaining <= 0:
        camp_status_label.text = f'❌ Camp ausgebucht ({current}/{max_cap})'
        camp_status_label.classes(replace='text-lg mt-2 font-bold text-red-700')
        submit_btn.enabled = False
    else:
        color_class = 'text-green-700' if remaining > 5 else 'text-orange-600'
        camp_status_label.text = f'✅ Noch {remaining} Plätze frei ({current}/{max_cap})'
        camp_status_label.classes(replace=f'text-lg mt-2 font-bold {color_class}')
        submit_btn.enabled = True

    # --- Preis anzeigen ---
    base = camp_prices.get(selected)
    camp_preis_label.text = f'💰 Teilnahmegebühr: {base:.2f} €' if base is not None else ''

    # --- Bild anzeigen ---
    img_url = camp_images.get(selected)
    if img_url:
        camp_image.set_source(img_url)
        camp_image.visible = True
    else:
        camp_image.visible = False

camp.on('update:model-value', update_camp_status)
update_camp_status()

# =========================
#   PRE-WARM-TASK
# =========================
import asyncio

async def prewarm_app():
    """Initialisiert Ressourcen, damit die App nach Render-Start sofort reagiert."""
    print("🧠 Pre-Warm-Task gestartet – initialisiere wichtige Komponenten...")

    try:
        # 1️⃣ Google Sheets vorladen
        try:
            camp_names = get_camp_names()
            camp_prices = get_camp_prices()
            camp_caps = get_camp_capacities()

            print(f"📋 Camps geladen: {len(camp_names)}")
            print(f"💰 Preislisten geladen: {len(camp_prices)}")
            print(f"📈 Kapazitäten geladen: {len(camp_caps)}")
            print("🟢 Google Sheets Verbindung aktiv.")
        except Exception as e:
            print(f"🔴 Fehler bei Google Sheets: {e}")

        # 2️⃣ Brevo / API-Key prüfen
        api_key = os.environ.get("BREVO_API_KEY") or os.environ.get("SMTP_PASSWORD")
        if api_key:
            print("📡 Brevo API-Key erkannt – Versandmodul bereit.")
        else:
            print("⚠️ Kein Brevo API-Key gefunden! Bitte in Render Environment setzen.")

        # 3️⃣ Konfiguration prüfen
        try:
            print(f"⚙️ SMTP Host: {CFG.get('smtp_host', 'unbekannt')}")
            print(f"⚙️ SMTP User: {CFG.get('smtp_user', 'unbekannt')}")
        except Exception:
            print("⚠️ Keine CFG-Daten verfügbar.")

        # 4️⃣ Simulierte Initial-Delay (für Cold-Start-Puffer)
        await asyncio.sleep(1)
        print("🔥 Pre-Warm abgeschlossen – App vollständig startbereit!")

    except Exception as e:
        print(f"❌ Unerwarteter Fehler im Pre-Warm-Task: {e}")


# Task nach App-Start ausführen
asyncio.get_event_loop().create_task(prewarm_app())

# =========================
#   START SERVER
# =========================
print("🧠 Debug: Starte NiceGUI...")
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    ui.run(title='Fußballcamp Anmeldung', host='0.0.0.0', port=port, reload=False)

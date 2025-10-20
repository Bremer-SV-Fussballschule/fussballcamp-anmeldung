from nicegui import ui
import gspread
from google.oauth2.service_account import Credentials
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
from datetime import datetime
import os


# ---------------- CONFIG LADEN ----------------
def load_config():
    base_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_path, "config.json")
    with open(config_path, "r") as f:
        return json.load(f)


CFG = load_config()
print("⚙️ GELADENE KONFIGURATION:")
print("SMTP Host:", CFG["smtp_host"])
print("SMTP Port:", CFG["smtp_port"])
print("SMTP User:", CFG["smtp_user"])


# ---------------- GOOGLE SHEET VERBINDUNG ----------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
CLIENT = gspread.authorize(CREDS)
SHEET = CLIENT.open_by_key("1b26Bz5KfPo1tePKBJ7_3tCM4kpKP5PRCO2xdVr0MMOo").sheet1


# ---------------- E-MAIL FUNKTION ----------------
def send_email(to_address, subject, body):
    msg = MIMEMultipart()
    msg["From"] = f"{CFG['from_name']} <{CFG['smtp_user']}>"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        print(f"📨 Verbinde zu {CFG['smtp_host']} (SSL, Port {CFG['smtp_port']})...")
        with smtplib.SMTP_SSL(CFG["smtp_host"], CFG["smtp_port"], context=context, timeout=20) as server:
            server.login(CFG["smtp_user"], CFG["smtp_password"])
            server.send_message(msg)
        print(f"✅ E-Mail erfolgreich an {to_address} gesendet.")
    except Exception as e:
        print(f"❌ Fehler beim E-Mail-Versand: {e}")
        raise


# ---------------- ANMELDUNG VERARBEITEN ----------------
def save_to_sheet(vorname, nachname, alter, telefon, email, frueh, allergien, anmerkung):
    zeitstempel = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    SHEET.append_row([vorname, nachname, alter, telefon, email, frueh, allergien, anmerkung, zeitstempel])


# ---------------- HAUPTFUNKTION ----------------
def anmelden():
    if not (vorname.value and nachname.value and email.value):
        ui.notify("Bitte mindestens Vorname, Nachname und E-Mail ausfüllen.", color="red")
        return

    try:
        save_to_sheet(
            vorname.value,
            nachname.value,
            alter.value,
            telefon.value,
            email.value,
            frueh.value,
            allergien.value,
            anmerkung.value,
        )

        teilnehmer_text = f"""Hallo {vorname.value},

vielen Dank für deine Anmeldung zum Fußballcamp! ⚽
Wir haben deine Daten erhalten und freuen uns auf dich.

Viele Grüße,
{CFG['from_name']}
--
Fußballschule Bremer SV
E-Mail: fussballschule@bremer-sv.de
Web: www.bremer-sv.de
"""
        send_email(email.value, "Anmeldebestätigung Fußballcamp", teilnehmer_text)

        orga_text = f"""Neue Anmeldung für das Fußballcamp!

Vorname: {vorname.value}
Nachname: {nachname.value}
Alter: {alter.value}
Telefon (Notfall): {telefon.value}
E-Mail: {email.value}
Frühbetreuung: {frueh.value}
Allergien/Besonderheiten: {allergien.value}
Anmerkung: {anmerkung.value}
Zeit: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}
"""
        send_email(CFG["school_notify_to"], f"Neue Anmeldung: {vorname.value} {nachname.value}", orga_text)

        ui.notify(f"Anmeldung für {vorname.value} {nachname.value} gespeichert & Mails versendet.", color="green")

        # Felder leeren
        vorname.value = nachname.value = alter.value = telefon.value = email.value = ""
        allergien.value = anmerkung.value = ""
        frueh.value = "Keine"

    except Exception as e:
        ui.notify(f"Fehler bei der Anmeldung: {e}", color="red")
        print(e)


# ---------------- DESIGN / UI ----------------

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
}
.card {
    background-color: rgba(255,255,255,0.95);
    color: #002B7F;
    border-radius: 1rem;
    box-shadow: 0 6px 25px rgba(0,0,0,0.3);
    padding: 2rem;
    z-index: 2;
    position: relative;
}
.titlebox {
    background-color: rgba(255,255,255,0.9);
    color: black;
    padding: 1.2rem 2rem;
    border-radius: 1rem;
    box-shadow: 0 4px 18px rgba(0,0,0,0.3);
    display: inline-block;
    text-align: center;
    margin-bottom: 1rem;
}
.button {
    background-color: #002B7F;
    color: white;
    border-radius: 0.75rem;
    padding: 0.75rem;
    font-weight: bold;
    transition: 0.3s;
}
.button:hover {
    background-color: #0044CC;
    transform: scale(1.03);
}
.hinweis {
    font-size: 0.9rem;
    color: #333;
    margin-top: 1rem;
}
hr {
    border: 0;
    height: 3px;
    background: #FFD700;
    width: 80px;
    margin: 1rem auto;
    border-radius: 2px;
}
</style>
""")

# ---------------- HEADER & FORM ----------------
with ui.column().classes("w-full max-w-xl mx-auto items-center text-center mt-12"):
    ui.image("https://upload.wikimedia.org/wikipedia/en/f/fe/Bremer_SV_logo.png").style("width:150px; margin-bottom:10px;")
    
    # Neuer weißer Titelrahmen mit schwarzem Text
    with ui.row().classes("justify-center"):
        with ui.column().classes("titlebox"):
            ui.label("⚽ Fußballcamp Anmeldung").classes("text-4xl font-bold")
            ui.label("Bitte tragt eure Daten vollständig ein.").classes("text-lg")

    ui.html("<hr>", sanitize=False)

    with ui.column().classes("w-full card mt-4"):
        with ui.row():
            vorname = ui.input("Vorname").classes("w-full")
            nachname = ui.input("Nachname").classes("w-full")
        with ui.row():
            alter = ui.input("Alter").classes("w-full")
            telefon = ui.input("Telefonnummer (Notfall)").classes("w-full")
        with ui.row():
            email = ui.input("E-Mail (für Bestätigung)").classes("w-full")
            frueh = ui.select(["Keine", "ab 8 Uhr (+15 €)"], value="Keine", label="Frühbetreuung ab …").classes("w-full")
        allergien = ui.input("Allergien / Besonderheiten").classes("w-full")
        anmerkung = ui.input("Anmerkung").classes("w-full")

        ui.button("JETZT ANMELDEN", on_click=anmelden).classes("button w-full mt-4")
        ui.label("💡 Sollte keine Bestätigungsmail eingehen, bitte auch im Spam-Ordner nachsehen.").classes("hinweis text-center")

# ---------------- SERVER START ----------------
ui.run(title="Fußballcamp Anmeldung", reload=False)

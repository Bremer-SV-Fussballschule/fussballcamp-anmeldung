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
from fastapi import FastAPI

# ---------------- CONFIG ----------------
def load_config():
    return {
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": int(os.getenv("SMTP_PORT", "465")),
        "smtp_user": os.getenv("SMTP_USER", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "school_notify_to": os.getenv("SCHOOL_NOTIFY_TO", ""),
        "from_name": os.getenv("FROM_NAME", "Fußballschule Bremer SV"),
    }

CFG = load_config()

# ---------------- GOOGLE SHEETS ----------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

if os.environ.get("GOOGLE_CREDENTIALS_JSON"):
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    CREDS = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
else:
    CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)

CLIENT = gspread.authorize(CREDS)
SHEET = CLIENT.open_by_key("1b26Bz5KfPo1tePKBJ7_3tCM4kpKP5PRCO2xdVr0MMOo").sheet1

# ---------------- EMAIL ----------------
def send_email(to_address, subject, body):
    msg = MIMEMultipart()
    msg["From"] = f"{CFG['from_name']} <{CFG['smtp_user']}>"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP_SSL(CFG["smtp_host"], CFG["smtp_port"], context=context) as server:
        server.login(CFG["smtp_user"], CFG["smtp_password"])
        server.send_message(msg)

# ---------------- SHEET SAVE ----------------
def save_to_sheet(vorname, nachname, alter, telefon, email, frueh, allergien, anmerkung):
    zeitstempel = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    SHEET.append_row([vorname, nachname, alter, telefon, email, frueh, allergien, anmerkung, zeitstempel])

# ---------------- UI LOGIC ----------------
def anmelden():
    if not (vorname.value and nachname.value and email.value):
        ui.notify("Bitte mindestens Vorname, Nachname und E-Mail ausfüllen.", color="red")
        return

    try:
        save_to_sheet(vorname.value, nachname.value, alter.value, telefon.value, email.value, frueh.value, allergien.value, anmerkung.value)

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

        vorname.value = nachname.value = alter.value = telefon.value = email.value = ""
        allergien.value = anmerkung.value = ""
        frueh.value = "Keine"

    except Exception as e:
        ui.notify(f"Fehler: {e}", color="red")
        print(e)

# ---------------- UI ----------------
ui.add_head_html("""
<style>
body {
    background: linear-gradient(180deg, #002B7F 0%, #0044CC 100%);
    color: white;
    font-family: 'Inter', sans-serif;
}
.card {background-color: rgba(255,255,255,0.95); color: #002B7F; border-radius: 1rem; box-shadow: 0 6px 25px rgba(0,0,0,0.3); padding: 2rem;}
.titlebox {background-color: rgba(255,255,255,0.9); color: black; padding: 1.2rem 2rem; border-radius: 1rem; margin-bottom: 1rem;}
.button {background-color: #002B7F; color: white; border-radius: 0.75rem; padding: 0.75rem; font-weight: bold;}
.button:hover {background-color: #0044CC;}
</style>
""")

with ui.column().classes("w-full max-w-xl mx-auto items-center text-center mt-12"):
    ui.image("https://upload.wikimedia.org/wikipedia/en/f/fe/Bremer_SV_logo.png").style("width:150px; margin-bottom:10px;")
    with ui.column().classes("titlebox"):
        ui.label("⚽ Fußballcamp Anmeldung").classes("text-4xl font-bold")
        ui.label("Bitte tragt eure Daten vollständig ein.").classes("text-lg")
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
        ui.label("💡 Sollte keine Bestätigungsmail eingehen, bitte auch im Spam-Ordner nachsehen.")

# ---------------- SERVER START ----------------
PORT = int(os.environ.get("PORT", 8080))
fastapi_app = FastAPI()
ui.run_with(fastapi_app)
application = fastapi_app

if __name__ == "__main__":
    ui.run(title="Fußballcamp Anmeldung", host="0.0.0.0", port=PORT)

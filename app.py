# -----------------------------
# Fußballcamp-Anmeldung (NiceGUI)
# Kompatibel mit Render & lokal
# -----------------------------

from nicegui import ui
from fastapi import FastAPI
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from email_validator import validate_email, EmailNotValidError

# 1️⃣ Umgebung laden (.env für lokal, Render ENV für Deployment)
load_dotenv()

# 2️⃣ Google Credentials laden
if "GOOGLE_CREDENTIALS_JSON" in os.environ:
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
else:
    with open("credentials.json") as f:
        creds_dict = json.load(f)

creds = Credentials.from_service_account_info(
    creds_dict,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gc = gspread.authorize(creds)

# 3️⃣ Spreadsheet-ID hier eintragen!
SPREADSHEET_ID = "DEINE_SPREADSHEET_ID_HIER"  # Beispiel: 1AbCdEfG12345XYZ67890

# 4️⃣ FastAPI-App für Render
fastapi_app = FastAPI()
ui.run_with(fastapi_app)

# 5️⃣ NiceGUI-Seite
@ui.page("/")
def index_page():
    ui.label("⚽ Fußballcamp Anmeldung").classes("text-3xl font-bold mt-8 mb-4")

    name = ui.input("Name").classes("w-full max-w-md")
    alter = ui.input("Alter").classes("w-full max-w-md")
    notfallnummer = ui.input("Notfallnummer").classes("w-full max-w-md")
    email = ui.input("E-Mail-Adresse (optional)").classes("w-full max-w-md")

    feedback = ui.label().classes("mt-4 text-green-600")

    def send_form():
        try:
            # E-Mail validieren (wenn angegeben)
            if email.value:
                validate_email(email.value)

            sh = gc.open_by_key(SPREADSHEET_ID)
            ws = sh.sheet1
            ws.append_row([name.value, alter.value, notfallnummer.value, email.value])

            feedback.text = "✅ Anmeldung erfolgreich gespeichert!"
            feedback.classes(replace="text-green-600")
        except EmailNotValidError:
            feedback.text = "❌ Ungültige E-Mail-Adresse."
            feedback.classes(replace="text-red-600")
        except Exception as e:
            feedback.text = f"❌ Fehler: {e}"
            feedback.classes(replace="text-red-600")

    ui.button("Absenden", on_click=send_form).classes("bg-blue-600 text-white mt-4")

# 6️⃣ Einstiegspunkte
application = fastapi_app  # für Render

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    ui.run(
        title="Fußballcamp Anmeldung",
        host="0.0.0.0",
        port=port,
        reload=False
    )

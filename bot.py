import logging
import os
import json
import http.server
import socketserver
import threading
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# Import configurations and handlers
from config import TELEGRAM_BOT_TOKEN
from state_manager import (
    get_user_state,
    update_user_state,
    clear_user_state,
    load_messages_from_file,
    save_message_to_file,
    get_messages_file_path,
    delete_last_message_from_file,
    delete_all_messages_from_file,
    clear_entire_message_file
)
from meme_handler import get_available_templates, create_meme, is_video_file

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- KEYBOARD HELPERS ---
def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton("Meme Generator"), KeyboardButton("Nachricht schreiben")],
        [KeyboardButton("Name ändern")],
        [KeyboardButton("Letzte Nachricht löschen"), KeyboardButton("Alle meine Nachrichten löschen")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    keyboard = [[KeyboardButton("/cancel")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --- HTTP API SERVER FOR THE WEBSITE ---
class MessagesAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request logging to keep the terminal clean
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/api/messages", "/messages.json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                messages = load_messages_from_file()
                self.wfile.write(json.dumps(messages, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                logger.error(f"Error serving messages: {e}")
                self.wfile.write(b"[]")
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server(port=5000):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    
    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), MessagesAPIHandler)
        logger.info(f"API HTTP Server started on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start API HTTP Server: {e}")


# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start-Command: Begrüßung und Name einrichten oder auflisten."""
    chat_id = update.effective_chat.id
    user_state = get_user_state(chat_id)
    saved_name = user_state.get("user_name")
    
    if not saved_name:
        # Ersteinrichtung Name (Keyboard ausblenden, damit der Nutzer tippt)
        update_user_state(chat_id, "state", "waiting_for_name_setup")
        await update.message.reply_text(
            "Hallo ich bin Megamilan. Wie lautet dein Name?",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        # Bereits eingerichtet - Menü-Keyboard anzeigen
        await update.message.reply_text(
            f"Hallo {saved_name}! Ich bin dein multifunktionaler Bot.\n\n"
            "Folgende Features stehen dir zur Verfügung:\n\n"
            "Meme Generator\n"
            "Nutze /memegen oder klicke unten auf den Button.\n\n"
            "Nachricht schreiben\n"
            "Nutze /message <deine Nachricht> oder klicke unten auf den Button.\n"
            f"Einträge werden automatisch unter dem Namen {saved_name} gespeichert.\n\n"
            "Name ändern\n"
            "Nutze /changename oder klicke auf den Button.\n\n"
            "Abbrechen\n"
            "Nutze /cancel um eine laufende Aktion abzubrechen.",
            reply_markup=get_main_menu_keyboard()
        )

async def changename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ändert den gespeicherten Namen des Benutzers."""
    chat_id = update.effective_chat.id
    clear_user_state(chat_id)
    
    if context.args:
        # Direkte Änderung per Argument
        new_name = " ".join(context.args).strip()
        update_user_state(chat_id, "user_name", new_name)
        await update.message.reply_text(
            f"Dein Name wurde in {new_name} geändert.",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        # Interaktive Änderung
        update_user_state(chat_id, "state", "waiting_for_name_change")
        await update.message.reply_text(
            "Bitte gib deinen neuen Namen ein:",
            reply_markup=get_cancel_keyboard()
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bricht die aktuelle Aktion (Meme-Erstellung oder Secret-Nachricht) ab."""
    chat_id = update.effective_chat.id
    user_state = get_user_state(chat_id)
    state = user_state.get("state")
    
    if state:
        clear_user_state(chat_id)
        await update.message.reply_text("Aktion abgebrochen.", reply_markup=get_main_menu_keyboard())
    else:
        await update.message.reply_text("Keine aktive Aktion vorhanden.", reply_markup=get_main_menu_keyboard())

async def memegen_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt das Menü zur Auswahl des Meme-Templates an."""
    templates = get_available_templates()
    if not templates:
        await update.message.reply_text("Keine Templates im `templates/` Ordner gefunden.")
        return
        
    keyboard = []
    # Templates als Inline-Buttons auflisten
    for key, info in templates.items():
        keyboard.append([InlineKeyboardButton(info["display_name"], callback_data=f"tpl:{key}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Wähle ein Meme-Template aus:",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet die Auswahl des Meme-Templates per Inline-Button."""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("tpl:"):
        template_key = data.split(":", 1)[1]
        chat_id = update.effective_chat.id
        
        # Zustand setzen
        clear_user_state(chat_id)
        update_user_state(chat_id, "active_template", template_key)
        update_user_state(chat_id, "state", "waiting_for_meme_text")
        
        await query.edit_message_text(
            text=f"Template <b>{template_key.replace('_', ' ').title()}</b> ausgewählt.",
            parse_mode="HTML"
        )
        # Tastatur unten auf "Abbrechen" ändern und nach Text fragen
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sende mir jetzt den Text für das Meme als normale Nachricht:",
            reply_markup=get_cancel_keyboard()
        )

async def message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Startet das Eintragen einer Nachricht mit dem gespeicherten Namen."""
    chat_id = update.effective_chat.id
    user_state = get_user_state(chat_id)
    saved_name = user_state.get("user_name")
    
    # Falls kein Name gesetzt ist, erst dazu auffordern
    if not saved_name:
        update_user_state(chat_id, "state", "waiting_for_name_setup")
        await update.message.reply_text(
            "Bevor du Nachrichten schreiben kannst, gib bitte deinen **Namen** ein:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return
        
    # Direktes Absenden per Argument
    if context.args:
        msg = " ".join(context.args).strip()
        if save_message_to_file(saved_name, msg, chat_id):
            await update.message.reply_text(
                f"Erfolgreich auf mil4n.de gespeichert!\n\n"
                f"**{saved_name}**: {msg}",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text("Fehler beim Speichern der Nachricht.", reply_markup=get_main_menu_keyboard())
        return
            
    # Geführter Dialog (Nachricht abfragen)
    clear_user_state(chat_id)
    update_user_state(chat_id, "state", "waiting_for_secret_msg")
    await update.message.reply_text(
        f"Du schreibst als **{saved_name}**.\n\n"
        "Gib nun deine **Nachricht** ein (oder klicke unten auf /cancel):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )

async def generate_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, template_key: str, text: str):
    """Generiert das Meme und schickt es zurück."""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("Generiere Meme... Bitte warten")
    
    try:
        output_file = create_meme(template_key, text)
        if not output_file or not output_file.exists():
            await status_msg.edit_text("Fehler beim Generieren des Memes.")
            await context.bot.send_message(chat_id=chat_id, text="Wähle eine Aktion aus:", reply_markup=get_main_menu_keyboard())
            return
            
        # Datei senden und Hauptmenü wieder anzeigen
        if is_video_file(output_file):
            with open(output_file, 'rb') as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=f"Meme: {text}",
                    reply_markup=get_main_menu_keyboard()
                )
        else:
            with open(output_file, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=f"Meme: {text}",
                    reply_markup=get_main_menu_keyboard()
                )
                
        # Statusmeldung löschen
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        
        # Lokale Datei löschen
        if output_file.exists():
            os.remove(output_file)
            
    except Exception as e:
        logger.error(f"Fehler beim Senden des Memes: {e}", exc_info=True)
        await status_msg.edit_text("Ein Fehler ist aufgetreten.")
        await context.bot.send_message(chat_id=chat_id, text="Wähle eine Aktion aus:", reply_markup=get_main_menu_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet eingehende Textnachrichten basierend auf dem aktuellen State."""
    chat_id = update.effective_chat.id
    text = update.message.text
    
    if not text or text.startswith('/'):
        return
        
    user_state = get_user_state(chat_id)
    state = user_state.get("state")
    
    if state == "waiting_for_name_setup":
        # Name speichern und bestätigen
        update_user_state(chat_id, "user_name", text)
        clear_user_state(chat_id)
        await update.message.reply_text(
            f"Sehr schön, **{text}**! Dein Name wurde gespeichert.\n\n"
            "Wähle unten eine Aktion aus dem Menü aus!",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        
    elif state == "waiting_for_name_change":
        # Name aktualisieren
        update_user_state(chat_id, "user_name", text)
        clear_user_state(chat_id)
        await update.message.reply_text(
            f"Dein Name wurde in **{text}** geändert.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        
    elif state == "waiting_for_meme_text":
        active_template = user_state.get("active_template")
        clear_user_state(chat_id)
        if active_template:
            await generate_and_send(update, context, active_template, text)
        else:
            await update.message.reply_text("Kein aktives Template gefunden. Nutze `/memegen` von vorn.", reply_markup=get_main_menu_keyboard())
            
    elif state == "waiting_for_secret_msg":
        # Nachricht speichern unter dem bereits gesetzten Namen
        name = user_state.get("user_name", "Anonym")
        clear_user_state(chat_id)
        if save_message_to_file(name, text, chat_id):
            await update.message.reply_text(
                f"Danke! Deine Nachricht wurde gespeichert und ist jetzt im 'secret' Tab auf mil4n.de sichtbar.\n\n"
                f"**{name}**: {text}",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text("Fehler beim Speichern der Nachricht.", reply_markup=get_main_menu_keyboard())
            
    else:
        # Falls kein aktiver Dialog läuft, prüfen wir ob einer der Menü-Buttons geklickt wurde:
        if text == "Meme Generator":
            await memegen_menu(update, context)
            return
        elif text == "Nachricht schreiben":
            await message_command(update, context)
            return
        elif text == "Name ändern":
            await changename_command(update, context)
            return
        elif text == "Letzte Nachricht löschen":
            await delete_last_message_command(update, context)
            return
        elif text == "Alle meine Nachrichten löschen":
            await delete_all_messages_command(update, context)
            return
            
        # Standard Fallback (Prüfen ob ein Name existiert)
        saved_name = user_state.get("user_name")
        if not saved_name:
            update_user_state(chat_id, "state", "waiting_for_name_setup")
            await update.message.reply_text(
                "Hallo ich bin Megamilan. Wie lautet dein Name?",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                f"Hallo {saved_name}!\n\n"
                "Wähle eine Aktion aus dem Menü unten aus oder nutze Slash-Commands.",
                reply_markup=get_main_menu_keyboard()
            )

async def delete_last_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Löscht die letzte Nachricht des aktuellen Nutzers."""
    chat_id = update.effective_chat.id
    success, removed_text = delete_last_message_from_file(chat_id)
    
    if success:
        await update.message.reply_text(
            f"Deine letzte Nachricht wurde von mil4n.de gelöscht.\n\n"
            f"**Gelöscht**: {removed_text}",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "Du hast keine Nachrichten auf mil4n.de gepostet, die gelöscht werden können.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )

async def delete_all_messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Löscht alle Nachrichten des aktuellen Nutzers."""
    chat_id = update.effective_chat.id
    success, count = delete_all_messages_from_file(chat_id)
    
    if success:
        await update.message.reply_text(
            f"Es wurden alle deine Nachrichten ({count}) von mil4n.de gelöscht.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "Es wurden keine Nachrichten von dir auf mil4n.de gefunden.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )

async def clear_all_messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Löscht absolut alle Nachrichten auf mil4n.de."""
    success = clear_entire_message_file()
    
    if success:
        await update.message.reply_text(
            "Der gesamte Chatverlauf auf mil4n.de wurde gelöscht.",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "Fehler beim Leeren des Chatverlaufs.",
            reply_markup=get_main_menu_keyboard()
        )

def run_hourly_cleanup():
    import time
    import datetime
    
    logger.info("Hourly cleanup thread started.")
    last_cleared_hour = -1
    
    while True:
        now = datetime.datetime.now()
        # Trigger at the top of the hour (minute 0)
        if now.minute == 0 and now.hour != last_cleared_hour:
            try:
                success = clear_entire_message_file()
                if success:
                    logger.info(f"Hourly cleanup: Cleared all messages at {now.strftime('%d.%m.%Y, %H:%M:%S')}")
                    last_cleared_hour = now.hour
                else:
                    logger.error("Hourly cleanup: Failed to clear messages.")
            except Exception as e:
                logger.error(f"Error during hourly cleanup: {e}")
        # Check every 10 seconds
        time.sleep(10)

def main():
    token = TELEGRAM_BOT_TOKEN
    if not token or token.startswith("YOUR_NEW_BOT_TOKEN"):
        logger.error("TELEGRAM_BOT_TOKEN in .env ist nicht gesetzt!")
        print("\n❌ Fehler: TELEGRAM_BOT_TOKEN ist nicht gesetzt!")
        print("Trage deinen Bot-Token in der Datei '.env' ein.\n")
        return

    # Start HTTP API Server for the website in a background thread
    threading.Thread(target=run_http_server, args=(5005,), daemon=True).start()
    
    # Start hourly cleanup thread
    threading.Thread(target=run_hourly_cleanup, daemon=True).start()

    application = ApplicationBuilder().token(token).build()
    
    # Commands registrieren
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', start))
    application.add_handler(CommandHandler('cancel', cancel))
    application.add_handler(CommandHandler('memegen', memegen_menu))
    application.add_handler(CommandHandler('templates', memegen_menu))
    application.add_handler(CommandHandler('list', memegen_menu))
    application.add_handler(CommandHandler('message', message_command))
    application.add_handler(CommandHandler('secret', message_command))
    application.add_handler(CommandHandler('changename', changename_command))
    application.add_handler(CommandHandler('deletelastmessage', delete_last_message_command))
    application.add_handler(CommandHandler('deleteallmessages', delete_all_messages_command))
    application.add_handler(CommandHandler('clearall', clear_all_messages_command))
    application.add_handler(CommandHandler('clearallmessages', clear_all_messages_command))
    
    # Callback query handler für das Inline-Meme-Menü
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Fallback-Nachrichten-Handler für Texteingaben
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    logger.info("Bot gestartet und wartet auf Updates...")
    application.run_polling()

if __name__ == "__main__":
    main()


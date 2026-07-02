import logging
import os
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters
)

# Import configurations and handlers
from config import TELEGRAM_BOT_TOKEN
from state_manager import (
    get_active_template,
    set_active_template,
    clear_active_template
)
from meme_handler import get_available_templates, create_meme, is_video_file

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start-Command: Begrüßung und Auflistung der Templates."""
    user = update.effective_user.first_name
    await update.message.reply_text(
        f"Hallo {user}! Ich bin dein Meme-Generator Bot. 🎬🎨\n\n"
        "Wähle ein Template mit einem Command aus und sende mir danach den Text.\n"
        "Oder schreibe den Text direkt hinter den Command, z.B.: `/vintage_vibe Mein Text`.\n\n"
        "Nutze `/templates` um alle verfügbaren Templates zu sehen.\n"
        "Nutze `/cancel` um die aktuelle Auswahl abzubrechen."
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bricht die aktuelle Template-Auswahl ab."""
    chat_id = update.effective_chat.id
    active = get_active_template(chat_id)
    if active:
        clear_active_template(chat_id)
        await update.message.reply_text(f"Auswahl für '{active}' abgebrochen.")
    else:
        await update.message.reply_text("Keine aktive Template-Auswahl vorhanden.")

async def list_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listet alle registrierten Meme-Templates auf."""
    templates = get_available_templates()
    if not templates:
        await update.message.reply_text("Keine Templates im `templates/` Ordner gefunden.")
        return
        
    lines = ["Verfügbare Meme Templates:"]
    for key, info in templates.items():
        # Zeige Commands mit und ohne Underscore
        cmd1 = f"/{key}"
        cmd2 = f"/{key.replace('_', '')}"
        lines.append(f"• <b>{info['display_name']}</b> ({info['type']}):\n  👉 {cmd1} oder {cmd2}")
        
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def generate_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, template_key: str, text: str):
    """Generiert das Meme und schickt es zurück."""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("Generiere Meme... Bitte warten ⏳")
    
    try:
        output_file = create_meme(template_key, text)
        if not output_file or not output_file.exists():
            await status_msg.edit_text("❌ Fehler beim Generieren des Memes.")
            return
            
        # Datei senden
        if is_video_file(output_file):
            with open(output_file, 'rb') as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=f"Meme: {text}"
                )
        else:
            with open(output_file, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=f"Meme: {text}"
                )
                
        # Statusmeldung löschen
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        
        # Lokale Datei löschen
        if output_file.exists():
            os.remove(output_file)
            
    except Exception as e:
        logger.error(f"Fehler beim Senden des Memes: {e}", exc_info=True)
        await status_msg.edit_text("❌ Ein Fehler ist aufgetreten.")

def make_template_command(template_key: str):
    """Erstellt dynamisch einen Handler für ein bestimmtes Template."""
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if context.args:
            # Command mit Text direkt: /vintagevibe mein text
            text = " ".join(context.args)
            await generate_and_send(update, context, template_key, text)
        else:
            # Nur Command: Auswahl speichern und auf Nachricht warten
            set_active_template(chat_id, template_key)
            await update.message.reply_text(
                f"Template <b>{template_key.replace('_', ' ').title()}</b> ausgewählt.\n"
                "Sende mir jetzt den Text für das Meme als normale Nachricht.",
                parse_mode="HTML"
            )
    return handler

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet eingehende Textnachrichten, wenn ein Template ausgewählt ist."""
    chat_id = update.effective_chat.id
    text = update.message.text
    
    if not text or text.startswith('/'):
        return
        
    active_template = get_active_template(chat_id)
    if active_template:
        # Template-Auswahl zurücksetzen (One-Off Flow)
        clear_active_template(chat_id)
        await generate_and_send(update, context, active_template, text)
    else:
        # Kein aktives Template: Info an den User senden
        await update.message.reply_text(
            "Bitte wähle zuerst ein Meme-Template aus, z.B. mit `/vintage_vibe`.\n"
            "Nutze `/templates` für eine Liste aller Templates."
        )

def main():
    token = TELEGRAM_BOT_TOKEN
    if not token or token.startswith("YOUR_NEW_BOT_TOKEN"):
        logger.error("TELEGRAM_BOT_TOKEN in .env ist nicht gesetzt!")
        print("\n❌ Fehler: TELEGRAM_BOT_TOKEN ist nicht gesetzt!")
        print("Trage deinen Bot-Token in der Datei '.env' ein.\n")
        return

    application = ApplicationBuilder().token(token).build()
    
    # Standard-Befehle
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('cancel', cancel))
    application.add_handler(CommandHandler('templates', list_templates))
    application.add_handler(CommandHandler('list', list_templates))
    
    # Dynamische Template-Befehle registrieren
    templates = get_available_templates()
    for key in templates:
        # Registriere beide Varianten (z.B. /vintage_vibe und /vintagevibe)
        keys_to_register = {key, key.replace('_', '')}
        for k in keys_to_register:
            application.add_handler(CommandHandler(k, make_template_command(key)))
            logger.info(f"Command registered: /{k}")

    # Fallback-Nachrichten-Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    logger.info("Bot gestartet und wartet auf Updates...")
    application.run_polling()

if __name__ == "__main__":
    main()

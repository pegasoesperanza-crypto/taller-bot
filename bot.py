import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore
import json
import random
import string

# ── Configuración ──────────────────────────────────────────────────
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID"))
FIREBASE_CREDS = os.environ.get("FIREBASE_CREDENTIALS")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Firebase ────────────────────────────────────────────────────────
cred_dict = json.loads(FIREBASE_CREDS)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ── Helpers ─────────────────────────────────────────────────────────
def gen_id():
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"{ts}_{rand}"

def today():
    return datetime.now().strftime("%Y-%m-%d")

def fmt(n):
    return f"${n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def es_admin(update: Update) -> bool:
    return update.effective_chat.id == ADMIN_CHAT_ID

def get_proyectos_activos():
    docs = db.collection("proyectos").where("estado", "==", "En curso").stream()
    return [d.to_dict() for d in docs]

def get_resumen_mes():
    ahora = datetime.now()
    mes = ahora.month
    anio = ahora.year
    
    ingresos = db.collection("ingresos").stream()
    egresos = db.collection("egresos").stream()
    
    total_ing = 0
    total_egr = 0
    
    for doc in ingresos:
        d = doc.to_dict()
        fecha = d.get("fecha", "")
        if fecha:
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            if dt.month == mes and dt.year == anio:
                total_ing += d.get("monto", 0)
    
    for doc in egresos:
        d = doc.to_dict()
        fecha = d.get("fecha", "")
        if fecha:
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            if dt.month == mes and dt.year == anio:
                total_egr += d.get("monto", 0)
    
    return total_ing, total_egr

# ── Comandos ────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        await update.message.reply_text("⛔ No tenés acceso a este bot.")
        return
    
    texto = (
        "🔧 *Bot Taller Metalúrgico*\n\n"
        "Comandos disponibles:\n\n"
        "💸 `/egreso MONTO PROVEEDOR DESCRIPCION`\n"
        "Ej: `/egreso 45000 YPF combustible`\n\n"
        "💰 `/ingreso MONTO CLIENTE DESCRIPCION`\n"
        "Ej: `/ingreso 150000 García seña galpón`\n\n"
        "📋 `/proyectos` — Ver proyectos activos\n\n"
        "📊 `/saldo` — Resumen del mes actual\n\n"
        "🧾 Mandá una *foto* de una factura con el monto en el caption\n"
        "Ej: foto + caption `45000 YPF combustible`"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def cmd_egreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        await update.message.reply_text("⛔ No tenés acceso.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Formato incorrecto.\n\nUsá: `/egreso MONTO PROVEEDOR DESCRIPCION`\nEj: `/egreso 45000 YPF combustible`",
            parse_mode="Markdown"
        )
        return
    
    try:
        monto = float(args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ El monto debe ser un número. Ej: `45000`", parse_mode="Markdown")
        return
    
    proveedor = args[1]
    descripcion = " ".join(args[2:]) if len(args) > 2 else ""
    
    item = {
        "id": gen_id(),
        "fecha": today(),
        "proveedor": proveedor,
        "factura": "",
        "sinFactura": True,
        "tipogasto": "Gastos administrativos",
        "proyecto": "",
        "pago": "Efectivo",
        "monto": monto,
        "obs": descripcion + " [vía Telegram]",
        "vencimiento": "",
        "pagadoCC": 0
    }
    
    db.collection("egresos").document(item["id"]).set(item)
    
    respuesta = (
        f"✅ *Egreso registrado*\n\n"
        f"📅 Fecha: {today()}\n"
        f"🏢 Proveedor: {proveedor}\n"
        f"💸 Monto: {fmt(monto)}\n"
        f"📝 Descripción: {descripcion or '—'}\n\n"
        f"_Aparece en la app como sin factura._"
    )
    await update.message.reply_text(respuesta, parse_mode="Markdown")

async def cmd_ingreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        await update.message.reply_text("⛔ No tenés acceso.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Formato incorrecto.\n\nUsá: `/ingreso MONTO CLIENTE DESCRIPCION`\nEj: `/ingreso 150000 García seña galpón`",
            parse_mode="Markdown"
        )
        return
    
    try:
        monto = float(args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ El monto debe ser un número. Ej: `150000`", parse_mode="Markdown")
        return
    
    cliente = args[1]
    descripcion = " ".join(args[2:]) if len(args) > 2 else ""
    
    item = {
        "id": gen_id(),
        "fecha": today(),
        "cliente": cliente,
        "factura": "",
        "sinFactura": True,
        "proyecto": "",
        "tipo": "Metalúrgica",
        "pago": "Efectivo",
        "monto": monto,
        "obs": descripcion + " [vía Telegram]",
        "cheque": {}
    }
    
    db.collection("ingresos").document(item["id"]).set(item)
    
    respuesta = (
        f"✅ *Ingreso registrado*\n\n"
        f"📅 Fecha: {today()}\n"
        f"👤 Cliente: {cliente}\n"
        f"💰 Monto: {fmt(monto)}\n"
        f"📝 Descripción: {descripcion or '—'}\n\n"
        f"_Aparece en la app como sin factura._"
    )
    await update.message.reply_text(respuesta, parse_mode="Markdown")

async def cmd_proyectos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        await update.message.reply_text("⛔ No tenés acceso.")
        return
    
    proyectos = get_proyectos_activos()
    
    if not proyectos:
        await update.message.reply_text("📋 No hay proyectos activos en este momento.")
        return
    
    texto = "📋 *Proyectos activos*\n\n"
    for p in proyectos:
        venta = p.get("venta", 0)
        texto += f"🏗️ *{p.get('nombre', '—')}*\n"
        texto += f"   👤 {p.get('cliente', '—')} · {p.get('tipo', '—')}\n"
        texto += f"   💰 Venta: {fmt(venta)}\n"
        texto += f"   📅 Inicio: {p.get('finicio', '—')}\n\n"
    
    await update.message.reply_text(texto, parse_mode="Markdown")

async def cmd_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        await update.message.reply_text("⛔ No tenés acceso.")
        return
    
    total_ing, total_egr = get_resumen_mes()
    resultado = total_ing - total_egr
    ahora = datetime.now()
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    mes_nombre = meses[ahora.month - 1]
    
    signo = "+" if resultado >= 0 else ""
    emoji = "🟢" if resultado >= 0 else "🔴"
    
    texto = (
        f"📊 *Resumen {mes_nombre.capitalize()} {ahora.year}*\n\n"
        f"💰 Ingresos: {fmt(total_ing)}\n"
        f"💸 Egresos: {fmt(total_egr)}\n"
        f"{'─'*25}\n"
        f"{emoji} Resultado: {signo}{fmt(resultado)}"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def handle_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        await update.message.reply_text("⛔ No tenés acceso.")
        return
    
    caption = update.message.caption or ""
    foto = update.message.photo[-1]
    file_id = foto.file_id
    
    # Intentar parsear monto del caption
    monto = 0
    proveedor = "Sin especificar"
    descripcion = ""
    
    partes = caption.strip().split()
    if partes:
        try:
            monto = float(partes[0].replace(",", "."))
            if len(partes) > 1:
                proveedor = partes[1]
            if len(partes) > 2:
                descripcion = " ".join(partes[2:])
        except ValueError:
            descripcion = caption
    
    item = {
        "id": gen_id(),
        "fecha": today(),
        "proveedor": proveedor,
        "factura": "",
        "sinFactura": False,
        "tipogasto": "Gastos administrativos",
        "proyecto": "",
        "pago": "Efectivo",
        "monto": monto,
        "obs": f"{descripcion} [foto factura Telegram, file_id: {file_id}]",
        "vencimiento": "",
        "pagadoCC": 0,
        "telegramFileId": file_id
    }
    
    db.collection("egresos").document(item["id"]).set(item)
    
    if monto > 0:
        respuesta = (
            f"🧾 *Factura registrada*\n\n"
            f"📅 Fecha: {today()}\n"
            f"🏢 Proveedor: {proveedor}\n"
            f"💸 Monto: {fmt(monto)}\n"
            f"📝 {descripcion or '—'}\n\n"
            f"_Podés editar los detalles desde la app._"
        )
    else:
        respuesta = (
            f"🧾 *Foto de factura guardada*\n\n"
            f"No detecté el monto automáticamente.\n"
            f"Podés completar los datos desde la app.\n\n"
            f"_Tip: mandá la foto con caption así:_\n`45000 YPF combustible`"
        )
    
    await update.message.reply_text(respuesta, parse_mode="Markdown")

async def handle_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update):
        return
    await update.message.reply_text(
        "No entendí ese mensaje. Usá los comandos:\n\n"
        "/egreso · /ingreso · /proyectos · /saldo\n\n"
        "O mandá /start para ver la ayuda completa."
    )

# ── Main ────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("egreso", cmd_egreso))
    app.add_handler(CommandHandler("ingreso", cmd_ingreso))
    app.add_handler(CommandHandler("proyectos", cmd_proyectos))
    app.add_handler(CommandHandler("saldo", cmd_saldo))
    app.add_handler(MessageHandler(filters.PHOTO, handle_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_texto))
    
    logger.info("Bot iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

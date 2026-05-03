import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import firebase_admin
from firebase_admin import credentials, firestore
import json
import random
import string

TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID"))
FIREBASE_CREDS = os.environ.get("FIREBASE_CREDENTIALS")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cred_dict = json.loads(FIREBASE_CREDS)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

ING_CLIENTE, ING_FACTURA, ING_PROYECTO, ING_TIPO, ING_FORMA_PAGO, ING_MONTO, ING_OBS = range(7)
EGR_PROVEEDOR, EGR_FACTURA, EGR_TIPO_GASTO, EGR_PROYECTO, EGR_FORMA_PAGO, EGR_MONTO, EGR_OBS = range(10, 17)
CANCELAR = "❌ Cancelar"

def gen_id():
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return ts + '_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))

def today():
    return datetime.now().strftime("%Y-%m-%d")

def fmt(n):
    try:
        return "${:,.2f}".format(float(n)).replace(",","X").replace(".",",").replace("X",".")
    except:
        return str(n)

def es_admin(update):
    return update.effective_chat.id == ADMIN_CHAT_ID

def kb(opciones, cols=2):
    filas = []
    for i in range(0, len(opciones), cols):
        filas.append(opciones[i:i+cols])
    filas.append([CANCELAR])
    return ReplyKeyboardMarkup(filas, resize_keyboard=True, one_time_keyboard=True)

def get_clientes():
    return [d.to_dict().get("nombre","") for d in db.collection("clientes").stream() if d.to_dict().get("nombre")]

def get_proveedores():
    return [d.to_dict().get("nombre","") for d in db.collection("proveedores").stream() if d.to_dict().get("nombre")]

def get_proyectos():
    return [d.to_dict().get("nombre","") for d in db.collection("proyectos").where("estado","==","En curso").stream() if d.to_dict().get("nombre")]

def get_resumen_mes():
    ahora = datetime.now()
    mes, anio = ahora.month, ahora.year
    ti = te = 0
    for doc in db.collection("ingresos").stream():
        d = doc.to_dict()
        f = d.get("fecha","")
        if f and datetime.strptime(f,"%Y-%m-%d").month==mes and datetime.strptime(f,"%Y-%m-%d").year==anio:
            ti += d.get("monto",0)
    for doc in db.collection("egresos").stream():
        d = doc.to_dict()
        f = d.get("fecha","")
        if f and datetime.strptime(f,"%Y-%m-%d").month==mes and datetime.strptime(f,"%Y-%m-%d").year==anio:
            te += d.get("monto",0)
    return ti, te

async def start(update, context):
    if not es_admin(update): return
    await update.message.reply_text(
        "🔧 *Bot Taller Metalúrgico*\n\n"
        "💰 /ingreso — Registrar un ingreso\n"
        "💸 /egreso — Registrar un egreso\n"
        "📋 /proyectos — Ver proyectos activos\n"
        "📊 /saldo — Resumen del mes\n"
        "❌ /cancelar — Cancelar operación en curso",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

async def ing_start(update, context):
    if not es_admin(update): return ConversationHandler.END
    context.user_data.clear()
    clientes = get_clientes()
    await update.message.reply_text(
        "💰 *Nuevo ingreso*\n\n👤 ¿*Cliente*?",
        parse_mode="Markdown",
        reply_markup=kb(clientes) if clientes else ReplyKeyboardRemove()
    )
    return ING_CLIENTE

async def ing_cliente(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['cliente'] = update.message.text.strip()
    await update.message.reply_text(
        "🧾 ¿*N° de factura*?\n_(escribí `sf` para sin factura)_",
        parse_mode="Markdown", reply_markup=kb(["sf"])
    )
    return ING_FACTURA

async def ing_factura(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['factura'] = "" if txt.lower()=="sf" else txt
    context.user_data['sin_factura'] = txt.lower()=="sf"
    proyectos = get_proyectos()
    await update.message.reply_text(
        "🏗️ ¿*Proyecto*?\n_(o `no` para omitir)_",
        parse_mode="Markdown",
        reply_markup=kb(proyectos+["no"],cols=1) if proyectos else kb(["no"],cols=1)
    )
    return ING_PROYECTO

async def ing_proyecto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['proyecto'] = "" if txt.lower() in ["no","sin proyecto"] else txt
    await update.message.reply_text(
        "⚙️ ¿*Tipo de trabajo*?",
        parse_mode="Markdown",
        reply_markup=kb(["Ingeniería","Metalúrgica","Mantenimiento"])
    )
    return ING_TIPO

async def ing_tipo(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['tipo'] = update.message.text.strip()
    await update.message.reply_text(
        "💳 ¿*Forma de cobro*?",
        parse_mode="Markdown",
        reply_markup=kb(["Efectivo","Transferencia","Cheque"])
    )
    return ING_FORMA_PAGO

async def ing_forma_pago(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['pago'] = update.message.text.strip()
    await update.message.reply_text(
        "💵 ¿*Monto* en pesos?",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return ING_MONTO

async def ing_monto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    try:
        monto = float(update.message.text.strip().replace(".","").replace(",","."))
    except:
        await update.message.reply_text("❌ Ingresá solo el número, ej: `150000`", parse_mode="Markdown")
        return ING_MONTO
    context.user_data['monto'] = monto
    await update.message.reply_text(
        "📝 ¿*Observación*?\n_(o `no` para omitir)_",
        parse_mode="Markdown", reply_markup=kb(["no"])
    )
    return ING_OBS

async def ing_obs(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    d = context.user_data
    d['obs'] = "" if txt.lower()=="no" else txt
    item = {
        "id": gen_id(), "fecha": today(),
        "cliente": d.get('cliente',''), "factura": d.get('factura',''),
        "sinFactura": d.get('sin_factura',False), "proyecto": d.get('proyecto',''),
        "tipo": d.get('tipo','Metalúrgica'), "pago": d.get('pago','Efectivo'),
        "monto": d.get('monto',0), "obs": d.get('obs','')+" [Telegram]", "cheque": {}
    }
    db.collection("ingresos").document(item["id"]).set(item)
    await update.message.reply_text(
        f"✅ *Ingreso registrado*\n\n"
        f"📅 {today()} | 👤 {item['cliente']}\n"
        f"🧾 {'Sin factura' if item['sinFactura'] else item['factura'] or '—'}\n"
        f"🏗️ {item['proyecto'] or '—'} | ⚙️ {item['tipo']}\n"
        f"💳 {item['pago']} | 💰 {fmt(item['monto'])}",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def egr_start(update, context):
    if not es_admin(update): return ConversationHandler.END
    context.user_data.clear()
    proveedores = get_proveedores()
    await update.message.reply_text(
        "💸 *Nuevo egreso*\n\n🏢 ¿*Proveedor*?\n_(o `no` si no aplica)_",
        parse_mode="Markdown",
        reply_markup=kb(proveedores+["no"],cols=1) if proveedores else kb(["no"],cols=1)
    )
    return EGR_PROVEEDOR

async def egr_proveedor(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['proveedor'] = "" if txt.lower()=="no" else txt
    await update.message.reply_text(
        "🧾 ¿*N° de factura*?\n_(o `sf` para sin factura)_",
        parse_mode="Markdown", reply_markup=kb(["sf"])
    )
    return EGR_FACTURA

async def egr_factura(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['factura'] = "" if txt.lower()=="sf" else txt
    context.user_data['sin_factura'] = txt.lower()=="sf"
    await update.message.reply_text(
        "📂 ¿*Tipo de gasto*?",
        parse_mode="Markdown",
        reply_markup=kb(["Gastos administrativos","Sueldos","Mano de obra",
                         "Retiros personales","Compra de insumos","Compra de materia prima"],cols=1)
    )
    return EGR_TIPO_GASTO

async def egr_tipo_gasto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['tipogasto'] = update.message.text.strip()
    proyectos = get_proyectos()
    await update.message.reply_text(
        "🏗️ ¿*Proyecto*?\n_(o `no` para omitir)_",
        parse_mode="Markdown",
        reply_markup=kb(proyectos+["no"],cols=1) if proyectos else kb(["no"],cols=1)
    )
    return EGR_PROYECTO

async def egr_proyecto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['proyecto'] = "" if txt.lower() in ["no","sin proyecto"] else txt
    await update.message.reply_text(
        "💳 ¿*Forma de pago*?",
        parse_mode="Markdown",
        reply_markup=kb(["Efectivo","Transferencia","Tarjeta de crédito",
                         "Cuenta corriente","Cheque propio","Cheque de terceros"],cols=2)
    )
    return EGR_FORMA_PAGO

async def egr_forma_pago(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['pago'] = update.message.text.strip()
    await update.message.reply_text(
        "💵 ¿*Monto* en pesos?",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return EGR_MONTO

async def egr_monto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    try:
        monto = float(update.message.text.strip().replace(".","").replace(",","."))
    except:
        await update.message.reply_text("❌ Ingresá solo el número, ej: `45000`", parse_mode="Markdown")
        return EGR_MONTO
    context.user_data['monto'] = monto
    await update.message.reply_text(
        "📝 ¿*Observación*?\n_(o `no` para omitir)_",
        parse_mode="Markdown", reply_markup=kb(["no"])
    )
    return EGR_OBS

async def egr_obs(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    d = context.user_data
    d['obs'] = "" if txt.lower()=="no" else txt
    item = {
        "id": gen_id(), "fecha": today(),
        "proveedor": d.get('proveedor',''), "factura": d.get('factura',''),
        "sinFactura": d.get('sin_factura',False), "tipogasto": d.get('tipogasto','Gastos administrativos'),
        "proyecto": d.get('proyecto',''), "pago": d.get('pago','Efectivo'),
        "monto": d.get('monto',0), "obs": d.get('obs','')+" [Telegram]",
        "vencimiento": "", "pagadoCC": 0
    }
    db.collection("egresos").document(item["id"]).set(item)
    await update.message.reply_text(
        f"✅ *Egreso registrado*\n\n"
        f"📅 {today()} | 🏢 {item['proveedor'] or '—'}\n"
        f"🧾 {'Sin factura' if item['sinFactura'] else item['factura'] or '—'}\n"
        f"📂 {item['tipogasto']} | 🏗️ {item['proyecto'] or '—'}\n"
        f"💳 {item['pago']} | 💸 {fmt(item['monto'])}",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cmd_proyectos(update, context):
    if not es_admin(update): return
    proyectos = [d.to_dict() for d in db.collection("proyectos").where("estado","==","En curso").stream()]
    if not proyectos:
        await update.message.reply_text("📋 No hay proyectos activos.")
        return
    texto = "📋 *Proyectos activos*\n\n"
    for p in proyectos:
        texto += f"🏗️ *{p.get('nombre','—')}*\n   👤 {p.get('cliente','—')} · {p.get('tipo','—')}\n   💰 {fmt(p.get('venta',0))}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

async def cmd_saldo(update, context):
    if not es_admin(update): return
    ti, te = get_resumen_mes()
    res = ti - te
    ahora = datetime.now()
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    await update.message.reply_text(
        f"📊 *{meses[ahora.month-1].capitalize()} {ahora.year}*\n\n"
        f"💰 Ingresos: {fmt(ti)}\n💸 Egresos: {fmt(te)}\n"
        f"{'─'*20}\n{'🟢' if res>=0 else '🔴'} Resultado: {'+'if res>=0 else ''}{fmt(res)}",
        parse_mode="Markdown"
    )

async def handle_foto(update, context):
    if not es_admin(update): return
    caption = update.message.caption or ""
    foto = update.message.photo[-1]
    file_id = foto.file_id
    monto, proveedor, descripcion = 0, "Sin especificar", ""
    partes = caption.strip().split()
    if partes:
        try:
            monto = float(partes[0].replace(",","."))
            if len(partes)>1: proveedor = partes[1]
            if len(partes)>2: descripcion = " ".join(partes[2:])
        except:
            descripcion = caption
    item = {
        "id": gen_id(), "fecha": today(), "proveedor": proveedor,
        "factura": "", "sinFactura": False, "tipogasto": "Gastos administrativos",
        "proyecto": "", "pago": "Efectivo", "monto": monto,
        "obs": f"{descripcion} [foto Telegram id:{file_id}]",
        "vencimiento": "", "pagadoCC": 0
    }
    db.collection("egresos").document(item["id"]).set(item)
    if monto > 0:
        resp = f"🧾 *Factura guardada*\n📅 {today()} | 🏢 {proveedor} | 💸 {fmt(monto)}\n_Editá los detalles desde la app._"
    else:
        resp = "🧾 *Foto guardada*\nNo detecté el monto.\n_Tip: `45000 YPF combustible`_"
    await update.message.reply_text(resp, parse_mode="Markdown")

async def handle_texto(update, context):
    if not es_admin(update): return
    await update.message.reply_text(
        "No entendí ese mensaje.\n\n/ingreso · /egreso · /proyectos · /saldo",
        reply_markup=ReplyKeyboardRemove()
    )

def main():
    app = Application.builder().token(TOKEN).build()

    conv_ingreso = ConversationHandler(
        entry_points=[CommandHandler("ingreso", ing_start)],
        states={
            ING_CLIENTE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_cliente)],
            ING_FACTURA:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_factura)],
            ING_PROYECTO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_proyecto)],
            ING_TIPO:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_tipo)],
            ING_FORMA_PAGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_forma_pago)],
            ING_MONTO:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_monto)],
            ING_OBS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_obs)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    conv_egreso = ConversationHandler(
        entry_points=[CommandHandler("egreso", egr_start)],
        states={
            EGR_PROVEEDOR:  [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_proveedor)],
            EGR_FACTURA:    [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_factura)],
            EGR_TIPO_GASTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_tipo_gasto)],
            EGR_PROYECTO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_proyecto)],
            EGR_FORMA_PAGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_forma_pago)],
            EGR_MONTO:      [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_monto)],
            EGR_OBS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, egr_obs)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("proyectos", cmd_proyectos))
    app.add_handler(CommandHandler("saldo", cmd_saldo))
    app.add_handler(conv_ingreso)
    app.add_handler(conv_egreso)
    app.add_handler(MessageHandler(filters.PHOTO, handle_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_texto))

    logger.info("Bot iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

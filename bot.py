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

# ── Estados conversación ────────────────────────────────────────────
ING_CLIENTE, ING_FACTURA, ING_PROYECTO, ING_TIPO, ING_FORMA_PAGO, ING_MONTO, ING_OBS = range(7)
EGR_PROVEEDOR, EGR_FACTURA, EGR_TIPO_GASTO, EGR_PROYECTO, EGR_FORMA_PAGO, EGR_MONTO, EGR_OBS = range(10, 17)
SUELDO_EMP, SUELDO_PERIODO, SUELDO_MONTO, SUELDO_OBS = range(20, 24)
PROY_NOMBRE, PROY_CLIENTE, PROY_TIPO, PROY_VENTA, PROY_OBS_P = range(30, 35)
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

def get_empleados():
    return [d.to_dict() for d in db.collection("empleados").stream() if d.to_dict().get("nombre")]

def get_resumen_mes():
    ahora = datetime.now()
    mes, anio = ahora.month, ahora.year
    ti = te = 0
    for doc in db.collection("ingresos").stream():
        d = doc.to_dict()
        f = d.get("fecha","")
        if f:
            try:
                dt = datetime.strptime(f,"%Y-%m-%d")
                if dt.month==mes and dt.year==anio: ti += d.get("monto",0)
            except: pass
    for doc in db.collection("egresos").stream():
        d = doc.to_dict()
        f = d.get("fecha","")
        if f:
            try:
                dt = datetime.strptime(f,"%Y-%m-%d")
                if dt.month==mes and dt.year==anio: te += d.get("monto",0)
            except: pass
    return ti, te

# ── /start ──────────────────────────────────────────────────────────
async def start(update, context):
    if not es_admin(update): return
    await update.message.reply_text(
        "🔧 *Bot Taller Metalúrgico — PEGASO*\n\n"
        "💰 /ingreso — Registrar un ingreso\n"
        "💸 /egreso — Registrar un egreso\n"
        "👷 /sueldo — Registrar pago de sueldo\n"
        "🏗️ /proyecto — Crear nuevo proyecto\n"
        "📋 /proyectos — Ver proyectos activos\n"
        "📊 /saldo — Resumen del mes\n"
        "❌ /cancelar — Cancelar operación en curso",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

# ── INGRESO ─────────────────────────────────────────────────────────
async def ing_start(update, context):
    if not es_admin(update): return ConversationHandler.END
    context.user_data.clear()
    clientes = get_clientes()
    await update.message.reply_text(
        "💰 *Nuevo ingreso*\n\n👤 ¿Cliente?",
        parse_mode="Markdown",
        reply_markup=kb(clientes) if clientes else ReplyKeyboardRemove()
    )
    return ING_CLIENTE

async def ing_cliente(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['cliente'] = update.message.text.strip()
    await update.message.reply_text("🧾 ¿N° de factura?\n_(escribí `sf` para sin factura)_",
        parse_mode="Markdown", reply_markup=kb(["sf"]))
    return ING_FACTURA

async def ing_factura(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['factura'] = "" if txt.lower()=="sf" else txt
    context.user_data['sin_factura'] = txt.lower()=="sf"
    proyectos = get_proyectos()
    await update.message.reply_text("🏗️ ¿Proyecto?\n_(o `no` para omitir)_",
        parse_mode="Markdown",
        reply_markup=kb(proyectos+["no"],cols=1) if proyectos else kb(["no"],cols=1))
    return ING_PROYECTO

async def ing_proyecto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['proyecto'] = "" if txt.lower() in ["no","sin proyecto"] else txt
    await update.message.reply_text("⚙️ ¿Tipo de trabajo?", parse_mode="Markdown",
        reply_markup=kb(["Ingeniería","Metalúrgica","Mantenimiento"]))
    return ING_TIPO

async def ing_tipo(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['tipo'] = update.message.text.strip()
    await update.message.reply_text("💳 ¿Forma de cobro?", parse_mode="Markdown",
        reply_markup=kb(["Efectivo","Transferencia","Cheque"]))
    return ING_FORMA_PAGO

async def ing_forma_pago(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['pago'] = update.message.text.strip()
    await update.message.reply_text("💵 ¿Monto en pesos?", parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove())
    return ING_MONTO

async def ing_monto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    try: monto = float(update.message.text.strip().replace(".","").replace(",","."))
    except:
        await update.message.reply_text("❌ Ingresá solo el número, ej: `150000`", parse_mode="Markdown")
        return ING_MONTO
    context.user_data['monto'] = monto
    await update.message.reply_text("📝 ¿Observación?\n_(o `no`)_", parse_mode="Markdown", reply_markup=kb(["no"]))
    return ING_OBS

async def ing_obs(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    d = context.user_data
    d['obs'] = "" if txt.lower()=="no" else txt
    item = {"id":gen_id(),"fecha":today(),"cliente":d.get('cliente',''),
        "factura":d.get('factura',''),"sinFactura":d.get('sin_factura',False),
        "proyecto":d.get('proyecto',''),"tipo":d.get('tipo','Metalúrgica'),
        "pago":d.get('pago','Efectivo'),"monto":d.get('monto',0),
        "obs":d.get('obs','')+" [Telegram]","cheque":{}}
    db.collection("ingresos").document(item["id"]).set(item)
    await update.message.reply_text(
        f"✅ *Ingreso registrado*\n\n"
        f"📅 {today()} | 👤 {item['cliente']}\n"
        f"🧾 {'Sin factura' if item['sinFactura'] else item['factura'] or '—'}\n"
        f"🏗️ {item['proyecto'] or '—'} | ⚙️ {item['tipo']}\n"
        f"💳 {item['pago']} | 💰 {fmt(item['monto'])}",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ── EGRESO ──────────────────────────────────────────────────────────
async def egr_start(update, context):
    if not es_admin(update): return ConversationHandler.END
    context.user_data.clear()
    proveedores = get_proveedores()
    await update.message.reply_text(
        "💸 *Nuevo egreso*\n\n🏢 ¿Proveedor?\n_(o `no` si no aplica)_",
        parse_mode="Markdown",
        reply_markup=kb(proveedores+["no"],cols=1) if proveedores else kb(["no"],cols=1))
    return EGR_PROVEEDOR

async def egr_proveedor(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['proveedor'] = "" if txt.lower()=="no" else txt
    await update.message.reply_text("🧾 ¿N° de factura?\n_(o `sf` para sin factura)_",
        parse_mode="Markdown", reply_markup=kb(["sf"]))
    return EGR_FACTURA

async def egr_factura(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['factura'] = "" if txt.lower()=="sf" else txt
    context.user_data['sin_factura'] = txt.lower()=="sf"
    await update.message.reply_text("📂 ¿Tipo de gasto?", parse_mode="Markdown",
        reply_markup=kb(["Gastos administrativos","Sueldos","Mano de obra",
                         "Retiros personales","Compra de insumos","Compra de materia prima"],cols=1))
    return EGR_TIPO_GASTO

async def egr_tipo_gasto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['tipogasto'] = update.message.text.strip()
    proyectos = get_proyectos()
    await update.message.reply_text("🏗️ ¿Proyecto?\n_(o `no`)_", parse_mode="Markdown",
        reply_markup=kb(proyectos+["no"],cols=1) if proyectos else kb(["no"],cols=1))
    return EGR_PROYECTO

async def egr_proyecto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    context.user_data['proyecto'] = "" if txt.lower() in ["no","sin proyecto"] else txt
    await update.message.reply_text("💳 ¿Forma de pago?", parse_mode="Markdown",
        reply_markup=kb(["Efectivo","Transferencia","Tarjeta de crédito",
                         "Cuenta corriente","Cheque propio","Cheque de terceros"],cols=2))
    return EGR_FORMA_PAGO

async def egr_forma_pago(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['pago'] = update.message.text.strip()
    await update.message.reply_text("💵 ¿Monto en pesos?", parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove())
    return EGR_MONTO

async def egr_monto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    try: monto = float(update.message.text.strip().replace(".","").replace(",","."))
    except:
        await update.message.reply_text("❌ Ingresá solo el número, ej: `45000`", parse_mode="Markdown")
        return EGR_MONTO
    context.user_data['monto'] = monto
    await update.message.reply_text("📝 ¿Observación?\n_(o `no`)_", parse_mode="Markdown", reply_markup=kb(["no"]))
    return EGR_OBS

async def egr_obs(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    d = context.user_data
    d['obs'] = "" if txt.lower()=="no" else txt
    item = {"id":gen_id(),"fecha":today(),"proveedor":d.get('proveedor',''),
        "empleado":"","factura":d.get('factura',''),"sinFactura":d.get('sin_factura',False),
        "tipogasto":d.get('tipogasto','Gastos administrativos'),
        "proyecto":d.get('proyecto',''),"pago":d.get('pago','Efectivo'),
        "monto":d.get('monto',0),"obs":d.get('obs','')+" [Telegram]",
        "vencimiento":"","pagadoCC":0}
    db.collection("egresos").document(item["id"]).set(item)
    await update.message.reply_text(
        f"✅ *Egreso registrado*\n\n"
        f"📅 {today()} | 🏢 {item['proveedor'] or '—'}\n"
        f"🧾 {'Sin factura' if item['sinFactura'] else item['factura'] or '—'}\n"
        f"📂 {item['tipogasto']} | 🏗️ {item['proyecto'] or '—'}\n"
        f"💳 {item['pago']} | 💸 {fmt(item['monto'])}",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ── SUELDO ──────────────────────────────────────────────────────────
async def sueldo_start(update, context):
    if not es_admin(update): return ConversationHandler.END
    context.user_data.clear()
    context.user_data['tipo_op'] = 'sueldo'
    empleados = get_empleados()
    if not empleados:
        await update.message.reply_text("❌ No hay empleados registrados en el sistema.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    nombres = [e.get('nombre','') for e in empleados if e.get('nombre')]
    context.user_data['_empleados_list'] = empleados
    await update.message.reply_text(
        "👷 *Registrar pago de sueldo*\n\n¿A qué empleado?",
        parse_mode="Markdown",
        reply_markup=kb(nombres, cols=1))
    return SUELDO_EMP

async def sueldo_emp(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    nombre = update.message.text.strip()
    context.user_data['empleado'] = nombre
    # Buscar costo/hora del empleado
    emps = context.user_data.get('_empleados_list', [])
    emp = next((e for e in emps if e.get('nombre') == nombre), None)
    context.user_data['costoh'] = emp.get('costoh', 0) if emp else 0
    context.user_data['emp_id'] = emp.get('id','') if emp else ''
    # Sugerir período actual
    ahora = datetime.now()
    mes_actual = ahora.strftime("%B %Y")
    await update.message.reply_text(
        f"📅 ¿Qué período se paga?\n_(Ej: Mayo 2026, 1° quincena Mayo 2026)_",
        parse_mode="Markdown",
        reply_markup=kb([f"1° quincena {mes_actual}", f"2° quincena {mes_actual}", mes_actual], cols=1))
    return SUELDO_PERIODO

async def sueldo_periodo(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['periodo'] = update.message.text.strip()
    await update.message.reply_text(
        "💵 ¿Monto del sueldo a pagar?\n_(solo el número)_",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return SUELDO_MONTO

async def sueldo_monto(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    try: monto = float(update.message.text.strip().replace(".","").replace(",","."))
    except:
        await update.message.reply_text("❌ Ingresá solo el número, ej: `250000`", parse_mode="Markdown")
        return SUELDO_MONTO
    context.user_data['monto'] = monto
    await update.message.reply_text(
        "💳 ¿Forma de pago?", parse_mode="Markdown",
        reply_markup=kb(["Transferencia","Efectivo","Cheque propio"]))
    return SUELDO_OBS

async def sueldo_obs(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    forma = update.message.text.strip()
    d = context.user_data
    item = {
        "id": gen_id(), "fecha": today(),
        "proveedor": "", "empleado": d.get('empleado',''),
        "factura": "", "sinFactura": True,
        "tipogasto": "Sueldos",
        "proyecto": "", "pago": forma,
        "monto": d.get('monto', 0),
        "obs": f"Sueldo {d.get('empleado','')} — {d.get('periodo','')} [Telegram]",
        "vencimiento": "", "pagadoCC": 0
    }
    db.collection("egresos").document(item["id"]).set(item)
    await update.message.reply_text(
        f"✅ *Sueldo registrado*\n\n"
        f"👷 {d.get('empleado','')}\n"
        f"📅 Período: {d.get('periodo','')}\n"
        f"💳 Forma: {forma}\n"
        f"💸 Monto: {fmt(d.get('monto',0))}",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ── PROYECTO ────────────────────────────────────────────────────────
async def proy_start(update, context):
    if not es_admin(update): return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "🏗️ *Nuevo proyecto*\n\n📝 ¿Nombre del proyecto?",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return PROY_NOMBRE

async def proy_nombre(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['nombre'] = update.message.text.strip()
    clientes = get_clientes()
    await update.message.reply_text("👤 ¿Cliente?", parse_mode="Markdown",
        reply_markup=kb(clientes,cols=1) if clientes else ReplyKeyboardRemove())
    return PROY_CLIENTE

async def proy_cliente(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['cliente'] = update.message.text.strip()
    await update.message.reply_text("⚙️ ¿Tipo de trabajo?", parse_mode="Markdown",
        reply_markup=kb(["Ingeniería","Metalúrgica","Mantenimiento"]))
    return PROY_TIPO

async def proy_tipo(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    context.user_data['tipo'] = update.message.text.strip()
    await update.message.reply_text(
        "💰 ¿Monto de venta / presupuesto acordado?\n_(o `0` si no está definido)_",
        parse_mode="Markdown", reply_markup=kb(["0"]))
    return PROY_VENTA

async def proy_venta(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    try: venta = float(update.message.text.strip().replace(".","").replace(",","."))
    except: venta = 0
    context.user_data['venta'] = venta
    await update.message.reply_text("📝 ¿Observaciones?\n_(o `no`)_",
        parse_mode="Markdown", reply_markup=kb(["no"]))
    return PROY_OBS_P

async def proy_obs(update, context):
    if update.message.text == CANCELAR: return await cancelar(update, context)
    txt = update.message.text.strip()
    d = context.user_data
    obs = "" if txt.lower()=="no" else txt
    item = {
        "id": gen_id(),
        "nombre": d.get('nombre',''),
        "cliente": d.get('cliente',''),
        "tipo": d.get('tipo','Metalúrgica'),
        "finicio": today(), "ffin": "",
        "hest": 0, "hreal": 0, "costoh": 0,
        "matest": 0, "matreal": 0,
        "venta": d.get('venta', 0),
        "obs": obs + " [Telegram]",
        "estado": "En curso",
        "empleadosAsignados": []
    }
    db.collection("proyectos").document(item["id"]).set(item)
    await update.message.reply_text(
        f"✅ *Proyecto creado*\n\n"
        f"🏗️ {item['nombre']}\n"
        f"👤 {item['cliente']} | ⚙️ {item['tipo']}\n"
        f"💰 Venta: {fmt(item['venta'])}\n"
        f"📅 Inicio: {today()}\n\n"
        f"_Podés asignar empleados desde la app principal._",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ── CANCELAR ────────────────────────────────────────────────────────
async def cancelar(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── PROYECTOS (listado) ─────────────────────────────────────────────
async def cmd_proyectos(update, context):
    if not es_admin(update): return
    docs = db.collection("proyectos").where("estado","==","En curso").stream()
    proyectos = [d.to_dict() for d in docs]
    if not proyectos:
        await update.message.reply_text("📋 No hay proyectos activos.")
        return
    texto = "📋 *Proyectos activos*\n\n"
    for p in proyectos:
        texto += f"🏗️ *{p.get('nombre','—')}*\n   👤 {p.get('cliente','—')} · {p.get('tipo','—')}\n   💰 {fmt(p.get('venta',0))}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

# ── SALDO ───────────────────────────────────────────────────────────
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
        parse_mode="Markdown")

# ── FOTO ────────────────────────────────────────────────────────────
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
        except: descripcion = caption
    item = {"id":gen_id(),"fecha":today(),"proveedor":proveedor,
        "factura":"","sinFactura":False,"tipogasto":"Gastos administrativos",
        "proyecto":"","pago":"Efectivo","monto":monto,
        "obs":f"{descripcion} [foto Telegram id:{file_id}]",
        "vencimiento":"","pagadoCC":0}
    db.collection("egresos").document(item["id"]).set(item)
    if monto > 0:
        resp = f"🧾 *Factura guardada*\n📅 {today()} | 🏢 {proveedor} | 💸 {fmt(monto)}\n_Editá los detalles desde la app._"
    else:
        resp = "🧾 *Foto guardada*\nNo detecté el monto.\n_Tip: `45000 YPF combustible`_"
    await update.message.reply_text(resp, parse_mode="Markdown")

# ── TEXTO LIBRE ─────────────────────────────────────────────────────
async def handle_texto(update, context):
    if not es_admin(update): return
    await update.message.reply_text(
        "No entendí ese mensaje.\n\n/ingreso · /egreso · /sueldo · /proyecto · /proyectos · /saldo\n\nO /start para ver la ayuda.",
        reply_markup=ReplyKeyboardRemove())

# ── MAIN ────────────────────────────────────────────────────────────
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

    conv_sueldo = ConversationHandler(
        entry_points=[CommandHandler("sueldo", sueldo_start)],
        states={
            SUELDO_EMP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, sueldo_emp)],
            SUELDO_PERIODO: [MessageHandler(filters.TEXT & ~filters.COMMAND, sueldo_periodo)],
            SUELDO_MONTO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, sueldo_monto)],
            SUELDO_OBS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, sueldo_obs)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    conv_proyecto = ConversationHandler(
        entry_points=[CommandHandler("proyecto", proy_start)],
        states={
            PROY_NOMBRE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, proy_nombre)],
            PROY_CLIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, proy_cliente)],
            PROY_TIPO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, proy_tipo)],
            PROY_VENTA:   [MessageHandler(filters.TEXT & ~filters.COMMAND, proy_venta)],
            PROY_OBS_P:   [MessageHandler(filters.TEXT & ~filters.COMMAND, proy_obs)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("proyectos", cmd_proyectos))
    app.add_handler(CommandHandler("saldo", cmd_saldo))
    app.add_handler(conv_ingreso)
    app.add_handler(conv_egreso)
    app.add_handler(conv_sueldo)
    app.add_handler(conv_proyecto)
    app.add_handler(MessageHandler(filters.PHOTO, handle_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_texto))

    logger.info("Bot PEGASO iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

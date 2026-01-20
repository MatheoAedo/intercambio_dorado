from flask import Flask, render_template, request, redirect, url_for, session, flash
from db import query_one

app = Flask(__name__)
app.secret_key = "dev_secret"


# ---------------------------
# USUARIOS MOCK (LOGIN + ROLES)
# ----------------------------
USUARIOS = [
    {"id": 1, "nombre": "Admin", "email": "admin@mail.com", "password": "Admin1234!", "rol": "admin"},
    {"id": 2, "nombre": "Rosa", "email": "rosa@mail.com", "password": "Demo1234!", "rol": "usuario"},
]


def get_user_by_email(email):
    return next((u for u in USUARIOS if u["email"] == email), None)


def is_logged_in():
    return session.get("user_id") is not None


def is_admin():
    return session.get("rol") == "admin"


# ----------------------------
# VALIDACIONES SIMPLES 
# ----------------------------
def valid_text(value, min_len=3, max_len=600):
    value = (value or "").strip()
    if len(value) < min_len:
        return None
    if len(value) > max_len:
        return None
    return value


def valid_int(value, min_val, max_val):
    try:
        n = int(value)
        if n < min_val or n > max_val:
            return None
        return n
    except:
        return None

SERVICIOS = [
    {"id": 1, "titulo": "Clases de celular", "descripcion": "Ayuda para WhatsApp, videollamadas y fotos.", "creditos_hora": 2},
    {"id": 2, "titulo": "Acompañamiento médico", "descripcion": "Acompañar a consulta y ayudar con trámites.", "creditos_hora": 3},
]

INTERCAMBIOS = [
    {"id": 1, "id_servicio": 1, "fecha": "2026-01-19 10:00:00", "estado": "pendiente"},
]

VALORACIONES = [
    {"id": 1, "id_intercambio": 1, "puntuacion": 5, "comentario": "Muy amable y paciente.", "fecha": "2026-01-19 12:30:00"},
]

ESTADOS = ["pendiente", "confirmado", "en_progreso", "completado", "cancelado"]


def next_id(lista):
    return (lista[-1]["id"] + 1) if lista else 1


# ----------------------------
# HOME PUBLICO
# ----------------------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


# ----------------------------
# DASHBOARD SEGUN ROL
# ----------------------------
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    if is_admin():
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/dashboard/user")
def user_dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    if is_admin():
        return redirect(url_for("admin_dashboard"))

    return render_template("dashboard_user.html")


@app.route("/dashboard/admin")
def admin_dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return render_template("no_permiso.html"), 403

    return render_template("dashboard_admin.html")


# ----------------------------
# LOGIN / LOGOUT
# ----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if not user or user["password"] != password:
            flash("Correo o contraseña incorrectos.", "danger")
            return render_template("login.html", error="Correo o contraseña incorrectos")

        session["user_id"] = user["id"]
        session["user_nombre"] = user["nombre"]
        session["rol"] = user["rol"]

        flash(f"Bienvenido/a {user['nombre']} 👋", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("login"))


# ----------------------------
# ADMIN PANEL 
# ----------------------------
@app.route("/admin")
def admin_panel():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_admin():
        flash("Acceso denegado: no tienes permisos de administrador.", "danger")
        return render_template("no_permiso.html"), 403
    return render_template("admin_panel.html", usuarios=USUARIOS)


# ----------------------------
# CRUD SERVICIOS
# ----------------------------
@app.route("/servicios")
def servicios_list():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("servicios_list.html", servicios=SERVICIOS)


@app.route("/servicios/create", methods=["GET", "POST"])
def servicios_create():
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        titulo = valid_text(request.form.get("titulo"), 3, 100)
        descripcion = valid_text(request.form.get("descripcion"), 10, 600)
        creditos_hora = valid_int(request.form.get("creditos_hora"), 1, 10)

        if not titulo:
            flash("El título debe tener entre 3 y 100 caracteres.", "danger")
            return render_template("servicios_create.html")

        if not descripcion:
            flash("La descripción debe tener entre 10 y 600 caracteres.", "danger")
            return render_template("servicios_create.html")

        if creditos_hora is None:
            flash("Los créditos por hora deben estar entre 1 y 10.", "danger")
            return render_template("servicios_create.html")

        SERVICIOS.append({
            "id": next_id(SERVICIOS),
            "titulo": titulo,
            "descripcion": descripcion,
            "creditos_hora": creditos_hora,
        })

        flash("Servicio creado correctamente.", "success")
        return redirect(url_for("servicios_list"))

    return render_template("servicios_create.html")


@app.route("/servicios/edit/<int:id>", methods=["GET", "POST"])
def servicios_edit(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    servicio = next((s for s in SERVICIOS if s["id"] == id), None)
    if not servicio:
        flash("Servicio no encontrado.", "danger")
        return redirect(url_for("servicios_list"))

    if request.method == "POST":
        titulo = valid_text(request.form.get("titulo"), 3, 100)
        descripcion = valid_text(request.form.get("descripcion"), 10, 600)
        creditos_hora = valid_int(request.form.get("creditos_hora"), 1, 10)

        if not titulo:
            flash("El título debe tener entre 3 y 100 caracteres.", "danger")
            return render_template("servicios_edit.html", servicio=servicio)

        if not descripcion:
            flash("La descripción debe tener entre 10 y 600 caracteres.", "danger")
            return render_template("servicios_edit.html", servicio=servicio)

        if creditos_hora is None:
            flash("Los créditos por hora deben estar entre 1 y 10.", "danger")
            return render_template("servicios_edit.html", servicio=servicio)

        servicio["titulo"] = titulo
        servicio["descripcion"] = descripcion
        servicio["creditos_hora"] = creditos_hora

        flash("Servicio actualizado correctamente.", "success")
        return redirect(url_for("servicios_list"))

    return render_template("servicios_edit.html", servicio=servicio)


@app.route("/servicios/delete/<int:id>")
def servicios_delete(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    servicio = next((s for s in SERVICIOS if s["id"] == id), None)
    if not servicio:
        flash("No se pudo eliminar: servicio no encontrado.", "danger")
        return redirect(url_for("servicios_list"))

    SERVICIOS.remove(servicio)

    flash("Servicio eliminado.", "info")
    return redirect(url_for("servicios_list"))


# ----------------------------
# CRUD INTERCAMBIOS
# ----------------------------
@app.route("/intercambios")
def intercambios_list():
    if not is_logged_in():
        return redirect(url_for("login"))

    servicios_map = {s["id"]: s["titulo"] for s in SERVICIOS}
    return render_template("intercambios_list.html", intercambios=INTERCAMBIOS, servicios_map=servicios_map)


@app.route("/intercambios/create", methods=["GET", "POST"])
def intercambios_create():
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        id_servicio = valid_int(request.form.get("id_servicio"), 1, 10**9)
        fecha = valid_text(request.form.get("fecha"), 10, 30)
        estado = request.form.get("estado")

        if id_servicio is None or not any(s["id"] == id_servicio for s in SERVICIOS):
            flash("Debes seleccionar un servicio válido.", "danger")
            return render_template("intercambios_create.html", servicios=SERVICIOS, estados=ESTADOS)

        if not fecha:
            flash("La fecha debe tener un formato válido (mínimo 10 caracteres).", "danger")
            return render_template("intercambios_create.html", servicios=SERVICIOS, estados=ESTADOS)

        if estado not in ESTADOS:
            flash("Estado inválido.", "danger")
            return render_template("intercambios_create.html", servicios=SERVICIOS, estados=ESTADOS)

        INTERCAMBIOS.append({
            "id": next_id(INTERCAMBIOS),
            "id_servicio": id_servicio,
            "fecha": fecha,
            "estado": estado,
        })

        flash("Intercambio creado correctamente.", "success")
        return redirect(url_for("intercambios_list"))

    return render_template("intercambios_create.html", servicios=SERVICIOS, estados=ESTADOS)


@app.route("/intercambios/edit/<int:id>", methods=["GET", "POST"])
def intercambios_edit(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    intercambio = next((i for i in INTERCAMBIOS if i["id"] == id), None)
    if not intercambio:
        flash("Intercambio no encontrado.", "danger")
        return redirect(url_for("intercambios_list"))

    if request.method == "POST":
        id_servicio = valid_int(request.form.get("id_servicio"), 1, 10**9)
        fecha = valid_text(request.form.get("fecha"), 10, 30)
        estado = request.form.get("estado")

        if id_servicio is None or not any(s["id"] == id_servicio for s in SERVICIOS):
            flash("Debes seleccionar un servicio válido.", "danger")
            return render_template("intercambios_edit.html", intercambio=intercambio, servicios=SERVICIOS, estados=ESTADOS)

        if not fecha:
            flash("La fecha debe tener un formato válido (mínimo 10 caracteres).", "danger")
            return render_template("intercambios_edit.html", intercambio=intercambio, servicios=SERVICIOS, estados=ESTADOS)

        if estado not in ESTADOS:
            flash("Estado inválido.", "danger")
            return render_template("intercambios_edit.html", intercambio=intercambio, servicios=SERVICIOS, estados=ESTADOS)

        intercambio["id_servicio"] = id_servicio
        intercambio["fecha"] = fecha
        intercambio["estado"] = estado

        flash("Intercambio actualizado correctamente.", "success")
        return redirect(url_for("intercambios_list"))

    return render_template("intercambios_edit.html", intercambio=intercambio, servicios=SERVICIOS, estados=ESTADOS)


@app.route("/intercambios/delete/<int:id>")
def intercambios_delete(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    intercambio = next((i for i in INTERCAMBIOS if i["id"] == id), None)
    if not intercambio:
        flash("No se pudo eliminar: intercambio no encontrado.", "danger")
        return redirect(url_for("intercambios_list"))

    INTERCAMBIOS.remove(intercambio)

    flash("Intercambio eliminado.", "info")
    return redirect(url_for("intercambios_list"))


# ----------------------------
# CRUD VALORACIONES
# ----------------------------
@app.route("/valoraciones")
def valoraciones_list():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("valoraciones_list.html", valoraciones=VALORACIONES)


@app.route("/valoraciones/create", methods=["GET", "POST"])
def valoraciones_create():
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        id_intercambio = valid_int(request.form.get("id_intercambio"), 1, 10**9)
        puntuacion = valid_int(request.form.get("puntuacion"), 1, 5)
        comentario = (request.form.get("comentario") or "").strip()

        if len(comentario) > 300:
            comentario = comentario[:300]

        if id_intercambio is None or not any(i["id"] == id_intercambio for i in INTERCAMBIOS):
            flash("Debes seleccionar un intercambio válido.", "danger")
            return render_template("valoraciones_create.html", intercambios=INTERCAMBIOS)

        if puntuacion is None:
            flash("La puntuación debe estar entre 1 y 5.", "danger")
            return render_template("valoraciones_create.html", intercambios=INTERCAMBIOS)

        VALORACIONES.append({
            "id": next_id(VALORACIONES),
            "id_intercambio": id_intercambio,
            "puntuacion": puntuacion,
            "comentario": comentario,
            "fecha": "2026-01-19 13:00:00",
        })

        flash("Valoración creada correctamente.", "success")
        return redirect(url_for("valoraciones_list"))

    return render_template("valoraciones_create.html", intercambios=INTERCAMBIOS)


@app.route("/valoraciones/edit/<int:id>", methods=["GET", "POST"])
def valoraciones_edit(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    valoracion = next((v for v in VALORACIONES if v["id"] == id), None)
    if not valoracion:
        flash("Valoración no encontrada.", "danger")
        return redirect(url_for("valoraciones_list"))

    if request.method == "POST":
        id_intercambio = valid_int(request.form.get("id_intercambio"), 1, 10**9)
        puntuacion = valid_int(request.form.get("puntuacion"), 1, 5)
        comentario = (request.form.get("comentario") or "").strip()

        if len(comentario) > 300:
            comentario = comentario[:300]

        if id_intercambio is None or not any(i["id"] == id_intercambio for i in INTERCAMBIOS):
            flash("Debes seleccionar un intercambio válido.", "danger")
            return render_template("valoraciones_edit.html", valoracion=valoracion, intercambios=INTERCAMBIOS)

        if puntuacion is None:
            flash("La puntuación debe estar entre 1 y 5.", "danger")
            return render_template("valoraciones_edit.html", valoracion=valoracion, intercambios=INTERCAMBIOS)

        valoracion["id_intercambio"] = id_intercambio
        valoracion["puntuacion"] = puntuacion
        valoracion["comentario"] = comentario

        flash("Valoración actualizada correctamente.", "success")
        return redirect(url_for("valoraciones_list"))

    return render_template("valoraciones_edit.html", valoracion=valoracion, intercambios=INTERCAMBIOS)


@app.route("/valoraciones/delete/<int:id>")
def valoraciones_delete(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    valoracion = next((v for v in VALORACIONES if v["id"] == id), None)
    if not valoracion:
        flash("No se pudo eliminar: valoración no encontrada.", "danger")
        return redirect(url_for("valoraciones_list"))

    VALORACIONES.remove(valoracion)

    flash("Valoración eliminada.", "info")
    return redirect(url_for("valoraciones_list"))


# ----------------------------
# REPORTE: REPUTACIÓN
# ----------------------------
@app.route("/reputacion")
def reputacion():
    if not is_logged_in():
        return redirect(url_for("login"))

    promedio = {}
    conteo = {}

    intercambio_servicio = {i["id"]: i["id_servicio"] for i in INTERCAMBIOS}

    for v in VALORACIONES:
        id_serv = intercambio_servicio.get(v["id_intercambio"])
        if not id_serv:
            continue
        promedio[id_serv] = promedio.get(id_serv, 0) + v["puntuacion"]
        conteo[id_serv] = conteo.get(id_serv, 0) + 1

    data = []
    for s in SERVICIOS:
        c = conteo.get(s["id"], 0)
        avg = (promedio.get(s["id"], 0) / c) if c else None
        data.append({"id_servicio": s["id"], "titulo": s["titulo"], "cantidad": c, "promedio": avg})

    data.sort(key=lambda x: (x["promedio"] is not None, x["promedio"]), reverse=True)
    return render_template("reputacion.html", data=data)


# ----------------------------
# CONTACTO (publico)
# ----------------------------
CONTACT_MESSAGES = []

@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        asunto = (request.form.get("asunto") or "").strip() or "Sin asunto"
        mensaje = (request.form.get("mensaje") or "").strip()

        if not nombre or not email or not mensaje:
            flash("Por favor completa nombre, correo y mensaje.", "danger")
            return render_template("contacto.html")

        CONTACT_MESSAGES.append({
            "id": len(CONTACT_MESSAGES) + 1,
            "nombre": nombre,
            "email": email,
            "asunto": asunto,
            "mensaje": mensaje,
        })

        flash("Mensaje enviado. El administrador lo revisará.", "success")
        return redirect(url_for("home"))

    return render_template("contacto.html")

@app.route("/db-test")
def db_test():
    row = query_one("SELECT 1 AS ok;")
    return {"db": "ok", "result": row}


if __name__ == "__main__":
    app.run(debug=True)

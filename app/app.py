import os
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from app.db import query_one, query_all, execute


# ============================================================
# Configuración Flask
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_local")

# ✅ Estados permitidos de un intercambio
ESTADOS = ["pendiente", "confirmado", "en_progreso", "completado", "cancelado"]

# ============================================================
# Intercambios: reglas de transición (máquina de estados)
# ============================================================
TRANSICIONES = {
    "pendiente": {"confirmado", "cancelado"},
    "confirmado": {"en_progreso", "cancelado"},
    "en_progreso": {"completado", "cancelado"},
    "completado": set(),
    "cancelado": set(),
}


def allowed_states_for_user(actual: str, es_proveedor: bool):
    """
    Devuelve los estados que se muestran en el <select> del listado de intercambios.

    Regla simple (para evitar confusiones):
    - Siempre se muestra el estado actual.
    - Si está activo (pendiente/confirmado/en_progreso), se permite "cancelado".
    - Solo el proveedor puede avanzar según TRANSICIONES.
    """
    actual = actual or "pendiente"
    opciones = {actual}

    # ✅ En estados "activos", se permite cancelar
    if actual in ("pendiente", "confirmado", "en_progreso"):
        opciones.add("cancelado")

    # ✅ El proveedor puede avanzar de estado
    if es_proveedor:
        opciones |= TRANSICIONES.get(actual, set())

    return [e for e in ESTADOS if e in opciones]


# ============================================================
# Helpers: validaciones y permisos
# ============================================================
def valid_text(value, min_len=3, max_len=600):
    """Valida texto: trim + largo mínimo y máximo. Retorna None si no cumple."""
    value = (value or "").strip()
    if len(value) < min_len or len(value) > max_len:
        return None
    return value


def valid_int(value, min_val, max_val):
    """Valida entero entre rangos. Retorna None si es inválido."""
    try:
        n = int(value)
        if n < min_val or n > max_val:
            return None
        return n
    except Exception:
        return None


def is_logged_in():
    """True si el usuario tiene sesión activa."""
    return session.get("user_id") is not None


def is_admin():
    """True si el rol en sesión es admin."""
    return session.get("rol") == "admin"


def admin_required():
    """
    Guard para rutas de administrador.
    Devuelve redirect si no cumple; si cumple, devuelve None.
    """
    if not is_logged_in():
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))
    if not is_admin():
        flash("Acceso denegado: solo administrador.", "danger")
        return redirect(url_for("home"))
    return None


def admin_cannot_use(feature_name="esta función"):
    """
    Bloquea funcionalidades que el admin NO debe usar
    (crear servicios/intercambios/valorar). El admin solo modera.
    """
    if not is_logged_in():
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))
    if is_admin():
        flash(f"Como administrador, no puedes usar {feature_name}. Solo puedes moderar.", "info")
        return redirect(url_for("admin_dashboard"))
    return None


def get_user_by_email(email: str):
    """Obtiene usuario por email + rol."""
    return query_one(
        """
        SELECT u.id_usuario AS id,
               u.nombre,
               u.email,
               u.password_hash,
               r.nombre_rol AS rol
        FROM usuario u
        JOIN rol r ON r.id_rol = u.id_rol
        WHERE u.email = %s
        """,
        (email,),
    )


# ============================================================
# Formato de fechas: SQL TO_CHAR
# - Así en todas las vistas se muestra DD-MM-YYYY
# - La BD sigue guardando timestamp completo (trazabilidad)
# ============================================================
DATE_FMT = "DD-MM-YYYY"


# ============================================================
# NOTIFICACIONES
# ============================================================
@app.context_processor
def inject_notifs():
    """
    Inyecta contadores simples para mostrar badge en el navbar:
    - solicitudes recibidas en pendiente (proveedor)
    - intercambios activos confirmados/en_progreso
    - chats (conteo total de mensajes en intercambios donde participo)
    """
    if not is_logged_in():
        return {}

    uid = session["user_id"]

    pendientes = query_one(
        """
        SELECT COUNT(*)::int AS n
        FROM intercambio
        WHERE id_proveedor=%s AND estado='pendiente'
        """,
        (uid,),
    ) or {"n": 0}

    activos = query_one(
        """
        SELECT COUNT(*)::int AS n
        FROM intercambio
        WHERE (id_solicitante=%s OR id_proveedor=%s)
          AND estado IN ('confirmado','en_progreso')
        """,
        (uid, uid),
    ) or {"n": 0}

    chats = query_one(
        """
        SELECT COUNT(*)::int AS n
        FROM mensaje_intercambio m
        JOIN intercambio i ON i.id_intercambio = m.id_intercambio
        WHERE (i.id_solicitante=%s OR i.id_proveedor=%s)
        """,
        (uid, uid),
    ) or {"n": 0}

    notif_count = int(pendientes["n"]) + int(activos["n"])
    return {
        "notif_count": notif_count,
        "notif_pendientes": int(pendientes["n"]),
        "notif_activos": int(activos["n"]),
        "notif_chats_total": int(chats["n"]),
    }


# ============================================================
# Debug (solo útil en local)
# ============================================================
@app.route("/db-whoami")
def db_whoami():
    guard = admin_required()
    if guard:
        return guard
    row = query_one("SELECT current_database() AS db, inet_server_addr()::text AS server_ip;")
    return {"db": row}


# ============================================================
# Público
# ============================================================
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


# ============================================================
# Contacto público
# ============================================================
CONTACT_MESSAGES = [] 


@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    """
    Formulario público sin login.
    Guarda mensajes en memoria (DEMO).
    """
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        asunto = (request.form.get("asunto") or "").strip() or "Sin asunto"
        mensaje = (request.form.get("mensaje") or "").strip()

        if not nombre or not email or not mensaje:
            flash("Por favor completa nombre, correo y mensaje.", "danger")
            return render_template("contacto.html")

        CONTACT_MESSAGES.append(
            {
                "id": len(CONTACT_MESSAGES) + 1,
                "tipo": "publico",
                "nombre": nombre,
                "email": email,
                "categoria": "consulta",
                "asunto": asunto,
                "mensaje": mensaje,
                "respuesta": None,
                "cerrado": False,
                "fecha": datetime.now().strftime("%d-%m-%Y"),
            }
        )

        flash("Mensaje enviado. El administrador lo revisará.", "success")
        return redirect(url_for("home"))

    return render_template("contacto.html")


# ============================================================
# Contacto interno al admin (DEMO en memoria)
# ============================================================
@app.route("/contacto-admin", methods=["GET", "POST"])
def contacto_admin():
    """Formulario interno: requiere sesión."""
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        nombre = valid_text(request.form.get("nombre"), 3, 100)
        asunto = valid_text(request.form.get("asunto"), 3, 120)
        categoria = (request.form.get("categoria") or "").strip().lower()
        mensaje = valid_text(request.form.get("mensaje"), 5, 600)

        if categoria not in ["reclamo", "sugerencia", "consulta", "felicitaciones"]:
            categoria = "consulta"

        if not (nombre and asunto and mensaje):
            flash("Completa nombre, asunto y mensaje.", "danger")
            return render_template("contacto_admin.html")

        CONTACT_MESSAGES.append(
            {
                "id": len(CONTACT_MESSAGES) + 1,
                "tipo": "interno",
                "user_id": session["user_id"],
                "nombre": nombre,
                "email": session.get("user_email", ""),
                "categoria": categoria,
                "asunto": asunto,
                "mensaje": mensaje,
                "respuesta": None,
                "cerrado": False,
                "fecha": datetime.now().strftime("%d-%m-%Y"),
            }
        )

        flash("Mensaje enviado al administrador (demo).", "success")
        return redirect(url_for("perfil"))

    return render_template("contacto_admin.html")


@app.route("/admin/contactos")
def admin_contactos_inbox():
    """Bandeja de mensajes de contacto (admin)."""
    guard = admin_required()
    if guard:
        return guard

    msgs = sorted(CONTACT_MESSAGES, key=lambda x: (x.get("cerrado", False), x.get("id", 0)))
    return render_template("contacto_admin_inbox.html", mensajes=msgs)


@app.route("/admin/contactos/responder/<int:mid>", methods=["POST"])
def admin_contactos_responder(mid):
    """Respuesta del admin a un mensaje (demo)."""
    guard = admin_required()
    if guard:
        return guard

    respuesta = valid_text(request.form.get("respuesta"), 1, 600)
    if respuesta is None:
        flash("La respuesta no puede estar vacía.", "danger")
        return redirect(url_for("admin_contactos_inbox"))

    for m in CONTACT_MESSAGES:
        if m["id"] == mid:
            m["respuesta"] = respuesta
            m["cerrado"] = True
            flash("Respuesta enviada (demo) y caso cerrado.", "success")
            break
    else:
        flash("Mensaje no encontrado.", "warning")

    return redirect(url_for("admin_contactos_inbox"))


# ============================================================
# Dashboard
# ============================================================
@app.route("/dashboard")
def dashboard():
    """Deriva según rol."""
    if not is_logged_in():
        return redirect(url_for("login"))
    if is_admin():
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/dashboard/user")
def user_dashboard():
    """Dashboard usuario: ve servicios de otros para solicitar intercambio."""
    if not is_logged_in():
        return redirect(url_for("login"))
    if is_admin():
        return redirect(url_for("admin_dashboard"))

    servicios = query_all(
        """
        SELECT s.id_servicio AS id,
               s.titulo,
               s.descripcion,
               s.creditos_hora,
               u.nombre AS dueno_nombre,
               u.ubicacion AS dueno_ubicacion,
               u.id_usuario AS dueno_id
        FROM servicio s
        JOIN usuario u ON u.id_usuario = s.id_usuario
        WHERE s.id_usuario <> %s
        ORDER BY s.id_servicio DESC
        """,
        (session["user_id"],),
    )

    return render_template("dashboard_user.html", servicios=servicios, nombre=session.get("user_nombre", "Usuario"))


@app.route("/dashboard/admin")
def admin_dashboard():
    """Dashboard admin: lista servicios para moderar."""
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_admin():
        return render_template("no_permiso.html"), 403

    servicios = query_all(
        """
        SELECT s.id_servicio AS id,
               s.titulo,
               s.descripcion,
               s.creditos_hora,
               u.nombre AS dueno_nombre,
               u.email AS dueno_email
        FROM servicio s
        JOIN usuario u ON u.id_usuario = s.id_usuario
        ORDER BY s.id_servicio DESC
        """
    )

    return render_template("dashboard_admin.html", servicios=servicios, nombre=session.get("user_nombre", "Administrador"))


# ============================================================
# Login / Register / Logout
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    """Inicio de sesión."""
    if is_logged_in():
        flash("Ya tienes una sesión iniciada. Para ingresar con otra cuenta, primero cierra sesión.", "info")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)

        if not user or not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
            flash("Correo o contraseña incorrectos.", "danger")
            return render_template("login.html", error="Correo o contraseña incorrectos")

        # ✅ Guardamos datos básicos en sesión
        session["user_id"] = user["id"]
        session["user_nombre"] = user["nombre"]
        session["rol"] = user["rol"]
        session["user_email"] = user["email"]

        flash(f"Bienvenido/a {user['nombre']} 👋", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Registro de usuarios (adulto mayor)."""
    if is_logged_in():
        flash("Ya tienes una sesión iniciada. Para crear otra cuenta, primero cierra sesión.", "info")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        nombre = valid_text(request.form.get("nombre"), 3, 100)
        email = (request.form.get("email") or "").strip().lower()

        edad = valid_int(request.form.get("edad"), 60, 120)
        ubicacion = valid_text(request.form.get("ubicacion"), 2, 100)

        password = (request.form.get("password") or "").strip()
        password2 = (request.form.get("password2") or "").strip()

        # Validaciones
        if not nombre:
            flash("El nombre debe tener al menos 3 caracteres.", "danger")
            return render_template("register.html")

        if not email or "@" not in email:
            flash("Correo inválido.", "danger")
            return render_template("register.html")

        if edad is None:
            flash("La edad debe estar entre 60 y 120.", "danger")
            return render_template("register.html")

        if not ubicacion:
            flash("La ubicación es obligatoria (mínimo 2 caracteres).", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return render_template("register.html")

        if password != password2:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("register.html")

        # Evitar emails duplicados
        existe = query_one("SELECT 1 FROM usuario WHERE email=%s", (email,))
        if existe:
            flash("Ese correo ya está registrado.", "warning")
            return render_template("register.html")

        # Obtener rol usuario
        rol_user = query_one("SELECT id_rol FROM rol WHERE nombre_rol='usuario'")
        if not rol_user:
            flash("No existe el rol 'usuario'. Ejecuta /init-db.", "danger")
            return render_template("register.html")

        # Insert usuario con créditos iniciales (10)
        execute(
            """
            INSERT INTO usuario (nombre, email, password_hash, edad, ubicacion, creditos, id_rol)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (nombre, email, generate_password_hash(password), edad, ubicacion, 10, rol_user["id_rol"]),
        )

        flash("Cuenta creada correctamente. Ahora inicia sesión.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    """Cierra sesión."""
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("login"))


# ============================================================
# Perfil propio + Perfil público
# ============================================================
@app.route("/perfil")
def perfil():
    """Perfil del usuario logueado + estadísticas."""
    if not is_logged_in():
        return redirect(url_for("login"))

    user_id = session["user_id"]

    usuario = query_one(
        """
        SELECT u.id_usuario AS id,
               u.nombre,
               u.email,
               u.edad,
               u.ubicacion,
               u.creditos,
               r.nombre_rol AS rol
        FROM usuario u
        JOIN rol r ON r.id_rol = u.id_rol
        WHERE u.id_usuario = %s
        """,
        (user_id,),
    )

    if not usuario:
        flash("No se encontró tu usuario.", "danger")
        return redirect(url_for("dashboard"))

    # Promedio y total de valoraciones recibidas
    stats = query_one(
        """
        SELECT
          COALESCE(ROUND(AVG(v.puntuacion)::numeric, 1), 0) AS promedio,
          COUNT(v.id_valoracion)::int AS total_valoraciones
        FROM valoracion v
        WHERE v.id_destinatario = %s
        """,
        (user_id,),
    ) or {"promedio": 0, "total_valoraciones": 0}

    # ✅ Últimas valoraciones recibidas
    ultimas_val = query_all(
        f"""
        SELECT v.puntuacion,
               v.comentario,
               TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
               ua.nombre AS autor
        FROM valoracion v
        JOIN usuario ua ON ua.id_usuario = v.id_autor
        WHERE v.id_destinatario=%s
        ORDER BY v.fecha_valoracion DESC
        LIMIT 5
        """,
        (user_id,),
    )

    # Total intercambios completados (usuario participó como solicitante o proveedor)
    intercambios = query_one(
        """
        SELECT COUNT(*)::int AS total
        FROM intercambio
        WHERE (id_solicitante=%s OR id_proveedor=%s)
          AND estado='completado'
        """,
        (user_id, user_id),
    )
    total_intercambios = intercambios["total"] if intercambios else 0

    return render_template(
        "perfil.html",
        usuario=usuario,
        user=usuario,
        stats=stats,
        total_intercambios=total_intercambios,
        ultimas_val=ultimas_val,
    )


@app.route("/usuarios/<int:id_usuario>")
def usuario_publico(id_usuario):
    """Perfil público: se ve después de login."""
    if not is_logged_in():
        return redirect(url_for("login"))

    u = query_one(
        """
        SELECT id_usuario AS id, nombre, ubicacion
        FROM usuario
        WHERE id_usuario=%s
        """,
        (id_usuario,),
    )
    if not u:
        flash("Usuario no encontrado.", "warning")
        return redirect(url_for("servicios_public"))

    stats = query_one(
        """
        SELECT
          COALESCE(ROUND(AVG(v.puntuacion)::numeric, 1), 0) AS promedio,
          COUNT(v.id_valoracion)::int AS total_valoraciones
        FROM valoracion v
        WHERE v.id_destinatario = %s
        """,
        (id_usuario,),
    ) or {"promedio": 0, "total_valoraciones": 0}

    ultimas_val = query_all(
        f"""
        SELECT v.puntuacion,
               v.comentario,
               TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
               ua.nombre AS autor
        FROM valoracion v
        JOIN usuario ua ON ua.id_usuario = v.id_autor
        WHERE v.id_destinatario=%s
        ORDER BY v.fecha_valoracion DESC
        LIMIT 5
        """,
        (id_usuario,),
    )

    total_inter = query_one(
        """
        SELECT COUNT(*)::int AS total
        FROM intercambio
        WHERE id_solicitante=%s OR id_proveedor=%s
        """,
        (id_usuario, id_usuario),
    ) or {"total": 0}

    return render_template(
        "usuario_publico.html",
        u=u,
        stats=stats,
        ultimas_val=ultimas_val,
        total_intercambios=int(total_inter["total"]),
    )


@app.route("/perfil/editar", methods=["GET", "POST"])
def perfil_editar():
    """Edición de perfil del usuario logueado."""
    if not is_logged_in():
        return redirect(url_for("login"))

    user_id = session["user_id"]

    usuario = query_one(
        """
        SELECT id_usuario AS id, nombre, email, edad, ubicacion
        FROM usuario
        WHERE id_usuario=%s
        """,
        (user_id,),
    )

    if not usuario:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        nombre = valid_text(request.form.get("nombre"), 3, 100)
        edad = valid_int(request.form.get("edad"), 18, 120)
        ubicacion = valid_text(request.form.get("ubicacion"), 2, 100)

        # email editable pero obligatorio
        email = (request.form.get("email") or "").strip().lower()
        if not email or "@" not in email:
            flash("Correo inválido.", "danger")
            return render_template("perfil_edit.html", usuario=usuario, user=usuario)

        new_pass = (request.form.get("password") or "").strip()
        new_pass2 = (request.form.get("password2") or "").strip()

        # validaciones básicas
        if not nombre:
            flash("El nombre debe tener al menos 3 caracteres.", "danger")
            return render_template("perfil_edit.html", usuario=usuario, user=usuario)
        if edad is None:
            flash("La edad debe estar entre 18 y 120.", "danger")
            return render_template("perfil_edit.html", usuario=usuario, user=usuario)
        if not ubicacion:
            flash("La ubicación es obligatoria (mínimo 2 caracteres).", "danger")
            return render_template("perfil_edit.html", usuario=usuario, user=usuario)

        dup = query_one("SELECT 1 FROM usuario WHERE email=%s AND id_usuario<>%s", (email, user_id))
        if dup:
            flash("Ese correo ya está en uso.", "warning")
            return render_template("perfil_edit.html", usuario=usuario, user=usuario)

        # Si cambia password, validamos y actualizamos hash
        if new_pass or new_pass2:
            if len(new_pass) < 6:
                flash("La nueva contraseña debe tener al menos 6 caracteres.", "danger")
                return render_template("perfil_edit.html", usuario=usuario, user=usuario)
            if new_pass != new_pass2:
                flash("Las contraseñas no coinciden.", "danger")
                return render_template("perfil_edit.html", usuario=usuario, user=usuario)

            execute(
                """
                UPDATE usuario
                SET nombre=%s, email=%s, edad=%s, ubicacion=%s, password_hash=%s
                WHERE id_usuario=%s
                """,
                (nombre, email, edad, ubicacion, generate_password_hash(new_pass), user_id),
            )
        else:
            execute(
                """
                UPDATE usuario
                SET nombre=%s, email=%s, edad=%s, ubicacion=%s
                WHERE id_usuario=%s
                """,
                (nombre, email, edad, ubicacion, user_id),
            )

        # Mantener sesión actualizada
        session["user_nombre"] = nombre
        session["user_email"] = email
        flash("Datos actualizados correctamente.", "success")
        return redirect(url_for("perfil"))

    return render_template("perfil_edit.html", usuario=usuario, user=usuario)


# ============================================================
# Admin panel (usuarios)
# ============================================================
@app.route("/admin")
def admin_panel():
    """Panel admin: lista usuarios."""
    guard = admin_required()
    if guard:
        return guard

    usuarios = query_all(
        """
        SELECT u.id_usuario AS id,
               u.nombre,
               u.email,
               u.edad,
               u.ubicacion,
               u.creditos,
               r.nombre_rol AS rol
        FROM usuario u
        JOIN rol r ON r.id_rol = u.id_rol
        ORDER BY u.id_usuario ASC
        """
    )
    return render_template("admin_panel.html", usuarios=usuarios)


@app.route("/admin/users/edit/<int:id>", methods=["POST"])
def admin_user_edit(id):
    """Admin: edita nombre/ubicación/créditos/rol."""
    guard = admin_required()
    if guard:
        return guard

    nombre = valid_text(request.form.get("nombre"), 3, 100)
    ubicacion = valid_text(request.form.get("ubicacion"), 2, 100)
    creditos = valid_int(request.form.get("creditos"), 0, 10**9)
    rol = (request.form.get("rol") or "").strip().lower()

    if rol not in ["admin", "usuario"]:
        flash("Rol inválido.", "danger")
        return redirect(url_for("admin_panel"))

    role_row = query_one("SELECT id_rol FROM rol WHERE nombre_rol=%s", (rol,))
    if not (nombre and ubicacion and creditos is not None and role_row):
        flash("Datos inválidos para actualizar usuario.", "danger")
        return redirect(url_for("admin_panel"))

    execute(
        """
        UPDATE usuario
        SET nombre=%s, ubicacion=%s, creditos=%s, id_rol=%s
        WHERE id_usuario=%s
        """,
        (nombre, ubicacion, creditos, role_row["id_rol"], id),
    )

    flash("Usuario actualizado.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/password/<int:id>", methods=["POST"])
def admin_user_password(id):
    """Admin: resetea password de un usuario."""
    guard = admin_required()
    if guard:
        return guard

    new_pass = (request.form.get("password") or "").strip()
    if len(new_pass) < 6:
        flash("La nueva clave debe tener al menos 6 caracteres.", "danger")
        return redirect(url_for("admin_panel"))

    execute(
        """
        UPDATE usuario
        SET password_hash=%s
        WHERE id_usuario=%s
        """,
        (generate_password_hash(new_pass), id),
    )

    flash("Contraseña actualizada.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/delete/<int:id>")
def admin_user_delete(id):
    """Admin: elimina usuario (ojo con cascadas definidas en BD)."""
    guard = admin_required()
    if guard:
        return guard

    if id == session.get("user_id"):
        flash("No puedes eliminar tu propio usuario en sesión.", "warning")
        return redirect(url_for("admin_panel"))

    execute("DELETE FROM usuario WHERE id_usuario=%s", (id,))
    flash("Usuario eliminado.", "info")
    return redirect(url_for("admin_panel"))


# ============================================================
# Admin: moderación de servicios
# ============================================================
@app.route("/admin/servicios/delete/<int:id_servicio>", methods=["POST"])
def admin_servicio_delete(id_servicio):
    """Admin: elimina cualquier servicio."""
    guard = admin_required()
    if guard:
        return guard

    existe = query_one("SELECT 1 FROM servicio WHERE id_servicio=%s", (id_servicio,))
    if not existe:
        flash("Servicio no encontrado.", "warning")
        return redirect(url_for("admin_dashboard"))

    execute("DELETE FROM servicio WHERE id_servicio=%s", (id_servicio,))
    flash("Servicio eliminado por el administrador.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/servicios/edit/<int:id_servicio>", methods=["GET", "POST"])
def admin_servicio_edit(id_servicio):
    """Admin: edita cualquier servicio (moderación)."""
    guard = admin_required()
    if guard:
        return guard

    servicio = query_one(
        """
        SELECT s.id_servicio AS id,
               s.titulo,
               s.descripcion,
               s.creditos_hora,
               u.nombre AS dueno_nombre,
               u.email AS dueno_email
        FROM servicio s
        JOIN usuario u ON u.id_usuario = s.id_usuario
        WHERE s.id_servicio=%s
        """,
        (id_servicio,),
    )

    if not servicio:
        flash("Servicio no encontrado.", "warning")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        titulo = valid_text(request.form.get("titulo"), 3, 120)
        descripcion = valid_text(request.form.get("descripcion"), 10, 600)
        creditos_hora = valid_int(request.form.get("creditos_hora"), 1, 10)

        if not titulo:
            flash("Título inválido (3 a 120).", "danger")
            return render_template("admin_servicio_edit.html", servicio=servicio)
        if not descripcion:
            flash("Descripción inválida (10 a 600).", "danger")
            return render_template("admin_servicio_edit.html", servicio=servicio)
        if creditos_hora is None:
            flash("Créditos por hora inválidos (1 a 10).", "danger")
            return render_template("admin_servicio_edit.html", servicio=servicio)

        execute(
            """
            UPDATE servicio
            SET titulo=%s, descripcion=%s, creditos_hora=%s
            WHERE id_servicio=%s
            """,
            (titulo, descripcion, creditos_hora, id_servicio),
        )

        flash("Servicio actualizado por moderación.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_servicio_edit.html", servicio=servicio)


# ============================================================
# Servicios propios (usuario normal)
# ============================================================
@app.route("/servicios")
def servicios_list():
    """Lista servicios del usuario logueado."""
    if not is_logged_in():
        return redirect(url_for("login"))

    servicios = query_all(
        """
        SELECT s.id_servicio AS id, s.titulo, s.descripcion, s.creditos_hora
        FROM servicio s
        WHERE s.id_usuario = %s
        ORDER BY s.id_servicio DESC
        """,
        (session["user_id"],),
    )
    return render_template("servicios_list.html", servicios=servicios)


@app.route("/servicios/create", methods=["GET", "POST"])
def servicios_create():
    """Crea un servicio del usuario."""
    if not is_logged_in():
        return redirect(url_for("login"))

    guard = admin_cannot_use("crear servicios")
    if guard:
        return guard

    if request.method == "POST":
        titulo = valid_text(request.form.get("titulo"), 3, 120)
        descripcion = valid_text(request.form.get("descripcion"), 10, 600)
        creditos_hora = valid_int(request.form.get("creditos_hora"), 1, 10)

        if not titulo:
            flash("El título debe tener entre 3 y 120 caracteres.", "danger")
            return render_template("servicios_create.html")
        if not descripcion:
            flash("La descripción debe tener entre 10 y 600 caracteres.", "danger")
            return render_template("servicios_create.html")
        if creditos_hora is None:
            flash("Los créditos por hora deben estar entre 1 y 10.", "danger")
            return render_template("servicios_create.html")

        execute(
            """
            INSERT INTO servicio (titulo, descripcion, creditos_hora, id_usuario)
            VALUES (%s, %s, %s, %s)
            """,
            (titulo, descripcion, creditos_hora, session["user_id"]),
        )

        flash("Servicio creado correctamente.", "success")
        return redirect(url_for("servicios_list"))

    return render_template("servicios_create.html")


@app.route("/servicios/edit/<int:id>", methods=["GET", "POST"])
def servicios_edit(id):
    """Edita un servicio propio."""
    if not is_logged_in():
        return redirect(url_for("login"))

    servicio = query_one(
        """
        SELECT s.id_servicio AS id, s.titulo, s.descripcion, s.creditos_hora
        FROM servicio s
        WHERE s.id_servicio=%s AND s.id_usuario=%s
        """,
        (id, session["user_id"]),
    )

    if not servicio:
        flash("Servicio no encontrado.", "danger")
        return redirect(url_for("servicios_list"))

    if request.method == "POST":
        titulo = valid_text(request.form.get("titulo"), 3, 120)
        descripcion = valid_text(request.form.get("descripcion"), 10, 600)
        creditos_hora = valid_int(request.form.get("creditos_hora"), 1, 10)

        if not titulo:
            flash("El título debe tener entre 3 y 120 caracteres.", "danger")
            return render_template("servicios_edit.html", servicio=servicio)
        if not descripcion:
            flash("La descripción debe tener entre 10 y 600 caracteres.", "danger")
            return render_template("servicios_edit.html", servicio=servicio)
        if creditos_hora is None:
            flash("Los créditos por hora deben estar entre 1 y 10.", "danger")
            return render_template("servicios_edit.html", servicio=servicio)

        execute(
            """
            UPDATE servicio
            SET titulo=%s, descripcion=%s, creditos_hora=%s
            WHERE id_servicio=%s AND id_usuario=%s
            """,
            (titulo, descripcion, creditos_hora, id, session["user_id"]),
        )

        flash("Servicio actualizado.", "success")
        return redirect(url_for("servicios_list"))

    return render_template("servicios_edit.html", servicio=servicio)


@app.route("/servicios/delete/<int:id>", methods=["POST"])
def servicios_delete(id):
    """Elimina un servicio propio."""
    if not is_logged_in():
        return redirect(url_for("login"))

    existe = query_one(
        """
        SELECT 1
        FROM servicio
        WHERE id_servicio=%s AND id_usuario=%s
        """,
        (id, session["user_id"]),
    )

    if not existe:
        flash("Servicio no encontrado o sin permisos.", "danger")
        return redirect(url_for("servicios_list"))

    execute("DELETE FROM servicio WHERE id_servicio=%s AND id_usuario=%s", (id, session["user_id"]))
    flash("Servicio eliminado.", "info")
    return redirect(url_for("servicios_list"))


# ============================================================
# Servicios públicos (usuario normal)
# ============================================================
@app.route("/servicios/public")
def servicios_public():
    """Lista servicios de otros usuarios para solicitar intercambio."""
    if not is_logged_in():
        return redirect(url_for("login"))

    servicios = query_all(
        """
        SELECT s.id_servicio AS id,
               s.titulo,
               s.descripcion,
               s.creditos_hora,
               u.nombre AS dueno_nombre,
               u.ubicacion AS dueno_ubicacion,
               u.email AS dueno_email,
               u.id_usuario AS dueno_id
        FROM servicio s
        JOIN usuario u ON u.id_usuario = s.id_usuario
        WHERE s.id_usuario <> %s
        ORDER BY s.id_servicio DESC
        """,
        (session["user_id"],),
    )
    return render_template("servicios_public.html", servicios=servicios)


# ============================================================
# Notificaciones (vistas)
# ============================================================
@app.route("/notificaciones")
def notificaciones():
    """Detalle de notificaciones."""
    if not is_logged_in():
        return redirect(url_for("login"))

    uid = session["user_id"]

    pendientes = query_all(
        f"""
        SELECT i.id_intercambio AS id,
               TO_CHAR(i.fecha_creacion, '{DATE_FMT}') AS fecha_creacion,
               s.titulo AS servicio_solicitado,
               us.nombre AS solicitante_nombre
        FROM intercambio i
        JOIN servicio s ON s.id_servicio=i.id_servicio_solicitado
        JOIN usuario us ON us.id_usuario=i.id_solicitante
        WHERE i.id_proveedor=%s AND i.estado='pendiente'
        ORDER BY i.id_intercambio DESC
        """,
        (uid,),
    )

    activos = query_all(
        f"""
        SELECT i.id_intercambio AS id,
               i.estado,
               TO_CHAR(i.fecha_creacion, '{DATE_FMT}') AS fecha_creacion,
               s.titulo AS servicio_solicitado,
               us.nombre AS solicitante_nombre,
               up.nombre AS proveedor_nombre
        FROM intercambio i
        JOIN servicio s ON s.id_servicio=i.id_servicio_solicitado
        JOIN usuario us ON us.id_usuario=i.id_solicitante
        JOIN usuario up ON up.id_usuario=i.id_proveedor
        WHERE (i.id_solicitante=%s OR i.id_proveedor=%s)
          AND i.estado IN ('confirmado','en_progreso')
        ORDER BY i.id_intercambio DESC
        """,
        (uid, uid),
    )

    return render_template("notificaciones.html", pendientes=pendientes, activos=activos)


# ============================================================
# Intercambios
# ============================================================
@app.route("/intercambios")
def intercambios_list():
    """Lista intercambios enviados y recibidos del usuario."""
    if not is_logged_in():
        return redirect(url_for("login"))

    uid = session["user_id"]

    enviados = query_all(
        f"""
        SELECT i.id_intercambio AS id,
               i.estado,
               TO_CHAR(i.fecha_creacion, '{DATE_FMT}') AS fecha_creacion,
               s.titulo AS servicio_solicitado,
               s.creditos_hora AS costo_creditos_hora,
               up.nombre AS proveedor_nombre,
               i.id_servicio_contraparte,
               sc.titulo AS servicio_contraparte
        FROM intercambio i
        JOIN servicio s ON s.id_servicio = i.id_servicio_solicitado
        JOIN usuario up ON up.id_usuario = i.id_proveedor
        LEFT JOIN servicio sc ON sc.id_servicio = i.id_servicio_contraparte
        WHERE i.id_solicitante = %s
        ORDER BY i.id_intercambio DESC
        """,
        (uid,),
    )

    recibidos = query_all(
        f"""
        SELECT i.id_intercambio AS id,
               i.estado,
               TO_CHAR(i.fecha_creacion, '{DATE_FMT}') AS fecha_creacion,
               s.titulo AS servicio_solicitado,
               s.creditos_hora AS costo_creditos_hora,
               us.nombre AS solicitante_nombre,
               us.email AS solicitante_email,
               i.id_solicitante,
               i.id_servicio_contraparte,
               sc.titulo AS servicio_contraparte
        FROM intercambio i
        JOIN servicio s ON s.id_servicio = i.id_servicio_solicitado
        JOIN usuario us ON us.id_usuario = i.id_solicitante
        LEFT JOIN servicio sc ON sc.id_servicio = i.id_servicio_contraparte
        WHERE i.id_proveedor = %s
        ORDER BY i.id_intercambio DESC
        """,
        (uid,),
    )

    for x in enviados:
        x["estados_permitidos"] = allowed_states_for_user(x["estado"], es_proveedor=False)
    for x in recibidos:
        x["estados_permitidos"] = allowed_states_for_user(x["estado"], es_proveedor=True)

    return render_template("intercambios_list.html", enviados=enviados, recibidos=recibidos, estados=ESTADOS)


@app.route("/intercambios/solicitar/<int:id_servicio>", methods=["POST", "GET"])
def intercambios_solicitar(id_servicio):
    """Solicita un intercambio por un servicio público."""
    if not is_logged_in():
        return redirect(url_for("login"))

    guard = admin_cannot_use("solicitar intercambios")
    if guard:
        return guard

    serv = query_one(
        """
        SELECT s.id_servicio AS id,
               s.titulo,
               s.id_usuario AS dueno_id,
               u.nombre AS dueno_nombre
        FROM servicio s
        JOIN usuario u ON u.id_usuario=s.id_usuario
        WHERE s.id_servicio=%s
        """,
        (id_servicio,),
    )

    if not serv:
        flash("Servicio no encontrado.", "danger")
        return redirect(url_for("servicios_public"))

    if serv["dueno_id"] == session["user_id"]:
        flash("No puedes solicitar intercambio por tu propio servicio.", "warning")
        return redirect(url_for("servicios_public"))

    if request.method == "POST":
        existe = query_one(
            """
            SELECT 1
            FROM intercambio
            WHERE id_servicio_solicitado=%s
              AND id_solicitante=%s
              AND id_proveedor=%s
              AND estado IN ('pendiente','confirmado','en_progreso')
            LIMIT 1
            """,
            (id_servicio, session["user_id"], serv["dueno_id"]),
        )

        if existe:
            flash("Ya tienes una solicitud activa para este servicio.", "info")
            return redirect(url_for("intercambios_list"))

        execute(
            """
            INSERT INTO intercambio (id_servicio_solicitado, id_solicitante, id_proveedor, estado)
            VALUES (%s, %s, %s, 'pendiente')
            """,
            (id_servicio, session["user_id"], serv["dueno_id"]),
        )

        flash(f"Solicitud enviada a {serv['dueno_nombre']}.", "success")
        return redirect(url_for("intercambios_list"))

    return render_template("intercambio_solicitar_confirm.html", serv=serv)


# ============================================================
# Intercambio directo
# ============================================================
@app.route("/intercambios/create-direct", methods=["GET", "POST"])
def intercambios_create_direct():
    """Crea un intercambio directo (sin entrar desde el servicio público)."""
    if not is_logged_in():
        return redirect(url_for("login"))

    guard = admin_cannot_use("crear intercambios")
    if guard:
        return guard

    uid = session["user_id"]

    usuarios = query_all(
        """
        SELECT id_usuario AS id, nombre, ubicacion
        FROM usuario
        WHERE id_usuario <> %s
        ORDER BY nombre ASC
        """,
        (uid,),
    )

    proveedor_id = valid_int(request.args.get("proveedor_id"), 1, 10**9)
    servicios_proveedor = []
    proveedor = None

    if proveedor_id:
        proveedor = query_one("SELECT id_usuario AS id, nombre FROM usuario WHERE id_usuario=%s", (proveedor_id,))
        if proveedor:
            servicios_proveedor = query_all(
                """
                SELECT id_servicio AS id, titulo, creditos_hora
                FROM servicio
                WHERE id_usuario=%s
                ORDER BY id_servicio DESC
                """,
                (proveedor_id,),
            )

    mis_servicios = query_all(
        """
        SELECT id_servicio AS id, titulo, creditos_hora
        FROM servicio
        WHERE id_usuario=%s
        ORDER BY id_servicio DESC
        """,
        (uid,),
    )

    if request.method == "POST":
        proveedor_id = valid_int(request.form.get("proveedor_id"), 1, 10**9)
        id_servicio_solicitado = valid_int(request.form.get("id_servicio_solicitado"), 1, 10**9)
        modo = (request.form.get("modo") or "creditos").strip()

        prov_ok = query_one("SELECT id_usuario AS id, nombre FROM usuario WHERE id_usuario=%s", (proveedor_id,))
        serv_ok = query_one(
            """
            SELECT id_servicio AS id, titulo
            FROM servicio
            WHERE id_servicio=%s AND id_usuario=%s
            """,
            (id_servicio_solicitado, proveedor_id),
        )

        if not (prov_ok and serv_ok):
            flash("Debes seleccionar un usuario y un servicio válido.", "danger")
            return render_template(
                "intercambios_create_direct.html",
                usuarios=usuarios,
                proveedor=proveedor,
                proveedor_id=proveedor_id,
                servicios_proveedor=servicios_proveedor,
                mis_servicios=mis_servicios,
            )

        dup = query_one(
            """
            SELECT 1
            FROM intercambio
            WHERE id_servicio_solicitado=%s
              AND id_solicitante=%s
              AND id_proveedor=%s
              AND estado IN ('pendiente','confirmado','en_progreso')
            LIMIT 1
            """,
            (id_servicio_solicitado, uid, proveedor_id),
        )
        if dup:
            flash("Ya tienes una solicitud activa para ese servicio con ese usuario.", "info")
            return redirect(url_for("intercambios_list"))

        id_contraparte = None

        # Si el solicitante ofrece un servicio a cambio
        if modo == "servicio":
            offer_id = valid_int(request.form.get("id_servicio_contraparte"), 1, 10**9)

            if offer_id:
                mine_ok = query_one("SELECT 1 FROM servicio WHERE id_servicio=%s AND id_usuario=%s", (offer_id, uid))
                if not mine_ok:
                    flash("Servicio ofrecido inválido.", "danger")
                    return redirect(url_for("intercambios_create_direct"))
                id_contraparte = offer_id
            else:
                # Crear servicio nuevo en el momento
                t = valid_text(request.form.get("nuevo_titulo"), 3, 120)
                d = valid_text(request.form.get("nueva_descripcion"), 10, 600)
                c = valid_int(request.form.get("nuevo_creditos_hora"), 1, 10)

                if not (t and d and c is not None):
                    flash("Si eliges ofrecer un servicio nuevo, completa título, descripción y créditos.", "danger")
                    return redirect(url_for("intercambios_create_direct"))

                row = query_one(
                    """
                    INSERT INTO servicio (titulo, descripcion, creditos_hora, id_usuario)
                    VALUES (%s,%s,%s,%s)
                    RETURNING id_servicio
                    """,
                    (t, d, c, uid),
                )
                id_contraparte = row["id_servicio"]

        execute(
            """
            INSERT INTO intercambio (id_servicio_solicitado, id_solicitante, id_proveedor, id_servicio_contraparte, estado)
            VALUES (%s, %s, %s, %s, 'pendiente')
            """,
            (id_servicio_solicitado, uid, proveedor_id, id_contraparte),
        )

        flash("Intercambio directo creado. Queda pendiente de aceptación.", "success")
        return redirect(url_for("intercambios_list"))

    return render_template(
        "intercambios_create_direct.html",
        usuarios=usuarios,
        proveedor=proveedor,
        proveedor_id=proveedor_id,
        servicios_proveedor=servicios_proveedor,
        mis_servicios=mis_servicios,
    )


@app.route("/intercambios/edit/<int:id_intercambio>", methods=["GET", "POST"])
def intercambios_edit(id_intercambio):
    """Solicitante edita intercambio (solo si está pendiente)."""
    if not is_logged_in():
        return redirect(url_for("login"))

    uid = session["user_id"]

    inter = query_one(
        """
        SELECT i.id_intercambio AS id,
               i.estado,
               i.id_solicitante,
               i.id_proveedor,
               i.id_servicio_contraparte,
               s.titulo AS servicio_solicitado,
               s.creditos_hora AS costo_creditos_hora,
               up.nombre AS proveedor_nombre
        FROM intercambio i
        JOIN servicio s ON s.id_servicio=i.id_servicio_solicitado
        JOIN usuario up ON up.id_usuario=i.id_proveedor
        WHERE i.id_intercambio=%s
        """,
        (id_intercambio,),
    )

    if not inter:
        flash("Intercambio no encontrado.", "danger")
        return redirect(url_for("intercambios_list"))

    if uid != inter["id_solicitante"]:
        flash("Solo el solicitante puede editar este intercambio.", "warning")
        return redirect(url_for("intercambios_list"))

    if inter["estado"] != "pendiente":
        flash("Solo puedes editar intercambios en estado 'pendiente'.", "warning")
        return redirect(url_for("intercambios_list"))

    mis_servicios = query_all(
        """
        SELECT id_servicio AS id, titulo, creditos_hora
        FROM servicio
        WHERE id_usuario=%s
        ORDER BY id_servicio DESC
        """,
        (uid,),
    )

    if request.method == "POST":
        modo = (request.form.get("modo") or "creditos").strip()
        id_contra = None

        if modo == "servicio":
            id_contra = valid_int(request.form.get("id_servicio_contraparte"), 1, 10**9)
            if id_contra is None:
                flash("Selecciona un servicio para ofrecer.", "danger")
                return render_template("intercambios_edit.html", inter=inter, mis_servicios=mis_servicios)

            ok = query_one("SELECT 1 FROM servicio WHERE id_servicio=%s AND id_usuario=%s", (id_contra, uid))
            if not ok:
                flash("Servicio ofrecido inválido.", "danger")
                return render_template("intercambios_edit.html", inter=inter, mis_servicios=mis_servicios)

        execute(
            """
            UPDATE intercambio
            SET id_servicio_contraparte=%s
            WHERE id_intercambio=%s AND id_solicitante=%s AND estado='pendiente'
            """,
            (id_contra, id_intercambio, uid),
        )

        flash("Intercambio actualizado.", "success")
        return redirect(url_for("intercambios_list"))

    return render_template("intercambios_edit.html", inter=inter, mis_servicios=mis_servicios)


# ============================================================
# Aceptar intercambio (proveedor)
# ============================================================
@app.route("/intercambios/aceptar/<int:id_intercambio>", methods=["GET", "POST"])
def intercambios_aceptar(id_intercambio):
    """Proveedor acepta intercambio pendiente."""
    if not is_logged_in():
        return redirect(url_for("login"))

    guard = admin_cannot_use("aceptar intercambios")
    if guard:
        return guard

    inter = query_one(
        """
        SELECT i.id_intercambio AS id,
               i.estado,
               i.id_solicitante,
               i.id_proveedor,
               i.id_servicio_contraparte,
               us.nombre AS solicitante_nombre,
               s.titulo AS servicio_solicitado,
               s.creditos_hora AS costo_creditos_hora
        FROM intercambio i
        JOIN usuario us ON us.id_usuario=i.id_solicitante
        JOIN servicio s ON s.id_servicio=i.id_servicio_solicitado
        WHERE i.id_intercambio=%s AND i.id_proveedor=%s
        """,
        (id_intercambio, session["user_id"]),
    )

    if not inter:
        flash("Intercambio no encontrado o no tienes permisos.", "danger")
        return redirect(url_for("intercambios_list"))

    if inter["estado"] != "pendiente":
        flash("Solo puedes aceptar intercambios en estado pendiente.", "warning")
        return redirect(url_for("intercambios_list"))

    servicios_solicitante = query_all(
        """
        SELECT id_servicio AS id, titulo
        FROM servicio
        WHERE id_usuario=%s
        ORDER BY id_servicio DESC
        """,
        (inter["id_solicitante"],),
    )

    if request.method == "POST":
        modo = (request.form.get("modo") or "").strip()

        if modo == "creditos":
            execute(
                """
                UPDATE intercambio
                SET id_servicio_contraparte = NULL,
                    estado='confirmado'
                WHERE id_intercambio=%s AND id_proveedor=%s
                """,
                (id_intercambio, session["user_id"]),
            )

            flash("Intercambio aceptado con pago en créditos. Estado: confirmado.", "success")
            return redirect(url_for("intercambios_list"))

        id_contra = valid_int(request.form.get("id_servicio_contraparte"), 1, 10**9)
        if id_contra is None or not any(s["id"] == id_contra for s in servicios_solicitante):
            flash("Debes seleccionar un servicio válido del solicitante.", "danger")
            return render_template("intercambio_aceptar.html", inter=inter, servicios_solicitante=servicios_solicitante)

        execute(
            """
            UPDATE intercambio
            SET id_servicio_contraparte=%s,
                estado='confirmado'
            WHERE id_intercambio=%s AND id_proveedor=%s
            """,
            (id_contra, id_intercambio, session["user_id"]),
        )

        flash("Intercambio aceptado. Estado: confirmado.", "success")
        return redirect(url_for("intercambios_list"))

    return render_template("intercambio_aceptar.html", inter=inter, servicios_solicitante=servicios_solicitante)


# ============================================================
# Cambiar estado del intercambio
# ============================================================
@app.route("/intercambios/estado/<int:id_intercambio>", methods=["POST"])
def intercambios_estado(id_intercambio):
    """
    Cambia estado del intercambio con reglas:
    - Solo proveedor puede avanzar (confirmado, en_progreso, completado)
    - Validamos transiciones con TRANSICIONES
    - Si completa con "pago en créditos", se transfieren créditos
    """
    if not is_logged_in():
        return redirect(url_for("login"))

    nuevo = (request.form.get("estado") or "").strip()
    if nuevo not in ESTADOS:
        flash("Estado inválido.", "danger")
        return redirect(url_for("intercambios_list"))

    uid = session["user_id"]

    data = query_one(
        """
        SELECT i.id_intercambio,
               i.estado AS estado_actual,
               i.id_solicitante,
               i.id_proveedor,
               i.id_servicio_contraparte,
               s.creditos_hora
        FROM intercambio i
        JOIN servicio s ON s.id_servicio = i.id_servicio_solicitado
        WHERE i.id_intercambio=%s
          AND (i.id_solicitante=%s OR i.id_proveedor=%s)
        """,
        (id_intercambio, uid, uid),
    )

    if not data:
        flash("No tienes permisos para cambiar este intercambio o no existe.", "danger")
        return redirect(url_for("intercambios_list"))

    actual = data["estado_actual"]
    es_proveedor = (uid == data["id_proveedor"])

    if nuevo == actual:
        flash("El intercambio ya está en ese estado.", "info")
        return redirect(url_for("intercambios_list"))

    # ✅ No permitimos saltos que no estén en la máquina de estados
    if nuevo not in TRANSICIONES.get(actual, set()):
        flash(f"No se permite cambiar de '{actual}' a '{nuevo}'.", "warning")
        return redirect(url_for("intercambios_list"))

    # ✅ Solo el proveedor puede avanzar el flujo
    if nuevo in ("confirmado", "en_progreso", "completado") and not es_proveedor:
        flash("Solo el proveedor puede avanzar el estado (confirmar / en_progreso / completar).", "warning")
        return redirect(url_for("intercambios_list"))

    # ✅ Al completar, si es con créditos: transferimos (solicitante paga / proveedor recibe)
    if nuevo == "completado":
        if actual != "en_progreso":
            flash("Para completar, primero debe estar en 'en_progreso'.", "warning")
            return redirect(url_for("intercambios_list"))

        # Si no hay servicio contraparte -> pago por créditos
        if data["id_servicio_contraparte"] is None:
            costo = int(data["creditos_hora"])

            saldo = query_one("SELECT creditos FROM usuario WHERE id_usuario=%s", (data["id_solicitante"],))
            if not saldo or saldo["creditos"] < costo:
                flash(f"Saldo insuficiente. Necesitas {costo} créditos para completar.", "danger")
                return redirect(url_for("intercambios_list"))

            execute("UPDATE usuario SET creditos = creditos - %s WHERE id_usuario=%s", (costo, data["id_solicitante"]))
            execute("UPDATE usuario SET creditos = creditos + %s WHERE id_usuario=%s", (costo, data["id_proveedor"]))

    execute("UPDATE intercambio SET estado=%s WHERE id_intercambio=%s", (nuevo, id_intercambio))
    flash("Estado actualizado.", "success")
    return redirect(url_for("intercambios_list"))


# ============================================================
# Eliminar intercambio
# ============================================================
@app.route("/intercambios/delete/<int:id_intercambio>", methods=["POST"])
def intercambios_delete(id_intercambio):
    """Elimina intercambio (si no está confirmado/en_progreso)."""
    if not is_logged_in():
        return redirect(url_for("login"))

    inter = query_one(
        """
        SELECT id_intercambio, estado, id_solicitante, id_proveedor
        FROM intercambio
        WHERE id_intercambio=%s
        """,
        (id_intercambio,),
    )

    if not inter:
        flash("Intercambio no encontrado.", "danger")
        return redirect(url_for("intercambios_list"))

    uid = session["user_id"]
    if uid != inter["id_solicitante"] and uid != inter["id_proveedor"]:
        flash("No tienes permisos para eliminar este intercambio.", "danger")
        return redirect(url_for("intercambios_list"))

    if inter["estado"] in ("confirmado", "en_progreso"):
        flash("No puedes eliminar un intercambio en 'confirmado' o 'en_progreso'. Cámbialo a 'cancelado' primero.", "warning")
        return redirect(url_for("intercambios_list"))

    execute("DELETE FROM intercambio WHERE id_intercambio=%s", (id_intercambio,))
    flash("Intercambio eliminado.", "info")
    return redirect(url_for("intercambios_list"))


# ============================================================
# Chat por intercambio
# ============================================================
@app.route("/intercambios/<int:id_intercambio>/chat", methods=["GET", "POST"])
def intercambio_chat(id_intercambio):
    """Chat interno por intercambio."""
    if not is_logged_in():
        return redirect(url_for("login"))

    inter = query_one(
        """
        SELECT i.id_intercambio AS id,
               i.estado,
               i.id_solicitante,
               i.id_proveedor,
               ss.titulo AS servicio_solicitado,
               us.nombre AS solicitante_nombre,
               up.nombre AS proveedor_nombre
        FROM intercambio i
        JOIN servicio ss ON ss.id_servicio = i.id_servicio_solicitado
        JOIN usuario us ON us.id_usuario = i.id_solicitante
        JOIN usuario up ON up.id_usuario = i.id_proveedor
        WHERE i.id_intercambio = %s
          AND (i.id_solicitante = %s OR i.id_proveedor = %s)
        """,
        (id_intercambio, session["user_id"], session["user_id"]),
    )

    if not inter:
        flash("No tienes acceso a ese intercambio o no existe.", "danger")
        return redirect(url_for("intercambios_list"))

    # Nombre del "otro" participante (para UI)
    otro_nombre = inter["proveedor_nombre"] if session["user_id"] == inter["id_solicitante"] else inter["solicitante_nombre"]

    if request.method == "POST":
        msg = (request.form.get("mensaje") or "").strip()

        if not msg:
            flash("Escribe un mensaje antes de enviar.", "warning")
            return redirect(url_for("intercambio_chat", id_intercambio=id_intercambio))

        # Evitar mensajes demasiado largos
        if len(msg) > 500:
            msg = msg[:500]

        execute(
            """
            INSERT INTO mensaje_intercambio (id_intercambio, id_autor, mensaje)
            VALUES (%s, %s, %s)
            """,
            (id_intercambio, session["user_id"], msg),
        )

        flash("Mensaje enviado.", "success")
        return redirect(url_for("intercambio_chat", id_intercambio=id_intercambio))

    mensajes = query_all(
        f"""
        SELECT m.id_mensaje AS id,
               m.mensaje,
               TO_CHAR(m.fecha, '{DATE_FMT}') AS fecha,
               u.id_usuario AS autor_id,
               u.nombre AS autor_nombre
        FROM mensaje_intercambio m
        JOIN usuario u ON u.id_usuario = m.id_autor
        WHERE m.id_intercambio = %s
        ORDER BY m.fecha ASC, m.id_mensaje ASC
        """,
        (id_intercambio,),
    )

    return render_template("chat_intercambio.html", intercambio=inter, mensajes=mensajes, otro_nombre=otro_nombre)


# ============================================================
# Valoraciones (usuario + moderación admin)
# ============================================================
@app.route("/valoraciones")
def valoraciones_list():
    """
    Vista de valoraciones.
    - Admin: ve TODAS (moderación).
    - Usuario: ve hechas y recibidas.
    """
    if not is_logged_in():
        return redirect(url_for("login"))

    uid = session["user_id"]

    if is_admin():
        # ✅ ADMIN: ve todas
        todas = query_all(
            f"""
            SELECT v.id_valoracion AS id,
                   v.id_intercambio,
                   v.puntuacion,
                   v.comentario,
                   TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
                   ua.nombre AS autor,
                   ud.nombre AS destinatario
            FROM valoracion v
            JOIN usuario ua ON ua.id_usuario=v.id_autor
            JOIN usuario ud ON ud.id_usuario=v.id_destinatario
            ORDER BY v.id_valoracion DESC
            """
        )
        return render_template("valoraciones_list.html", todas=todas)

    # ✅ USUARIO: hechas
    hechas = query_all(
        f"""
        SELECT v.id_valoracion AS id,
               v.id_intercambio,
               v.puntuacion,
               v.comentario,
               TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
               ud.nombre AS destinatario
        FROM valoracion v
        JOIN usuario ud ON ud.id_usuario=v.id_destinatario
        WHERE v.id_autor=%s
        ORDER BY v.id_valoracion DESC
        """,
        (uid,),
    )

    # ✅ USUARIO: recibidas
    recibidas = query_all(
        f"""
        SELECT v.id_valoracion AS id,
               v.id_intercambio,
               v.puntuacion,
               v.comentario,
               TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
               ua.nombre AS autor
        FROM valoracion v
        JOIN usuario ua ON ua.id_usuario=v.id_autor
        WHERE v.id_destinatario=%s
        ORDER BY v.id_valoracion DESC
        """,
        (uid,),
    )

    return render_template("valoraciones_list.html", hechas=hechas, recibidas=recibidas)


@app.route("/admin/valoraciones/edit/<int:id_valoracion>", methods=["GET", "POST"])
def admin_valoraciones_edit(id_valoracion):
    """Admin: edita cualquier valoración (moderación)."""
    guard = admin_required()
    if guard:
        return guard

    v = query_one(
        f"""
        SELECT v.id_valoracion AS id,
               v.id_intercambio,
               v.puntuacion,
               v.comentario,
               TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
               ua.nombre AS autor,
               ud.nombre AS destinatario
        FROM valoracion v
        JOIN usuario ua ON ua.id_usuario = v.id_autor
        JOIN usuario ud ON ud.id_usuario = v.id_destinatario
        WHERE v.id_valoracion=%s
        """,
        (id_valoracion,),
    )

    if not v:
        flash("Valoración no encontrada.", "danger")
        return redirect(url_for("valoraciones_list"))

    if request.method == "POST":
        puntuacion = valid_int(request.form.get("puntuacion"), 1, 5)
        comentario = (request.form.get("comentario") or "").strip()
        if len(comentario) > 300:
            comentario = comentario[:300]

        if puntuacion is None:
            flash("La puntuación debe estar entre 1 y 5.", "danger")
            return render_template("valoraciones_edit.html", v=v)

        execute(
            """
            UPDATE valoracion
            SET puntuacion=%s, comentario=%s
            WHERE id_valoracion=%s
            """,
            (puntuacion, comentario, id_valoracion),
        )

        flash("Valoración actualizada por moderación.", "success")
        return redirect(url_for("valoraciones_list"))

    return render_template("valoraciones_edit.html", v=v)


@app.route("/admin/valoraciones/delete/<int:id_valoracion>", methods=["POST"])
def admin_valoraciones_delete(id_valoracion):
    """Admin: elimina cualquier valoración."""
    guard = admin_required()
    if guard:
        return guard

    ok = query_one("SELECT 1 FROM valoracion WHERE id_valoracion=%s", (id_valoracion,))
    if not ok:
        flash("Valoración no encontrada.", "danger")
        return redirect(url_for("valoraciones_list"))

    execute("DELETE FROM valoracion WHERE id_valoracion=%s", (id_valoracion,))
    flash("Valoración eliminada por moderación.", "info")
    return redirect(url_for("valoraciones_list"))


@app.route("/valoraciones/create/<int:id_intercambio>", methods=["GET", "POST"])
def valoraciones_create(id_intercambio):
    """Usuario crea valoración (solo si intercambio completado)."""
    if not is_logged_in():
        return redirect(url_for("login"))

    guard = admin_cannot_use("crear valoraciones")
    if guard:
        return guard

    inter = query_one(
        """
        SELECT id_intercambio, estado, id_solicitante, id_proveedor
        FROM intercambio
        WHERE id_intercambio=%s AND (id_solicitante=%s OR id_proveedor=%s)
        """,
        (id_intercambio, session["user_id"], session["user_id"]),
    )

    if not inter:
        flash("Intercambio no encontrado o sin permisos.", "danger")
        return redirect(url_for("intercambios_list"))

    if inter["estado"] != "completado":
        flash("Solo puedes valorar intercambios completados.", "warning")
        return redirect(url_for("intercambios_list"))

    autor = session["user_id"]
    destinatario = inter["id_proveedor"] if autor == inter["id_solicitante"] else inter["id_solicitante"]

    ya = query_one(
        """
        SELECT 1 FROM valoracion
        WHERE id_intercambio=%s AND id_autor=%s
        """,
        (id_intercambio, autor),
    )
    if ya:
        flash("Ya valoraste este intercambio.", "info")
        return redirect(url_for("valoraciones_list"))

    if request.method == "POST":
        puntuacion = valid_int(request.form.get("puntuacion"), 1, 5)
        comentario = (request.form.get("comentario") or "").strip()
        if len(comentario) > 300:
            comentario = comentario[:300]

        if puntuacion is None:
            flash("La puntuación debe estar entre 1 y 5.", "danger")
            return render_template("valoraciones_create.html", id_intercambio=id_intercambio)

        execute(
            """
            INSERT INTO valoracion (id_intercambio, id_autor, id_destinatario, puntuacion, comentario)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (id_intercambio, autor, destinatario, puntuacion, comentario),
        )

        flash("Valoración registrada.", "success")
        return redirect(url_for("valoraciones_list"))

    return render_template("valoraciones_create.html", id_intercambio=id_intercambio)


@app.route("/valoraciones/edit/<int:id_valoracion>", methods=["GET", "POST"])
def valoraciones_edit(id_valoracion):
    """Usuario edita solo valoraciones que él creó."""
    if not is_logged_in():
        return redirect(url_for("login"))

    v = query_one(
        f"""
        SELECT v.id_valoracion AS id,
               v.id_intercambio,
               v.puntuacion,
               v.comentario,
               TO_CHAR(v.fecha_valoracion, '{DATE_FMT}') AS fecha,
               ud.nombre AS destinatario
        FROM valoracion v
        JOIN usuario ud ON ud.id_usuario = v.id_destinatario
        WHERE v.id_valoracion=%s AND v.id_autor=%s
        """,
        (id_valoracion, session["user_id"]),
    )

    if not v:
        flash("Valoración no encontrada o sin permisos.", "danger")
        return redirect(url_for("valoraciones_list"))

    if request.method == "POST":
        puntuacion = valid_int(request.form.get("puntuacion"), 1, 5)
        comentario = (request.form.get("comentario") or "").strip()
        if len(comentario) > 300:
            comentario = comentario[:300]

        if puntuacion is None:
            flash("La puntuación debe estar entre 1 y 5.", "danger")
            return render_template("valoraciones_edit.html", v=v)

        execute(
            """
            UPDATE valoracion
            SET puntuacion=%s, comentario=%s
            WHERE id_valoracion=%s AND id_autor=%s
            """,
            (puntuacion, comentario, id_valoracion, session["user_id"]),
        )

        flash("Valoración actualizada.", "success")
        return redirect(url_for("valoraciones_list"))

    return render_template("valoraciones_edit.html", v=v)


@app.route("/valoraciones/delete/<int:id_valoracion>", methods=["POST"])
def valoraciones_delete(id_valoracion):
    """Usuario elimina solo valoraciones que él creó."""
    if not is_logged_in():
        return redirect(url_for("login"))

    ok = query_one(
        """
        SELECT 1
        FROM valoracion
        WHERE id_valoracion=%s AND id_autor=%s
        """,
        (id_valoracion, session["user_id"]),
    )

    if not ok:
        flash("Valoración no encontrada o sin permisos.", "danger")
        return redirect(url_for("valoraciones_list"))

    execute("DELETE FROM valoracion WHERE id_valoracion=%s AND id_autor=%s", (id_valoracion, session["user_id"]))
    flash("Valoración eliminada.", "info")
    return redirect(url_for("valoraciones_list"))


if __name__ == "__main__":
    app.run()

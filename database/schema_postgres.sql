-- ============================================
-- Intercambio Dorado - PostgreSQL Schema FINAL
-- ============================================
-- ----------------------------
-- Roles
-- ----------------------------
CREATE TABLE IF NOT EXISTS rol (
  id_rol SERIAL PRIMARY KEY,
  nombre_rol VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO rol (nombre_rol)
VALUES ('admin'), ('usuario')
ON CONFLICT (nombre_rol) DO NOTHING;

-- ----------------------------
-- Usuarios
-- ----------------------------
CREATE TABLE IF NOT EXISTS usuario (
  id_usuario SERIAL PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  email VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  edad INT NOT NULL CHECK (edad >= 18 AND edad <= 120),
  ubicacion VARCHAR(100) NOT NULL,
  creditos INT NOT NULL DEFAULT 0 CHECK (creditos >= 0),
  id_rol INT NOT NULL REFERENCES rol(id_rol)
);

-- ----------------------------
-- Habilidades (opcional)
-- ----------------------------
CREATE TABLE IF NOT EXISTS habilidad (
  id_habilidad SERIAL PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS usuario_habilidad (
  id_usuario INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  id_habilidad INT NOT NULL REFERENCES habilidad(id_habilidad) ON DELETE CASCADE,
  PRIMARY KEY (id_usuario, id_habilidad)
);

CREATE INDEX IF NOT EXISTS idx_usuario_habilidad_usuario ON usuario_habilidad (id_usuario);
CREATE INDEX IF NOT EXISTS idx_usuario_habilidad_habilidad ON usuario_habilidad (id_habilidad);

-- ----------------------------
-- Servicios
-- ----------------------------
CREATE TABLE IF NOT EXISTS servicio (
  id_servicio SERIAL PRIMARY KEY,
  titulo VARCHAR(120) NOT NULL,
  descripcion TEXT NOT NULL,
  creditos_hora INT NOT NULL CHECK (creditos_hora BETWEEN 1 AND 10),
  id_usuario INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_servicio_usuario ON servicio (id_usuario);

-- ----------------------------
-- Intercambios
-- ----------------------------
CREATE TABLE IF NOT EXISTS intercambio (
  id_intercambio SERIAL PRIMARY KEY,
  id_servicio_solicitado INT NOT NULL REFERENCES servicio(id_servicio) ON DELETE CASCADE,
  id_solicitante INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  id_proveedor INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  id_servicio_contraparte INT NULL REFERENCES servicio(id_servicio) ON DELETE SET NULL,
  estado VARCHAR(20) NOT NULL CHECK (estado IN ('pendiente','confirmado','en_progreso','completado','cancelado')),
  fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_intercambio_solicitante ON intercambio (id_solicitante);
CREATE INDEX IF NOT EXISTS idx_intercambio_proveedor ON intercambio (id_proveedor);
CREATE INDEX IF NOT EXISTS idx_intercambio_estado ON intercambio (estado);
CREATE INDEX IF NOT EXISTS idx_intercambio_fecha ON intercambio (fecha_creacion);

-- ----------------------------
-- Valoraciones
-- Cada usuario valora 1 vez por intercambio
-- ----------------------------
CREATE TABLE IF NOT EXISTS valoracion (
  id_valoracion SERIAL PRIMARY KEY,
  id_intercambio INT NOT NULL REFERENCES intercambio(id_intercambio) ON DELETE CASCADE,
  id_autor INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  id_destinatario INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  puntuacion INT NOT NULL CHECK (puntuacion BETWEEN 1 AND 5),
  comentario TEXT NULL,
  fecha_valoracion TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (id_intercambio, id_autor)
);

CREATE INDEX IF NOT EXISTS idx_valoracion_destinatario ON valoracion (id_destinatario);
CREATE INDEX IF NOT EXISTS idx_valoracion_autor ON valoracion (id_autor);
CREATE INDEX IF NOT EXISTS idx_valoracion_fecha ON valoracion (fecha_valoracion);

-- ----------------------------
-- Mensajes del intercambio (Chat simple)
-- ----------------------------
CREATE TABLE IF NOT EXISTS mensaje_intercambio (
  id_mensaje SERIAL PRIMARY KEY,
  id_intercambio INT NOT NULL REFERENCES intercambio(id_intercambio) ON DELETE CASCADE,
  id_autor INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  mensaje TEXT NOT NULL,
  fecha TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Índices para listar más rápido
CREATE INDEX IF NOT EXISTS idx_mensaje_intercambio_intercambio ON mensaje_intercambio (id_intercambio);
CREATE INDEX IF NOT EXISTS idx_mensaje_intercambio_fecha ON mensaje_intercambio (fecha);

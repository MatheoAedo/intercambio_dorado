CREATE TABLE IF NOT EXISTS rol (
  id_rol SERIAL PRIMARY KEY,
  nombre_rol VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO rol (nombre_rol) VALUES ('admin'), ('usuario')
ON CONFLICT (nombre_rol) DO NOTHING;

CREATE TABLE IF NOT EXISTS usuario (
  id_usuario SERIAL PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  email VARCHAR(100) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,
  edad INT NOT NULL CHECK (edad >= 18 AND edad <= 120),
  ubicacion VARCHAR(100) NOT NULL,
  creditos INT NOT NULL DEFAULT 0 CHECK (creditos >= 0),
  id_rol INT NOT NULL REFERENCES rol(id_rol)
);

CREATE TABLE IF NOT EXISTS habilidad (
  id_habilidad SERIAL PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS usuario_habilidade (
  id_usuario INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  id_habilidad INT NOT NULL REFERENCES habilidad(id_habilidad) ON DELETE CASCADE,
  PRIMARY KEY (id_usuario, id_habilidad)
);

CREATE TABLE IF NOT EXISTS servicio (
  id_servicio SERIAL PRIMARY KEY,
  titulo VARCHAR(100) NOT NULL,
  descripcion TEXT NOT NULL,
  creditos_hora INT NOT NULL CHECK (creditos_hora BETWEEN 1 AND 10),
  id_usuario INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS intercambio (
  id_intercambio SERIAL PRIMARY KEY,
  id_servicio INT NOT NULL REFERENCES servicio(id_servicio) ON DELETE CASCADE,
  id_solicitante INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
  estado VARCHAR(20) NOT NULL CHECK (estado IN ('pendiente','confirmado','en_progreso','completado','cancelado')),
  fecha TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS valoracion (
  id_valoracion SERIAL PRIMARY KEY,
  puntuacion INT NOT NULL CHECK (puntuacion BETWEEN 1 AND 5),
  comentario TEXT NULL,
  id_intercambio INT NOT NULL REFERENCES intercambio(id_intercambio) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documento_verificacion (
  id_documento SERIAL PRIMARY KEY,
  tipo VARCHAR(100) NOT NULL,
  archivo VARCHAR(200) NOT NULL,
  id_usuario INT NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE
);

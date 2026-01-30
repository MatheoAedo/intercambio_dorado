-- ============================================
-- Intercambio Dorado - Seed de datos DEMO
-- Usuarios + Servicios
-- ============================================

-- --------------------------------------------
-- Roles (por seguridad, idempotente)
-- --------------------------------------------
INSERT INTO rol (nombre_rol)
VALUES ('admin'), ('usuario')
ON CONFLICT (nombre_rol) DO NOTHING;


-- --------------------------------------------
-- Usuarios DEMO
-- --------------------------------------------

-- ADMIN
-- email: admin@mail.com
-- pass : Admin1234!
INSERT INTO usuario (nombre, email, password_hash, edad, ubicacion, creditos, id_rol)
VALUES (
  'Admin',
  'admin@mail.com',
  'scrypt:32768:8:1$w0XW1zxo34SyimTu$4aa4f608f90f19153f831d4da014e3d1eaec6c8aa78292a096aa5521eb55e6e5ac2ac0f8f498d109042ff550574f0c83ea40453aab19cb462e5289d25814e03b',
  60,
  'Santiago',
  999,
  (SELECT id_rol FROM rol WHERE nombre_rol = 'admin')
)
ON CONFLICT (email) DO NOTHING;


-- USUARIO DEMO (Adulto mayor)
-- email: rosa@mail.com
-- pass : Demo1234!
INSERT INTO usuario (nombre, email, password_hash, edad, ubicacion, creditos, id_rol)
VALUES (
  'Rosa',
  'rosa@mail.com',
  'scrypt:32768:8:1$uytQguXHvIsPAfm0$79a857ae873d054780223da6fc56c7b2021769cc99f3468eb7338a81a63541748123e1283c6b4afb7059f4391665142bf82505d7918838277cc0644a95871ecf',
  70,
  'Santiago',
  10,
  (SELECT id_rol FROM rol WHERE nombre_rol = 'usuario')
)
ON CONFLICT (email) DO NOTHING;


-- --------------------------------------------
-- Servicios DEMO (de Rosa)
-- --------------------------------------------
INSERT INTO servicio (titulo, descripcion, creditos_hora, id_usuario)
VALUES
(
  'Clases de celular',
  'Ayuda para WhatsApp, videollamadas y uso básico del celular.',
  2,
  (SELECT id_usuario FROM usuario WHERE email = 'rosa@mail.com')
),
(
  'Acompañamiento médico',
  'Acompañamiento a consultas médicas y apoyo en trámites.',
  3,
  (SELECT id_usuario FROM usuario WHERE email = 'rosa@mail.com')
)
ON CONFLICT DO NOTHING;


-- Usuarios demo + Servicios demo


-- 1) Insertar roles
INSERT INTO rol (nombre_rol)
VALUES ('admin'), ('usuario')
ON CONFLICT (nombre_rol) DO NOTHING;

INSERT INTO usuario (nombre, email, password_hash, edad, ubicacion, creditos, id_rol)
VALUES
(
  'Admin',
  'admin@mail.com',
  'pbkdf2:sha256:600000$demo$0b9a6d0a0d4b1f5c2f1c0d6e3a9a9f2c2e2b0a1f0b1c2d3e4f5a6b7c8d9e0f1a',
  60,
  'Santiago',
  999,
  (SELECT id_rol FROM rol WHERE nombre_rol='admin')
),
(
  'Rosa',
  'rosa@mail.com',
  'pbkdf2:sha256:600000$demo$0b9a6d0a0d4b1f5c2f1c0d6e3a9a9f2c2e2b0a1f0b1c2d3e4f5a6b7c8d9e0f1a',
  70,
  'Santiago',
  10,
  (SELECT id_rol FROM rol WHERE nombre_rol='usuario')
)
ON CONFLICT (email) DO NOTHING;

-- 3) Insertar servicios demo
INSERT INTO servicio (titulo, descripcion, creditos_hora, id_usuario)
VALUES
(
  'Clases de celular',
  'Ayuda para WhatsApp, videollamadas y fotos.',
  2,
  (SELECT id_usuario FROM usuario WHERE email='rosa@mail.com')
),
(
  'Acompañamiento médico',
  'Acompañar a consulta y ayudar con trámites.',
  3,
  (SELECT id_usuario FROM usuario WHERE email='rosa@mail.com')
)
ON CONFLICT DO NOTHING;

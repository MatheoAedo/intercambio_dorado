INSERT INTO usuario (nombre, email, password, edad, ubicacion, creditos, id_rol)
VALUES
('Admin', 'admin@mail.com', 'Admin1234!', 30, 'Santiago', 999, (SELECT id_rol FROM rol WHERE nombre_rol='admin')),
('Rosa', 'rosa@mail.com', 'Demo1234!', 70, 'Santiago', 10, (SELECT id_rol FROM rol WHERE nombre_rol='usuario'))
ON CONFLICT (email) DO NOTHING;

INSERT INTO servicio (titulo, descripcion, creditos_hora, id_usuario)
VALUES
('Clases de celular', 'Ayuda para WhatsApp, videollamadas y fotos.', 2, (SELECT id_usuario FROM usuario WHERE email='rosa@mail.com')),
('Acompañamiento médico', 'Acompañar a consulta y ayudar con trámites.', 3, (SELECT id_usuario FROM usuario WHERE email='rosa@mail.com'));

-- Étape 8 : tournois saisis par un utilisateur connecté (source = 'local').
-- created_by sans clé étrangère : l'utilisateur vit dans user_db, une autre base.
ALTER TABLE tournament
  ADD COLUMN created_by INT NULL,
  ADD COLUMN detail_level ENUM('winner', 'top16') NULL

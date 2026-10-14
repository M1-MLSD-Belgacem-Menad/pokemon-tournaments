-- Étape 9 : objet tenu par chaque Pokémon d'équipe. NULL pour les données importées avant (et les tournois locaux).
CREATE TABLE item (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(100) NOT NULL UNIQUE
);

ALTER TABLE team_pokemon
  ADD COLUMN item_id INT NULL,
  ADD FOREIGN KEY (item_id) REFERENCES item (id)

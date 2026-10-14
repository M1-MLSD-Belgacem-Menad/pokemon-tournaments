-- Étape 9 : talent de chaque Pokémon d'équipe. NULL pour les données importées avant (et les tournois locaux).
CREATE TABLE ability (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(100) NOT NULL UNIQUE
);

ALTER TABLE team_pokemon
  ADD COLUMN ability_id INT NULL,
  ADD FOREIGN KEY (ability_id) REFERENCES ability (id)

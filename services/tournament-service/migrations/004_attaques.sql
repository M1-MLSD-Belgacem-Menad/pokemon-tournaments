-- Étape 9 : attaques de chaque Pokémon d'équipe (déjà envoyées par le scraper).
-- Type, catégorie et puissance viendront de PokéAPI en 007 (003 passe avant 004 sur une base neuve).
CREATE TABLE move (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE team_pokemon_move (
  team_pokemon_id  INT     NOT NULL,
  slot             TINYINT NOT NULL CHECK (slot BETWEEN 1 AND 4),
  move_id          INT     NOT NULL,
  PRIMARY KEY (team_pokemon_id, slot),
  FOREIGN KEY (team_pokemon_id) REFERENCES team_pokemon (id) ON DELETE CASCADE,
  FOREIGN KEY (move_id) REFERENCES move (id)
)

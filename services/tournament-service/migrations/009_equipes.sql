-- Étape 10 : équipes sauvegardées par les utilisateurs (user_id sans clé étrangère : il vit dans user_db).
-- Les Pokémon légaux d'un format ne sont pas stockés : ce sont ceux vus dans ses tournois scrapés (décision 6).
CREATE TABLE saved_team (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  user_id     INT          NOT NULL,
  name        VARCHAR(100) NOT NULL,
  format_id   INT          NOT NULL,
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX (user_id),
  FOREIGN KEY (format_id) REFERENCES format (id)
);

CREATE TABLE saved_team_pokemon (
  saved_team_id  INT     NOT NULL,
  slot           TINYINT NOT NULL CHECK (slot BETWEEN 1 AND 6),
  pokemon_id     INT     NOT NULL,
  PRIMARY KEY (saved_team_id, slot),
  UNIQUE (saved_team_id, pokemon_id),
  FOREIGN KEY (saved_team_id) REFERENCES saved_team (id) ON DELETE CASCADE,
  FOREIGN KEY (pokemon_id) REFERENCES pokemon (id)
)

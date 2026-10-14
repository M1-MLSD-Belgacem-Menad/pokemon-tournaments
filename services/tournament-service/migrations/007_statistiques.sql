-- Étape 9 : statistiques de base des espèces et détails des attaques, depuis PokéAPI.
-- Une espèce sans ligne ici, ou une attaque sans catégorie, n'est pas encore enrichie.
CREATE TABLE pokemon_stats (
  pokemon_id  INT      PRIMARY KEY,
  hp          SMALLINT NOT NULL,
  atk         SMALLINT NOT NULL,
  def         SMALLINT NOT NULL,
  spa         SMALLINT NOT NULL,
  spd         SMALLINT NOT NULL,
  spe         SMALLINT NOT NULL,
  FOREIGN KEY (pokemon_id) REFERENCES pokemon (id)
);

ALTER TABLE move
  ADD COLUMN type_id   INT NULL,
  ADD COLUMN category  ENUM('physical', 'special', 'status') NULL,
  ADD COLUMN power     SMALLINT NULL,
  ADD FOREIGN KEY (type_id) REFERENCES type (id)

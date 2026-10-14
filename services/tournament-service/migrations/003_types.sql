-- Étape 9 : types de chaque espèce (1 ou 2), chargés depuis PokéAPI par `scraper.py enrich`.
-- Sur une base créée avant, 003 passe après 008 et 009 : rien n'en dépend.
CREATE TABLE type (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE pokemon_type (
  pokemon_id  INT     NOT NULL,
  slot        TINYINT NOT NULL CHECK (slot BETWEEN 1 AND 2),
  type_id     INT     NOT NULL,
  PRIMARY KEY (pokemon_id, slot),
  FOREIGN KEY (pokemon_id) REFERENCES pokemon (id),
  FOREIGN KEY (type_id) REFERENCES type (id)
)

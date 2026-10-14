-- Schéma v1 (étape 1 : noms uniquement). Voir docs/02-architecture.md.
-- Les clés étrangères sont déclarées au niveau de la table : InnoDB ignore les REFERENCES en ligne.

CREATE TABLE format (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  code        VARCHAR(50)  NOT NULL UNIQUE,
  name        VARCHAR(100) NOT NULL,
  is_current  BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE pokemon (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(100) NOT NULL UNIQUE
);

-- source_id : identifiant du joueur sur le site source (NULL pour un tournoi local)
CREATE TABLE player (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  source_id  VARCHAR(100) UNIQUE,
  name       VARCHAR(100) NOT NULL,
  country    CHAR(2)
);

CREATE TABLE tournament (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(200) NOT NULL,
  date          DATE         NOT NULL,
  format_id     INT          NOT NULL,
  source        ENUM('scraped', 'local') NOT NULL,
  source_url    VARCHAR(500) UNIQUE,
  player_count  INT,
  FOREIGN KEY (format_id) REFERENCES format (id)
);

CREATE TABLE standing (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  tournament_id  INT NOT NULL,
  player_id      INT NOT NULL,
  placement      INT NOT NULL,
  wins           INT,
  losses         INT,
  ties           INT,
  UNIQUE (tournament_id, placement),
  UNIQUE (tournament_id, player_id),
  FOREIGN KEY (tournament_id) REFERENCES tournament (id) ON DELETE CASCADE,
  FOREIGN KEY (player_id) REFERENCES player (id)
);

-- Matchs des joueurs du top 16. player2_id NULL = bye, winner_id NULL = nul ou double défaite.
CREATE TABLE game_match (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  tournament_id  INT NOT NULL,
  phase          INT NOT NULL DEFAULT 1,
  round          INT NOT NULL,
  player1_id     INT NOT NULL,
  player2_id     INT,
  winner_id      INT,
  FOREIGN KEY (tournament_id) REFERENCES tournament (id) ON DELETE CASCADE,
  FOREIGN KEY (player1_id) REFERENCES player (id),
  FOREIGN KEY (player2_id) REFERENCES player (id),
  FOREIGN KEY (winner_id) REFERENCES player (id)
);

CREATE TABLE team_pokemon (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  standing_id  INT     NOT NULL,
  slot         TINYINT NOT NULL CHECK (slot BETWEEN 1 AND 6),
  pokemon_id   INT     NOT NULL,
  UNIQUE (standing_id, slot),
  FOREIGN KEY (standing_id) REFERENCES standing (id) ON DELETE CASCADE,
  FOREIGN KEY (pokemon_id) REFERENCES pokemon (id)
)

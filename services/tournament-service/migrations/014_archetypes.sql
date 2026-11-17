-- Archétypes (familles d'équipes) par format (docs/07-apprentissage.md) : k-means sphérique sur les équipes,
-- entraîné par `python -m app.train` (CronJob). Comptes bruts stockés : l'API calcule winrate et intervalles
-- avec app/stats.py, comme ailleurs. Les id changent à chaque entraînement : l'interface affiche le nom.
CREATE TABLE archetype (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  format_id   INT          NOT NULL,
  name        VARCHAR(200) NOT NULL,  -- 1 à 3 Pokémon caractéristiques, ex. « Whimsicott / Charizard / Garchomp »
  divers      BOOLEAN      NOT NULL,  -- groupe fourre-tout sans cœur commun : « pas d'archétype net »
  teams       INT          NOT NULL,
  wins        INT          NOT NULL,
  losses      INT          NOT NULL,
  top_teams   INT          NOT NULL,  -- équipes des tournois d'au moins 32 joueurs
  top_cut     INT          NOT NULL,  -- parmi elles, celles classées dans le top 8
  trained_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (format_id) REFERENCES format (id)
);

-- Score d'une équipe pour un archétype = somme des poids de ses Pokémon (poids = IDF × centre du groupe).
CREATE TABLE archetype_weight (
  archetype_id  INT    NOT NULL,
  pokemon_id    INT    NOT NULL,
  weight        DOUBLE NOT NULL,
  share         DOUBLE NOT NULL,  -- part des équipes de l'archétype qui jouent ce Pokémon
  PRIMARY KEY (archetype_id, pokemon_id),
  FOREIGN KEY (archetype_id) REFERENCES archetype (id) ON DELETE CASCADE,
  FOREIGN KEY (pokemon_id) REFERENCES pokemon (id)
)

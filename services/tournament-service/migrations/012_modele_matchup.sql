-- Modèle de prédiction de matchs (docs/07-apprentissage.md) : une régression logistique par format,
-- entraînée par `python -m app.train` (CronJob), lue par l'API sans scikit-learn.
-- Les métriques sont celles du jeu de test (tournois les plus récents), avant le réentraînement sur tout.
CREATE TABLE matchup_model (
  format_id      INT PRIMARY KEY,
  trained_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  train_matches  INT    NOT NULL,
  test_matches   INT    NOT NULL,
  c              DOUBLE NOT NULL,
  log_loss       DOUBLE NOT NULL,
  brier          DOUBLE NOT NULL,
  accuracy       DOUBLE NOT NULL,
  field_score    DOUBLE NOT NULL,
  FOREIGN KEY (format_id) REFERENCES format (id)
);

-- Poids de chaque Pokémon (positif : il fait gagner) et nombre de matchs où il apparaît.
CREATE TABLE matchup_weight (
  format_id   INT    NOT NULL,
  pokemon_id  INT    NOT NULL,
  weight      DOUBLE NOT NULL,
  matches     INT    NOT NULL,
  PRIMARY KEY (format_id, pokemon_id),
  FOREIGN KEY (format_id) REFERENCES matchup_model (format_id) ON DELETE CASCADE,
  FOREIGN KEY (pokemon_id) REFERENCES pokemon (id)
)

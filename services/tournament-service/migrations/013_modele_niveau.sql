-- Modèle de matchup en deux étages (docs/07-apprentissage.md) : niveau des joueurs (Elo) en décalage fixe,
-- puis poids des Pokémon. Mesures du jeu de test en plus : log-loss du niveau seul, intervalle à 95 %
-- (bootstrap par tournoi) de l'écart de log-loss entre le modèle complet et le niveau seul, et nombre de
-- tournois de test (avec un seul, l'intervalle n'a pas de sens). field_score ne sert plus.
-- Les modèles déjà entraînés n'ont pas ces mesures : supprimés (poids compris, en cascade), le prochain
-- entraînement les recrée.
DELETE FROM matchup_model;
ALTER TABLE matchup_model
  ADD COLUMN test_tournaments INT    NOT NULL,
  ADD COLUMN elo_log_loss     DOUBLE NOT NULL,
  ADD COLUMN delta_low        DOUBLE NOT NULL,
  ADD COLUMN delta_high       DOUBLE NOT NULL,
  DROP COLUMN field_score;

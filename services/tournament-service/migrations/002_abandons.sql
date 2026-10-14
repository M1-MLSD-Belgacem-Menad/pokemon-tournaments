-- Tous les joueurs d'un tournoi sont enregistrés, pas seulement le top 16 (décision du 14/10, pour des winrates non biaisés).
-- Un joueur qui abandonne n'a pas de place finale : placement devient facultatif (UNIQUE accepte plusieurs NULL).
ALTER TABLE standing MODIFY placement INT NULL

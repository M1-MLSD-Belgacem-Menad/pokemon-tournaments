-- Dans un tableau à élimination directe, des joueurs partagent une place (deux 3es, quatre 5es...).
-- L'index unique (tournament_id, placement) de 001 faisait refuser ces tournois à chaque scraping.
-- Un joueur reste classé une seule fois par tournoi (index tournament_id_2), qui sert aussi la clé étrangère.
ALTER TABLE standing DROP INDEX tournament_id

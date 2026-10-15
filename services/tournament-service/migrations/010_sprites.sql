-- Sprite PokéAPI de chaque espèce, chargé avec ses statistiques.
-- Une espèce sans sprite est redemandée par `scraper.py enrich`, comme une espèce sans statistiques.
ALTER TABLE pokemon_stats ADD COLUMN sprite_url VARCHAR(255) NULL

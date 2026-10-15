#!/bin/bash
# Lancé par l'image mysql au premier démarrage seulement (volume vide), en Compose comme sur Kubernetes.
# tournament_db et son compte viennent de MYSQL_DATABASE / MYSQL_USER ; ici, la base du user-service.
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE DATABASE IF NOT EXISTS user_db;
CREATE USER IF NOT EXISTS '$USER_DB_USER'@'%' IDENTIFIED BY '$USER_DB_PASSWORD';
GRANT ALL PRIVILEGES ON user_db.* TO '$USER_DB_USER'@'%';
SQL

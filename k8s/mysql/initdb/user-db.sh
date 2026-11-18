#!/bin/bash
# Lancé par l'image mysql au premier démarrage seulement (volume vide), en Compose comme sur Kubernetes.
# tournament_db et son compte viennent de MYSQL_DATABASE / MYSQL_USER ; ici, la base du user-service.

# Sur Kubernetes, la ConfigMap n'est pas exécutable : l'entrypoint source ce fichier, et docker_process_sql
# vise le socket de son serveur temporaire (le client mysql par défaut ne le trouve pas toujours).
# En Compose le fichier est exécuté, sans les fonctions de l'entrypoint : client mysql direct.
run_sql() {
  if declare -F docker_process_sql >/dev/null; then
    docker_process_sql
  else
    mysql -uroot -p"$MYSQL_ROOT_PASSWORD"
  fi
}

# Le compte et le mot de passe sont écrits tels quels dans le SQL ci-dessous : lettres et chiffres seulement
# (une apostrophe ou un antislash casserait la requête, ou pire).
if [[ ! "$USER_DB_USER" =~ ^[A-Za-z0-9_]+$ || ! "$USER_DB_PASSWORD" =~ ^[A-Za-z0-9]+$ ]]; then
  echo "USER_DB_USER et USER_DB_PASSWORD : lettres et chiffres uniquement, non vides." >&2
  exit 1
fi

run_sql <<SQL
CREATE DATABASE IF NOT EXISTS user_db;
CREATE USER IF NOT EXISTS '$USER_DB_USER'@'%' IDENTIFIED BY '$USER_DB_PASSWORD';
GRANT ALL PRIVILEGES ON user_db.* TO '$USER_DB_USER'@'%';
SQL

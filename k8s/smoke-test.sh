#!/usr/bin/env bash
# Vérifie un déploiement de k8s/ sur le cluster visé par kubectl (minikube, kind en CI, GKE) :
# pods prêts, gateway en HTTPS, /internal/ fermé, NetworkPolicy, droits des comptes de service, Pod Security.
# Prérequis : kubectl apply -k k8s/ fait, ingress-nginx installé. Pas besoin de /etc/hosts ni de tunnel.
# Usage : k8s/smoke-test.sh
set -euo pipefail

NS=pokemon
HOST=pokemon.local
HTTPS_PORT=18443
HTTP_PORT=18080
failures=0

check() { # check <description> <attendu> <obtenu>
  if [ "$2" = "$3" ]; then
    echo "ok    $1"
  else
    echo "ECHEC $1 : attendu « $2 », obtenu « $3 »"
    failures=$((failures + 1))
  fi
}

# Code HTTP renvoyé par la gateway, en résolvant pokemon.local vers le port-forward.
status() { # status <méthode> <url> [arguments curl]
  curl -sk --max-time 10 -o /dev/null -w '%{http_code}' -X "$1" "$2" "${@:3}" \
    --resolve "$HOST:$HTTPS_PORT:127.0.0.1" --resolve "$HOST:$HTTP_PORT:127.0.0.1" || true
}

# Ouverture d'une connexion TCP depuis un pod : « ouvert », « bloqué » (TimeoutError) ou l'erreur.
connect() { # connect <déploiement> <hôte> <port>
  local out
  if out=$(kubectl -n "$NS" exec "deploy/$1" -c "$1" -- .venv/bin/python -c \
    "import socket; socket.create_connection(('$2', $3), timeout=3)" 2>&1); then
    echo ouvert
  elif grep -q TimeoutError <<<"$out"; then
    echo bloqué
  else
    tail -1 <<<"$out"
  fi
}

# rollout status attend aussi l'arrêt des anciens pods (« available » est déjà vrai pendant une mise à jour).
echo "Attente des déploiements..."
for deployment in $(kubectl -n "$NS" get deployment -o name); do
  kubectl -n "$NS" rollout status "$deployment" --timeout=300s >/dev/null
done

# Sortie du port-forward gardée : affichée en cas d'échec (port déjà pris, connexion perdue...).
port_forward_log=$(mktemp)
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller \
  "$HTTPS_PORT:443" "$HTTP_PORT:80" >"$port_forward_log" 2>&1 &
port_forward=$!
# Le port-forward peut déjà être mort : son arrêt ne doit pas changer le code de sortie.
trap 'rm -f "$port_forward_log"; kill "$port_forward" 2>/dev/null || true' EXIT
# Juste après un déploiement, nginx répond 404 le temps de charger la règle de l'Ingress, puis 503
# tant qu'il n'a pas les adresses des pods prêts : on attend que les trois services répondent (1 min max).
for _ in $(seq 30); do
  codes="$(status GET "https://$HOST:$HTTPS_PORT/health") $(status GET "https://$HOST:$HTTPS_PORT/api/formats")"
  codes="$codes $(status POST "https://$HOST:$HTTPS_PORT/api/auth/login")"
  case "$codes" in *000* | *404* | *503*) sleep 2 ;; *) break ;; esac
done

echo "Gateway"
check "page d'accueil en HTTPS" 200 "$(status GET "https://$HOST:$HTTPS_PORT/")"
check "API des tournois" 200 "$(status GET "https://$HOST:$HTTPS_PORT/api/tournaments")"
check "API des comptes (mauvais identifiants)" 401 "$(status POST "https://$HOST:$HTTPS_PORT/api/auth/login" \
  -H 'Content-Type: application/json' -d '{"username": "personne", "password": "mauvais"}')"
check "HTTP redirigé vers HTTPS" 308 "$(status GET "http://$HOST:$HTTP_PORT/")"
check "/internal/import fermé depuis l'extérieur" 404 "$(status POST "https://$HOST:$HTTPS_PORT/internal/import")"

echo "NetworkPolicy"
check "frontend -> mysql:3306" bloqué "$(connect frontend mysql 3306)"
check "frontend -> tournament-service:50051 (gRPC)" bloqué "$(connect frontend tournament-service 50051)"
check "frontend -> tournament-service:8000" ouvert "$(connect frontend tournament-service 8000)"
check "tournament-service -> mysql:3306" ouvert "$(connect tournament-service mysql 3306)"
check "user-service -> mysql:3306" ouvert "$(connect user-service mysql 3306)"

echo "Droits et utilisateurs"
for sa in frontend tournament-service user-service scraper; do
  check "compte $sa : lire les secrets" no \
    "$(kubectl auth can-i --as="system:serviceaccount:$NS:$sa" get secrets -n "$NS" || true)"
done
for d in frontend tournament-service user-service; do
  check "$d tourne en nobody" 65534 "$(kubectl -n "$NS" exec "deploy/$d" -c "$d" -- id -u)"
done
check "mysql tourne sous l'utilisateur mysql" 999 "$(kubectl -n "$NS" exec deploy/mysql -c mysql -- id -u)"
# Pod Security « restricted » : un pod sans securityContext (root possible) est refusé par l'API.
psa=$(kubectl -n "$NS" run psa-test --image=busybox --restart=Never --dry-run=server -- true 2>&1 || true)
check "pod non conforme refusé par Pod Security" refusé \
  "$(grep -q 'violates PodSecurity' <<<"$psa" && echo refusé || echo accepté)"

if [ "$failures" -gt 0 ]; then
  echo "$failures vérification(s) en échec"
  echo "--- sortie du port-forward vers ingress-nginx :"
  cat "$port_forward_log"
  exit 1
fi
echo "Toutes les vérifications passent"

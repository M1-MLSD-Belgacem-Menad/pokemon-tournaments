import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

API_URL = os.environ["TOURNAMENT_API_URL"]  # absent : le service refuse de démarrer
HERE = Path(__file__).parent
templates = Jinja2Templates(HERE / "templates")
app = FastAPI(title="frontend")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def api_get(path: str):
    """GET JSON sur le tournament-service. Le frontend n'a pas de logique métier : il affiche l'API."""
    try:
        with urllib.request.urlopen(f"{API_URL}{path}", timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(404, "introuvable") from e
        raise HTTPException(502, "erreur du service des tournois") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(503, "service des tournois injoignable") from e


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde liveness/readiness pour Kubernetes."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def tournaments(request: Request):
    """Liste des tournois, du plus récent au plus ancien."""
    return templates.TemplateResponse(
        request, "tournaments.html", {"tournaments": api_get("/api/tournaments")}
    )


@app.get("/tournaments/{tournament_id}", response_class=HTMLResponse)
def tournament(request: Request, tournament_id: int):
    """Détail d'un tournoi : top 16 et équipes (l'API a tous les joueurs, on ne demande que ça)."""
    return templates.TemplateResponse(
        request,
        "tournament.html",
        {"t": api_get(f"/api/tournaments/{tournament_id}?top=16")},
    )

import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Annotated
from urllib.parse import quote, urlencode, urlsplit

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Absentes : le service refuse de démarrer.
API_URL = os.environ["TOURNAMENT_API_URL"]
USER_API_URL = os.environ["USER_API_URL"]
HERE = Path(__file__).parent
templates = Jinja2Templates(HERE / "templates")
# Noms anglais de PokéAPI -> affichage en français.
TYPES_FR = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée", "stellar": "Stellaire",
}  # fmt: skip
CATEGORIES_FR = {"physical": "physique", "special": "spéciale", "status": "statut"}
templates.env.filters["type_fr"] = lambda t: TYPES_FR.get(t, t)
templates.env.filters["category_fr"] = lambda c: CATEGORIES_FR.get(c, c)
# Drapeau d'un code pays ISO à 2 lettres (Limitless), chargé par le navigateur depuis flagcdn.com.
templates.env.filters["flag"] = lambda c: (
    f"https://flagcdn.com/w20/{c.lower()}.png"
    if re.fullmatch(r"[A-Za-z]{2}", c or "")
    else None
)
app = FastAPI(title="frontend")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.middleware("http")
async def same_origin_posts(request: Request, call_next):
    """Refuse un formulaire envoyé depuis un autre site (CSRF, y compris sur /login et /logout).

    Les navigateurs ajoutent `Origin` aux POST : il doit désigner ce site-ci.
    """
    origin = request.headers.get("origin")
    if (
        request.method == "POST"
        and origin
        and urlsplit(origin).netloc != request.headers.get("host")
    ):
        return PlainTextResponse("formulaire d'un autre site refusé", status_code=403)
    return await call_next(request)


ROWS, TEAM_SIZE = 16, 6  # lignes et Pokémon par ligne du formulaire de saisie


def api_get(path: str, token: str | None = None):
    """GET JSON sur le tournament-service. Le frontend n'a pas de logique métier : il affiche l'API."""
    url = f"{API_URL}{path}"
    req = (
        urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        if token
        else url
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            raise HTTPException(
                e.code, "introuvable" if e.code == 404 else "session expirée"
            ) from e
        raise HTTPException(502, "erreur du service des tournois") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(503, "service des tournois injoignable") from e


def api_post(url: str, data: dict, token: str | None = None) -> tuple[int, dict]:
    """POST JSON. Renvoie (code, corps) : les erreurs 4xx sont pour l'utilisateur, à afficher."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, json.dumps(data).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            return e.code, json.loads(e.read() or b"{}")
        raise HTTPException(502, "erreur d'un service") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(503, "service injoignable") from e


def error_message(body: dict) -> str:
    """Message lisible depuis une erreur FastAPI : texte simple, ou liste d'erreurs de validation."""
    detail = body.get("detail", "erreur")
    if not isinstance(detail, list):
        return str(detail)
    messages = []
    for d in detail:
        loc = [p for p in d.get("loc", []) if p != "body"]
        if (
            len(loc) >= 2 and loc[0] == "standings"
        ):  # ["standings", 2, "team", 0] -> ligne 3
            where = f"ligne {loc[1] + 1}"
        else:
            where = ".".join(map(str, loc))
        msg = d.get("msg", "").removeprefix("Value error, ")
        messages.append(f"{where} : {msg}" if where else msg)
    return " ; ".join(messages)


def logged_in(request: Request, token: str) -> RedirectResponse:
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("token", token, max_age=24 * 3600, **cookie_flags(request))
    return resp


def cookie_flags(request: Request) -> dict:
    """HttpOnly : illisible en JavaScript. SameSite=Lax : pas envoyé par un formulaire d'un autre site.
    Secure derrière l'Ingress HTTPS, qui ajoute X-Forwarded-Proto (Compose reste en HTTP).
    Le frontend n'est joignable que par l'Ingress (NetworkPolicy) : l'en-tête est fiable.
    """
    https = request.headers.get("x-forwarded-proto") == "https"
    return {"httponly": True, "samesite": "lax", "secure": https}


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


@app.get("/tournaments/new", response_class=HTMLResponse)
def new_tournament_form(request: Request):
    if "token" not in request.cookies:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "new_tournament.html", {"rows": ROWS, "size": TEAM_SIZE, "form": {}}
    )


@app.post("/tournaments/new", response_class=HTMLResponse)
async def new_tournament(request: Request):
    """Formulaire -> POST /api/tournaments. Les règles (places contiguës, 6 Pokémon…) sont vérifiées par l'API."""
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse("/login", status_code=303)
    form = dict(await request.form())
    rows = 1 if form.get("detail_level") == "winner" else ROWS
    standings = [
        {
            "placement": i,
            "player": form[f"player_{i}"],
            "team": [
                form[f"mon_{i}_{j}"]
                for j in range(1, TEAM_SIZE + 1)
                if form.get(f"mon_{i}_{j}", "").strip()
            ],
        }
        for i in range(1, rows + 1)
        if form.get(f"player_{i}", "").strip()
    ]

    def page(error: str, status_code: int):
        context = {"rows": ROWS, "size": TEAM_SIZE, "form": form, "error": error}
        return templates.TemplateResponse(
            request, "new_tournament.html", context, status_code=status_code
        )

    filled = {s["placement"] for s in standings}
    for i in range(1, rows + 1):
        if i not in filled and any(
            form.get(f"mon_{i}_{j}", "").strip() for j in range(1, TEAM_SIZE + 1)
        ):
            return page(f"ligne {i} : des Pokémon sans nom de joueur", 422)
    data = {
        "name": form.get("name", ""),
        "date": form.get("date", ""),
        "format": form.get("format", ""),
        "detail_level": form.get("detail_level", ""),
        "player_count": form.get("player_count") or None,
        "standings": standings,
    }
    code, body = await run_in_threadpool(
        api_post, f"{API_URL}/api/tournaments", data, token
    )
    if code == 201:
        return RedirectResponse(f"/tournaments/{body['id']}", status_code=303)
    if (
        code == 401
    ):  # jeton expiré : la saisie reste affichée, le temps de se reconnecter
        return page(
            "Session expirée : reconnecte-toi dans un autre onglet (/login), puis renvoie ce formulaire.",
            401,
        )
    return page(error_message(body), 422)


def usage(standings: list[dict], limit: int = 5) -> dict:
    """Pokémon les plus joués : part (en %) des équipes connues qui l'alignent."""
    teams = [s.get("team") for s in standings if s.get("team")]
    # set : un Pokémon compte une fois par équipe, la part ne dépasse jamais 100 %
    counts = Counter(name for team in teams for name in {p["name"] for p in team})
    sprites = {}
    for p in (p for team in teams for p in team):
        sprites[p["name"]] = sprites.get(p["name"]) or p.get("sprite")
    top = [
        {"name": n, "sprite": sprites[n], "pct": round(100 * c / len(teams))}
        for n, c in counts.most_common(limit)
    ]
    return {"teams": len(teams), "top": top}


@app.get("/tournaments/{tournament_id}", response_class=HTMLResponse)
def tournament(request: Request, tournament_id: int):
    """Détail d'un tournoi : top 16 et équipes (l'API a tous les joueurs, on ne demande que ça)."""
    t = api_get(f"/api/tournaments/{tournament_id}?top=16")
    return templates.TemplateResponse(
        request, "tournament.html", {"t": t, "usage": usage(t["standings"])}
    )


def builder_page(request: Request, fmt: str | None, chosen: list[str], **extra):
    """Créateur d'équipe : Pokémon légaux du format, puis winrates des Pokémon et des paires choisis."""
    formats = api_get("/api/formats")
    fmt = fmt or (
        formats[0]["code"] if formats else None
    )  # par défaut : le format courant
    ctx = {
        "formats": formats,
        "format": fmt,
        "chosen": [],
        "size": TEAM_SIZE,
        "teams": None,
    }
    if fmt:
        ctx["legal"] = api_get(f"/api/formats/{quote(fmt, safe='')}/legal-pokemon")
        # Sans doublon ni case vide, et légaux dans ce format (il a pu changer depuis le choix).
        legal = set(ctx["legal"])
        chosen = list(dict.fromkeys(p for p in chosen if p in legal))[:TEAM_SIZE]
        ctx["chosen"] = chosen
        q = urlencode({"format": fmt, "pokemon": chosen}, doseq=True)
        if chosen:
            ctx["info"] = {
                p["name"]: p
                for p in api_get(
                    f"/api/pokemon?{urlencode({'pokemon': chosen}, doseq=True)}"
                )
            }
            ctx["stats"] = api_get(f"/api/stats/pokemon?{q}")
            ctx["pairs"] = api_get(f"/api/stats/combinations?{q}")
            ctx["matchups"] = {
                p: api_get(
                    f"/api/stats/matchups?{urlencode({'format': fmt, 'pokemon': p, 'limit': 5})}"
                )
                for p in chosen
            }
    if token := request.cookies.get("token"):
        try:
            ctx["teams"] = api_get("/api/teams", token)
            for t in ctx["teams"]:
                t["query"] = urlencode(
                    {"format": t["format"], "p": t["pokemon"]}, doseq=True
                )
        except HTTPException:  # jeton expiré : la page s'affiche quand même
            pass
    status_code = extra.pop("status_code", 200)
    return templates.TemplateResponse(
        request, "builder.html", ctx | extra, status_code=status_code
    )


@app.get("/builder", response_class=HTMLResponse)
def builder(
    request: Request,
    format: str | None = None,
    p: Annotated[list[str], Query()] = [],  # noqa: B006 (FastAPI copie la valeur par défaut)
    saved: bool = False,
):
    return builder_page(request, format, p, saved=saved)


@app.post("/builder/save", response_class=HTMLResponse)
async def save_team(request: Request):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    fmt, chosen = form.get("format", ""), [p for p in form.getlist("p") if p]
    team = {"name": form.get("name", ""), "format": fmt, "pokemon": chosen}
    code, body = await run_in_threadpool(api_post, f"{API_URL}/api/teams", team, token)
    if code == 201:
        q = urlencode({"format": fmt, "p": chosen, "saved": 1}, doseq=True)
        return RedirectResponse(f"/builder?{q}", status_code=303)
    error = "Session expirée : reconnecte-toi." if code == 401 else error_message(body)
    return await run_in_threadpool(
        builder_page, request, fmt, chosen, error=error, status_code=code
    )


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    code, body = api_post(
        f"{USER_API_URL}/api/auth/login", {"username": username, "password": password}
    )
    if code == 200:
        return logged_in(request, body["access_token"])
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error_message(body), "username": username},
        status_code=code,
    )


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(request, "register.html", {"form": {}})


@app.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    username: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    account = {"username": username, "email": email, "password": password}
    code, body = api_post(f"{USER_API_URL}/api/auth/register", account)
    if code == 201:  # inscrit : connexion directe
        code, body = api_post(
            f"{USER_API_URL}/api/auth/login",
            {"username": username, "password": password},
        )
        if code == 200:
            return logged_in(request, body["access_token"])
        return RedirectResponse("/login", status_code=303)  # compte créé : se connecter
    return templates.TemplateResponse(
        request,
        "register.html",
        {"error": error_message(body), "form": {"username": username, "email": email}},
        status_code=code,
    )


@app.post("/logout")
def logout(request: Request):
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(
        "token", **cookie_flags(request)
    )  # mêmes attributs qu'à la connexion
    return resp

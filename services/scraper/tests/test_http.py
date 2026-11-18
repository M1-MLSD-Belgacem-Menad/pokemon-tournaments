import contextlib

import pytest
import requests

import scraper


class Response:
    def __init__(self, status_code=200, headers=None, data=None):
        self.status_code, self.headers, self.data = status_code, headers or {}, data

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


@pytest.fixture
def http(monkeypatch):
    """requests.get factice : renvoie les réponses données dans l'ordre ; garde les pauses demandées."""
    sleeps, calls, queue = [], [], []

    def get(url, **kwargs):
        calls.append(url)
        return queue.pop(0)

    monkeypatch.setattr(scraper.requests, "get", get)
    monkeypatch.setattr(scraper.time, "sleep", sleeps.append)
    return sleeps, calls, queue


def test_429_attend_retry_after_puis_reessaie_une_fois(http):
    sleeps, calls, queue = http
    queue += [Response(429, {"Retry-After": "7"}), Response(data={"ok": 1})]
    assert scraper.get_json("http://x", 0) == {"ok": 1}
    assert sleeps == [0, 7]
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("headers", "wait"),
    [
        ({}, 10),  # sans en-tête : défaut
        ({"Retry-After": "600"}, 60),  # plafonné
        ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, 10),  # date : défaut
        ({"Retry-After": "inf"}, 10),  # non fini : défaut
        ({"Retry-After": "nan"}, 10),
    ],
    ids=["defaut", "plafond", "date", "inf", "nan"],
)
def test_429_duree_d_attente(http, headers, wait):
    sleeps, _, queue = http
    queue += [Response(429, headers), Response(data={})]
    scraper.get_json("http://x", 0)
    assert sleeps[1] == wait


def test_429_deux_fois_leve_une_erreur_sans_troisieme_essai(http):
    _, calls, queue = http
    queue += [Response(429), Response(429), Response(data={})]
    with pytest.raises(requests.HTTPError):
        scraper.get_json("http://x", 0)
    assert len(calls) == 2


@pytest.fixture
def run_main(monkeypatch):
    """main() avec scrape, enrich et gRPC simulés ; renvoie (codes de sortie, tournois tentés)."""
    tried = []

    def scrape(tid, importer):
        tried.append(tid)
        if tid == "b":
            raise RuntimeError("boom")

    monkeypatch.setenv("TOURNAMENT_API_URL", "http://api")
    monkeypatch.setenv("TOURNAMENT_GRPC_TARGET", "grpc:1")
    monkeypatch.setattr(scraper, "scrape", scrape)
    monkeypatch.setattr(scraper, "enrich", lambda api_url: None)
    monkeypatch.setattr(
        scraper.grpc, "insecure_channel", lambda target: contextlib.nullcontext()
    )
    monkeypatch.setattr(scraper.services, "TournamentImporterStub", lambda ch: None)

    def run(*ids):
        monkeypatch.setattr(scraper.sys, "argv", ["scraper.py", *ids])
        with pytest.raises(SystemExit) as exit_info:
            scraper.main()
        return exit_info.value.code, tried

    return run


def test_main_un_echec_n_arrete_pas_les_suivants_et_sort_en_1(run_main):
    assert run_main("a", "b", "c") == (1, ["a", "b", "c"])


def test_main_sans_echec_sort_en_0(run_main):
    assert run_main("a", "c") == (0, ["a", "c"])

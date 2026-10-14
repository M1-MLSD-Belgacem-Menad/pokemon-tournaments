from concurrent import futures
from pathlib import Path

import grpc
import pytest
from test_parse import DETAILS, PAIRINGS, STANDINGS

import scraper

HERE = Path(__file__).parent.parent


def test_proto_identique_a_celui_du_tournament_service():
    server_proto = HERE.parent / "tournament-service" / "app" / "tournament.proto"
    assert (HERE / "tournament.proto").read_text() == server_proto.read_text()


class FakeImporter(scraper.services.TournamentImporterServicer):
    """tournament-service factice : garde les requêtes, répond « déjà en base » à la deuxième."""

    def __init__(self):
        self.received = []

    def Import(self, request, context):
        self.received.append(request)
        return scraper.protos.ImportResult(id=7, created=len(self.received) == 1)


@pytest.fixture
def importer(monkeypatch):
    responses = {"details": DETAILS, "standings": STANDINGS, "pairings": PAIRINGS}
    monkeypatch.setattr(scraper, "get", lambda path: responses[path.rsplit("/", 1)[1]])
    fake = FakeImporter()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    scraper.services.add_TournamentImporterServicer_to_server(fake, server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    with grpc.insecure_channel(f"localhost:{port}") as channel:
        yield fake, scraper.services.TournamentImporterStub(channel)
    server.stop(None)


def test_scrape_envoie_le_tournoi_par_grpc(importer, capsys):
    fake, stub = importer
    scraper.scrape("abc", stub)
    scraper.scrape("abc", stub)
    assert capsys.readouterr().out.splitlines() == [
        "VGC UmbreNews #35 (abc) : importé",
        "VGC UmbreNews #35 (abc) : déjà en base",
    ]
    sent = fake.received[0]
    expected = scraper.build_payload("abc", DETAILS, STANDINGS, PAIRINGS)
    assert (sent.name, sent.date, sent.player_count) == (
        "VGC UmbreNews #35",
        "2026-10-13",
        92,
    )
    assert len(sent.standings) == len(expected["standings"])
    assert len(sent.matches) == len(expected["matches"])
    # Les valeurs None du JSON deviennent des champs absents (abandon, bye, nul).
    dropped = [s for s in sent.standings if not s.HasField("placement")]
    assert len(dropped) == sum(s["placement"] is None for s in expected["standings"])
    byes = [m for m in sent.matches if not m.HasField("player2")]
    assert len(byes) == sum(m["player2"] is None for m in expected["matches"])
    first = sent.standings[0].team[0]
    assert first.name == expected["standings"][0]["team"][0]["name"]
    assert list(first.moves) == expected["standings"][0]["team"][0]["moves"]

import grpc
import pytest
from google.protobuf.json_format import ParseDict
from test_import import make_payload

from app.grpc_server import protos, services


@pytest.fixture
def stub(client, db):
    with grpc.insecure_channel(f"localhost:{client.app.state.grpc_port}") as channel:
        yield services.TournamentImporterStub(channel)


def request(payload):
    # make_payload garde une nature, que la route REST ignore et que le .proto n'a pas.
    return ParseDict(payload, protos.TournamentImport(), ignore_unknown_fields=True)


def test_import_puis_doublon(stub, client):
    first = stub.Import(request(make_payload()))
    assert first.created
    again = stub.Import(request(make_payload()))
    assert (again.id, again.created) == (first.id, False)
    detail = client.get(f"/api/tournaments/{first.id}").json()
    assert detail["name"] == "VGC Test Cup"
    assert len(detail["standings"]) == 16
    assert detail["standings"][0]["team"][0]["moves"][0]["name"] == "Protect"


def test_placement_absent_est_un_abandon(stub, db):
    payload = make_payload()
    payload["standings"][15]["placement"] = None
    stub.Import(request(payload))
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM standing WHERE placement IS NULL")
        assert cur.fetchone()["n"] == 1


def test_donnees_invalides(stub):
    payload = make_payload()
    payload["matches"][0]["winner"] = "p5"  # n'a pas joué ce match
    with pytest.raises(grpc.RpcError) as e:
        stub.Import(request(payload))
    assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "p5" in e.value.details()


def test_tournoi_vide(stub):
    """Les listes vides arrivent telles quelles, pas comme des champs manquants."""
    payload = make_payload() | {"players": [], "standings": [], "matches": []}
    assert stub.Import(request(payload)).created


def test_message_d_erreur_tronque(stub):
    payload = make_payload()
    for s in payload["standings"]:
        s["team"] *= 10  # 60 Pokémon par équipe : une erreur par classement
    with pytest.raises(grpc.RpcError) as e:
        stub.Import(request(payload))
    assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert len(e.value.details()) <= 2000

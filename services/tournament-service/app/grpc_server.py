"""Serveur gRPC : le scraper y envoie les tournois à importer (contrat dans app/tournament.proto)."""

import os
from concurrent import futures

import grpc
from google.protobuf.json_format import MessageToDict

from app.db import connect
from app.importer import store_import
from app.schemas import TournamentImport

# Classes générées au démarrage depuis le .proto (grpcio-tools) : pas de fichier généré à maintenir.
protos, services = grpc.protos_and_services("app/tournament.proto")
# Les gros tournois dépassent la limite par défaut de 4 Mo (environ 700 octets par joueur).
MAX_MESSAGE = [("grpc.max_receive_message_length", 64 * 1024 * 1024)]


class TournamentImporter(services.TournamentImporterServicer):
    def Import(self, request, context):
        # Garde les listes vides et les 0 : seuls les champs `optional` absents manquent.
        data = MessageToDict(
            request,
            preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True,
        )
        for s in data["standings"]:
            # Champ absent = abandon ; le schéma le veut explicite (None).
            s.setdefault("placement", None)
        try:
            tournament = TournamentImport(**data)
            conn = connect()
            try:
                tournament_id, created = store_import(conn, tournament)
            finally:
                conn.close()
        except ValueError as e:  # dont la ValidationError de Pydantic
            # Tronqué : le message voyage dans les métadonnées de fin, limitées à 8 Ko.
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e)[:2000])
        return protos.ImportResult(id=tournament_id, created=created)


def start() -> tuple[grpc.Server, int]:
    """Lance le serveur sur GRPC_PORT (50051 par défaut, 0 = port libre) ; renvoie le serveur et son port."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4), options=MAX_MESSAGE)
    services.add_TournamentImporterServicer_to_server(TournamentImporter(), server)
    port = server.add_insecure_port(f"[::]:{os.environ.get('GRPC_PORT', '50051')}")
    server.start()
    return server, port

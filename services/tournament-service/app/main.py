from fastapi import FastAPI

app = FastAPI(title="tournament-service")


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde liveness/readiness pour Kubernetes."""
    return {"status": "ok"}

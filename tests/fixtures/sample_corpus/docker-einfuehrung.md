# Docker — Einführung

Docker ist eine Plattform zur Containerisierung von Anwendungen.

## Was ist ein Container?

Ein Container ist eine leichtgewichtige, eigenständige, ausführbare Softwareeinheit,
die Code und alle seine Abhängigkeiten enthält.

## Wichtige Befehle

```bash
# Image bauen
docker build -t meine-app:1.0 .

# Container starten
docker run -d -p 8080:80 meine-app:1.0

# Laufende Container anzeigen
docker ps

# Container stoppen
docker stop <container-id>
```

## Dockerfile-Beispiel

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

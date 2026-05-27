# REST API

REST (Representational State Transfer) ist ein Architektur-Stil für verteilte Systeme.

## Kernprinzipien

- **Zustandslos**: Jede Anfrage enthält alle nötigen Informationen
- **Ressourcen-orientiert**: Alles ist eine Ressource mit eindeutiger URL
- **Einheitliche Schnittstelle**: Standardisierte HTTP-Methoden

## Beispiel-Endpunkte

```
GET    /api/articles       → Liste aller Artikel
POST   /api/articles       → Neuen Artikel erstellen
GET    /api/articles/42    → Artikel 42 abrufen
PUT    /api/articles/42    → Artikel 42 ersetzen
DELETE /api/articles/42    → Artikel 42 löschen
```

## JSON-Response

```json
{
  "id": 42,
  "title": "REST-Grundlagen",
  "status": "published"
}
```

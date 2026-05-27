# HTTP-Protokoll

HTTP (Hypertext Transfer Protocol) ist das Fundament der Datenkommunikation im Web.

## Grundprinzip

HTTP folgt dem Client-Server-Modell. Der Client sendet Anfragen, der Server antwortet.

## HTTP-Methoden

- **GET** — Ressource abrufen
- **POST** — Ressource erstellen
- **PUT** — Ressource ersetzen
- **PATCH** — Ressource teilweise aktualisieren
- **DELETE** — Ressource löschen

## Statuscodes

| Code | Bedeutung |
|------|-----------|
| 200  | OK |
| 201  | Created |
| 400  | Bad Request |
| 404  | Not Found |
| 500  | Internal Server Error |

## Beispiel-Request

```http
GET /api/users/42 HTTP/1.1
Host: example.com
Accept: application/json
```

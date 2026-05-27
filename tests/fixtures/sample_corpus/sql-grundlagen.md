# SQL-Grundlagen

SQL (Structured Query Language) ist die Standardsprache für relationale Datenbanken.

## SELECT

```sql
-- Alle Spalten einer Tabelle abrufen
SELECT * FROM benutzer;

-- Bestimmte Spalten
SELECT name, email FROM benutzer WHERE aktiv = true;

-- Sortiert und limitiert
SELECT name, email
FROM benutzer
ORDER BY name ASC
LIMIT 10;
```

## INSERT / UPDATE / DELETE

```sql
-- Einfügen
INSERT INTO benutzer (name, email) VALUES ('Alice', 'alice@example.com');

-- Aktualisieren
UPDATE benutzer SET aktiv = false WHERE id = 42;

-- Löschen
DELETE FROM benutzer WHERE id = 42;
```

## JOINs

```sql
SELECT b.name, o.betrag
FROM benutzer b
INNER JOIN bestellungen o ON b.id = o.benutzer_id
WHERE o.betrag > 100;
```

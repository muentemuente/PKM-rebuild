# Python-Grundlagen

Python ist eine interpretierte, dynamisch getypte Programmiersprache mit klarer Syntax.

## Variablen und Typen

In Python werden Variablen ohne explizite Typdeklaration erstellt.

```python
name = "Alice"       # str
alter = 30           # int
gewicht = 65.5       # float
aktiv = True         # bool
```

## Listen und Dicts

```python
farben = ["rot", "grün", "blau"]
person = {"name": "Alice", "alter": 30}

# Zugriff
print(farben[0])       # "rot"
print(person["name"])  # "Alice"
```

## Funktionen

```python
def begrüße(name: str) -> str:
    return f"Hallo, {name}!"

ergebnis = begrüße("Alice")
```

## Häufige Fehler

- `IndentationError`: falsche Einrückung
- `KeyError`: Schlüssel nicht im Dict
- `TypeError`: falscher Datentyp

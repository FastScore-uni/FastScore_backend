# FastScore backend

API w technologii FastAPI

Do przetwarzania korzysta z biblioteki basic_pitch oraz crepe.

## Uruchamianie Lokalne

```bash
uvicorn api:app --reload
```

Otwiera API pod adresem http://127.0.0.1:8000/audio-to-xml.

## Wdrożenie

Wersja programu przygotowana do wdrożenia w środowisku chmurowym Google Run znajduje się w katalogu functions. 

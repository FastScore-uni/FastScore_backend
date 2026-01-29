# FastScore backend

API w technologii FastAPI służące do transkrypcji dźwięku na nuty.

Do przetwarzania korzysta z biblioteki basic_pitch oraz crepe.

## Uruchamianie Lokalne

```bash
uvicorn api:app --reload
```

Otwiera API pod adresem http://127.0.0.1:8000/.

## Wdrożenie

Wersja programu przygotowana do wdrożenia w środowisku chmurowym Google Run znajduje się w katalogu functions. 

## Endpointy

 - convert-bp - dokonuje transkrypcji za pomocą basic pitch. Przyjmuje plik dźwiękowy, zwraca plik musicxml oraz midi w formacie json: {"xml": XML_DATA, "midi_base64": MIDI_DATA}.
 - convert-crepe - dokonuje transkrypcji za pomocą crepe. Przyjmuje plik dźwiękowy, zwraca plik musicxml oraz midi w formacie json: {"xml": XML_DATA, "midi_base64": MIDI_DATA}.
 - convert-crepe-preprocessing - wykonuje preprocessing a następnie dokonuje transkrypcji za pomocą crepe. Przyjmuje plik dźwiękowy, zwraca plik musicxml oraz midi w formacie json: {"xml": XML_DATA, "midi_base64": MIDI_DATA}.
 - midi-to-audio - dokonuje syntezy dźwięku. Przyjmuje plik midi, zwraca plik dźwiękowy w formacie wav.
 - xml-to-pdf - wykonuje export pliku z zapisem nutowym. Przyjmuje plik musicxml i zwraca plik pdf.

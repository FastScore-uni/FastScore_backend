from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
import io

app = FastAPI()

@app.post("/audio-to-midi")
async def audio_to_midi(file: UploadFile = File(...)):
    # 🔽 tu normalnie zrobiłbyś konwersję audio → midi
    # content = await file.read()
    # midi_bytes = convert_audio_to_midi(content)
    # dla przykładu: zwracamy pusty plik MIDI
    midi_bytes = b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x60MTrk..."

    return StreamingResponse(
        io.BytesIO(midi_bytes),
        media_type="audio/midi",
        headers={"Content-Disposition": "attachment; filename=output.mid"}
    )


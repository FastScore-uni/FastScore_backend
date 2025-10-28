from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # do testów
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/audio-to-xml")
async def audio_to_xml(file: UploadFile = File(...)):
    print("Received file:", file.filename)
    with open("score.musicxml", "r", encoding="utf-8") as f:
        xml_data = f.read()
    return Response(content=xml_data, media_type="application/xml")

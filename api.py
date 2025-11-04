import shutil

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import basic_pitch_convert
import os

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
    audio_file_path = os.path.join("uploads", file.filename)
    with open(audio_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    xml_file_path = basic_pitch_convert.convert(audio_file_path)
    with open(xml_file_path, "r", encoding="utf-8") as f:
        xml_data = f.read()
    return Response(content=xml_data, media_type="application/xml")

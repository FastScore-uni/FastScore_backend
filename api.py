import shutil

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import basic_pitch_convert
import crepe_convert
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # do testów
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def audio_to_xml(convert_function, file: UploadFile):
    print("Received file:", file.filename)
    os.makedirs("./uploads", exist_ok=True)
    audio_file_path = os.path.join("uploads", file.filename)
    with open(audio_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    xml_file_path, midi_file_path = convert_function(audio_file_path)
    with open(xml_file_path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/convert_bp")
async def convert_bp(file: UploadFile = File(...)):
    xml_data = audio_to_xml(basic_pitch_convert.convert, file)
    return Response(content=xml_data, media_type="application/xml")

@app.post("/convert_crepe")
async def convert_crepe(file: UploadFile = File(...)):
    xml_data = audio_to_xml(crepe_convert.convert, file)
    return Response(content=xml_data, media_type="application/xml")

@app.post("/convert_crepe_ext")
async def convert_crepe_ext(file: UploadFile = File(...)):
    xml_data = audio_to_xml(crepe_convert.convert, file)
    return Response(content=xml_data, media_type="application/xml")
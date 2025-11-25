import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from multiprocessing import Process, Pipe
import workers
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # do testów
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

crepe_pipe, crepe_child = Pipe()
crepe_process = Process(target=workers.crepe_worker, args=(crepe_child,))
crepe_process.start()

bp_pipe, bp_child = Pipe()
bp_process = Process(target=workers.basic_pitch_worker, args=(bp_child,))
bp_process.start()

melody_ext_pipe, melody_ext_child = Pipe()
melody_ext_process = Process(target=workers.melody_ext_worker, args=(melody_ext_child,))
melody_ext_process.start()

def audio_to_xml(convert_pipe, file: UploadFile):
    print("Received file:", file.filename)
    os.makedirs("./uploads", exist_ok=True)
    audio_file_path = os.path.join("uploads", file.filename)
    if os.path.exists(audio_file_path):
        base, ext = os.path.splitext(audio_file_path)
        i = 1
        while os.path.exists(new_path := f"{base}_{i}{ext}"):
            i += 1
        audio_file_path = new_path
    with open(audio_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    convert_pipe.send(audio_file_path)
    xml_file_path, midi_file_path = convert_pipe.recv()
    print(f"otrzymane xml: {xml_file_path}")
    with open(xml_file_path, "r", encoding="utf-8") as f:
        xml_file = f.read()
    os.remove(xml_file_path)
    return xml_file

@app.post("/convert_bp")
async def convert_bp(file: UploadFile = File(...)):
    xml_data = audio_to_xml(bp_pipe, file)
    return Response(content=xml_data, media_type="application/xml")

@app.post("/convert_crepe")
async def convert_crepe(file: UploadFile = File(...)):
    xml_data = audio_to_xml(crepe_pipe, file)
    return Response(content=xml_data, media_type="application/xml")

@app.post("/convert_melody_ext")
async def convert_crepe_ext(file: UploadFile = File(...)):
    xml_data = audio_to_xml(melody_ext_pipe, file)
    return Response(content=xml_data, media_type="application/xml")
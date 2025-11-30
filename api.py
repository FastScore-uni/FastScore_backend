import shutil
from multiprocessing import Process, Pipe
import workers
from svglib.svglib import svg2rlg
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
import verovio
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from midi2audio import FluidSynth
import os

pipes = []
def newPipe():
    parent, child = Pipe()
    pipes.append(parent)
    return parent, child

crepe_pipe, crepe_child = newPipe()
bp_pipe, bp_child = newPipe()
melody_ext_pipe, melody_ext_child = newPipe()

@asynccontextmanager
async def lifespan(app: FastAPI):
    processes = [
        Process(target=workers.crepe_worker, args=(crepe_child,), daemon=True),
        Process(target=workers.basic_pitch_worker, args=(bp_child,), daemon=True),
        Process(target=workers.melody_ext_worker, args=(melody_ext_child,), daemon=True),
    ]
    for p in processes:
        p.start()
    yield
    for pipe in pipes:
        pipe.send(None)
    for p in processes:
        if p.is_alive():
            p.kill()
            p.join(timeout=3)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # do testów
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    xml_file_path: str
    xml_file_path, midi_file_path = convert_pipe.recv()
    print(f"otrzymane xml: {xml_file_path}")
    if xml_file_path == "" or midi_file_path == "":
        return ""
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


@app.post("/midi-to-audio")
async def midi_to_audio(midi_path: str = Query(...)):
    midi_path = midi_path.replace("\\", "/")
    wav_path = midi_path.replace(".mid", ".wav")

    fs = FluidSynth("FluidR3_GM.sf2")
    fs.midi_to_audio(midi_path, wav_path)

    return FileResponse(
        wav_path,
        media_type="audio/wav",
        filename=os.path.basename(wav_path)
    )

@app.get("/download-xml")
async def download_xml(xml_path):    
    if not os.path.exists(xml_path):
        raise HTTPException(status_code=404, content="XML not found")
    
    return FileResponse(
        xml_path,
        media_type="application/vnd.recordare.musicxml+xml",
        filename="output.musicxml"
    )

@app.get("/download-midi")
async def download_midi(midi_path):
    if not os.path.exists(midi_path):
        raise HTTPException(status_code=404, content="MIDI not found")

    return FileResponse(
        midi_path,
        media_type="audio/midi",
        filename=os.path.basename(midi_path)
    )
    
@app.get("/xml-to-pdf")
async def xml_to_pdf(xml_path: str = Query(...)):
    xml_path = xml_path.replace("\\", "/")

    if not os.path.exists(xml_path):
        raise HTTPException(status_code=404, detail="XML file not found")

    pdf_path = xml_path.replace(".musicxml", ".pdf").replace(".xml", ".pdf")

    tk = verovio.toolkit()

    options = {
        "pageHeight": 200,
        "pageWidth": 150,
        "scale": 30
    }

    tk.setOptions(options)
    tk.loadFile(xml_path)

    svg = tk.renderToSVG()

    tmp_svg_path = "tmp.svg"
    with open(tmp_svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    drawing = svg2rlg(tmp_svg_path)

    c = canvas.Canvas(pdf_path)
    renderPDF.draw(drawing, c, 0, 0)
    c.save()

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path)
    )

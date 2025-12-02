import base64
import shutil
from multiprocessing import Process, Pipe
import workers
from svglib.svglib import svg2rlg
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
import verovio
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
from io import BytesIO
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from pathlib import Path
from fastapi.responses import Response
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

_upload_dir = "uploads"

def audio_to_xml(convert_pipe, file: UploadFile):
    print("Received file:", file.filename)
    os.makedirs(_upload_dir, exist_ok=True)
    audio_file_path = os.path.join(_upload_dir, file.filename)
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
    if xml_file_path == "" or midi_file_path == "":
        return ""
    with open(xml_file_path, "r", encoding="utf-8") as f:
        xml_data = f.read()
    with open(midi_file_path, "rb") as f:
        midi_bytes = f.read()
    midi_b64 = base64.b64encode(midi_bytes).decode("ascii")
    os.remove(xml_file_path)
    return {"xml": xml_data, "midi_base64": midi_b64}

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
async def midi_to_audio(midi_file: UploadFile = File(...)):
    midi_path = Path(midi_file.filename or "upload.mid")
    with open(midi_path, "wb") as f:
        shutil.copyfileobj(midi_file.file, f)

    wav_path = midi_path.with_suffix(".wav")
    fs = FluidSynth("FluidR3_GM.sf2")
    fs.midi_to_audio(str(midi_path), str(wav_path))

    with open(wav_path, "rb") as f:
        wav_bytes = f.read()
    
    try:
        midi_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
    except Exception:
        pass

    return Response(content=wav_bytes, media_type="audio/wav")
    
@app.post("/xml-to-pdf")
async def xml_to_pdf(xml: str = Form(...)):
    if not xml or not xml.strip():
        raise HTTPException(status_code=400, detail="Empty xml")

    tk = verovio.toolkit()
    options = {
        "scale": 40,
        "adjustPageWidth": True,
    }
    tk.setOptions(options)

    try:
        tk.loadData(xml)
        page_count = tk.getPageCount()
        if page_count < 1:
            raise HTTPException(status_code=500, detail="No pages rendered by Verovio")

        svg = tk.renderToSVG(1)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verovio render error: {e}")
    svg = svg.replace("#00000", "#000000")
    try:
        drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"svg2rlg parse error: {e}")

    max_w, max_h = 595.0, 842.0
    dw = getattr(drawing, "width", None)
    dh = getattr(drawing, "height", None)

    if not dw or not dh:
        scale = 1.0
    else:
        scale = min(max_w / float(dw), max_h / float(dh))
        try:
            drawing.scale(scale, scale)
        except Exception:
            pass

    translated_x = (max_w - (dw * scale if dw else 0)) / 2
    translated_y = (max_h - (dh * scale if dh else 0)) / 2

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(max_w, max_h))
    try:
        renderPDF.draw(drawing, c, translated_x, translated_y)
    except Exception as e:
        try:
            renderPDF.draw(drawing, c, 0, 0)
        except Exception as e2:
            raise HTTPException(status_code=500, detail=f"SVG->PDF render error: {e} / fallback {e2}")
    c.showPage()
    c.save()
    packet.seek(0)
    pdf_bytes = packet.read()

    return Response(content=pdf_bytes, media_type="application/pdf")

def scale_drawing(drawing, max_width=595, max_height=842):
    scale_w = max_width / drawing.width
    scale_h = max_height / drawing.height
    scale = min(scale_w, scale_h)
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)


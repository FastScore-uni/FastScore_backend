import base64
import re
import shutil
from multiprocessing import Process, Pipe
import workers
from svglib.svglib import svg2rlg
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
import verovio
from io import BytesIO
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from pathlib import Path
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from midi2audio import FluidSynth
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
        xml_data = f.read()
    with open(midi_file_path, "rb") as f:
        midi_bytes = f.read()
    midi_b64 = base64.b64encode(midi_bytes).decode("ascii")
    os.remove(xml_file_path)
    return {"xml": xml_data, "midi_base64": midi_b64}

@app.post("/convert_bp")
async def convert_bp(file: UploadFile = File(...)):
    xml_data = audio_to_xml(bp_pipe, file)
    return xml_data

@app.post("/convert_crepe")
async def convert_crepe(file: UploadFile = File(...)):
    xml_data = audio_to_xml(crepe_pipe, file)
    return xml_data

@app.post("/convert_melody_ext")
async def convert_crepe_ext(file: UploadFile = File(...)):
    xml_data = audio_to_xml(melody_ext_pipe, file)
    return xml_data


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
        "scale": 80,
        "footer": "none",
        "header": "none",
        "pageHeight": 2970,
        "pageWidth": 2100,
        "unit": 10,
    }
    tk.setOptions(options)

    try:
        tk.loadData(xml)
        page_count = tk.getPageCount()

        packet = BytesIO()

        pdf_w, pdf_h = 595.0, 842.0
        c = canvas.Canvas(packet, pagesize=(pdf_w, pdf_h))

        for page in range(1, page_count + 1):
            svg = tk.renderToSVG(page)
            svg = svg.replace("#00000", "#000000")
            svg = fix_tempo(svg)

            drawing = svg2rlg(BytesIO(svg.encode("utf-8")))

            scale_x = pdf_w / 21000
            scale_y = pdf_h / 29700
            scale = min(scale_x, scale_y)
            
            drawing.scale(scale, scale)
            offset_y = -drawing.height * scale + pdf_h

            renderPDF.draw(drawing, c, 0, offset_y)
            c.showPage()

        c.save()
        packet.seek(0)
        return Response(content=packet.read(), media_type="application/pdf")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verovio render error: {e}")

def fix_tempo(svg: str) -> str:
    svg = re.sub(
        r'<tspan[^>]*font-family=["\']Leipzig["\'][^>]*font-size=["\']800px["\'][^>]*>.*?</tspan>',
        '',
        svg,
        flags=re.DOTALL
    )

    svg = re.sub(
        r'<tspan[^>]*font-size=["\']450px["\'][^>]*>\s*=\s*</tspan>',
        '',
        svg,
        flags=re.DOTALL
    )

    svg = re.sub(r'<tspan\b[^>]*>\s*</tspan>', '', svg)

    return svg
import base64
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
from contextlib import asynccontextmanager
from midi2audio import FluidSynth
import os
import subprocess

pipes = []
def newPipe():
    parent, child = Pipe()
    pipes.append(parent)
    return parent, child

crepe_pipe, crepe_child = newPipe()
bp_pipe, bp_child = newPipe()
# melody_ext_pipe, melody_ext_child = newPipe()

@asynccontextmanager
async def lifespan(app: FastAPI):
    processes = [
        Process(target=workers.crepe_worker, args=(crepe_child,), daemon=True),
        Process(target=workers.basic_pitch_worker, args=(bp_child,), daemon=True),
        # Process(target=workers.melody_ext_worker, args=(melody_ext_child,), daemon=True),
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

def convert_opus_to_wav(input_path, timeout=10):
    input_path = Path(input_path)
    output_path = input_path.with_suffix(".wav")

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-v", "error",
        "-i", str(input_path),
        "-ac", "1",
        "-ar", "44100",
        str(output_path)
    ]

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=True
        )
    except subprocess.TimeoutExpired:
        print("FFmpeg timeout — proces zawiesił się.")
        raise
    except subprocess.CalledProcessError as e:
        print("FFmpeg error:", e.stderr.decode())
        raise

    return output_path

def audio_to_xml(convert_pipe, file: UploadFile, preprocessing=False):
    print("Received file:", file.filename)

    # ensure directory exists
    os.makedirs(_upload_dir, exist_ok=True)
    audio_file_path = os.path.join(_upload_dir, file.filename)

    # ensure filename is unique
    if os.path.exists(audio_file_path):
        base, ext = os.path.splitext(audio_file_path)
        i = 1
        while os.path.exists(new_path := f"{base}_{i}{ext}"):
            i += 1
        audio_file_path = new_path
    with open(audio_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # convert opus file
    if Path(audio_file_path).suffix.lower() == ".opus":
        audio_file_path = convert_opus_to_wav(audio_file_path)

    # audio processing
    convert_pipe.send((audio_file_path, preprocessing))
    xml_file_path, midi_file_path = convert_pipe.recv()
    print(f"otrzymane xml: {xml_file_path}")
    if xml_file_path == "" or midi_file_path == "":
        print(f"Filepath error: xml {xml_file_path}, midi {midi_file_path}")
        return ""

    # reading files and returning data
    with open(xml_file_path, "r", encoding="utf-8") as f:
        xml_data = f.read()
    with open(midi_file_path, "rb") as f:
        midi_bytes = f.read()
    midi_b64 = base64.b64encode(midi_bytes).decode("ascii")
    os.remove(xml_file_path)
    return {"xml": xml_data, "midi_base64": midi_b64}

@app.post("/convert-bp")
async def convert_bp(file: UploadFile = File(...)):
    return audio_to_xml(bp_pipe, file)

@app.post("/convert-crepe")
async def convert_crepe(file: UploadFile = File(...)):
    return audio_to_xml(crepe_pipe, file)

@app.post("/convert-crepe_preproc")
async def convert_with_preprocessing(file: UploadFile = File(...)):
    return audio_to_xml(crepe_pipe, file, preprocessing=True)

# @app.post("/convert_melody_ext")
# async def convert_crepe_ext(file: UploadFile = File(...)):
#     return audio_to_xml(melody_ext_pipe, file)


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

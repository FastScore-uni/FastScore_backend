import base64
import shutil
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

app.mount("/basic_pitch_output", StaticFiles(directory="basic_pitch_output"), name="basic_pitch_output")


@app.post("/audio-to-xml")
async def audio_to_xml(file: UploadFile = File(...)):
    print("Received file:", file.filename)
    os.makedirs("./uploads", exist_ok=True)
    audio_file_path = os.path.join("uploads", file.filename)
    with open(audio_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    xml_file_path, midi_file_path = basic_pitch_convert.convert(audio_file_path)
    with open(xml_file_path, "r", encoding="utf-8") as f:
        xml_data = f.read()
    with open(midi_file_path, "rb") as f:
        midi_bytes = f.read()
    midi_b64 = base64.b64encode(midi_bytes).decode("ascii")
    return {"xml": xml_data, "midi_base64": midi_b64}



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
import shutil
from svglib.svglib import svg2rlg
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
import verovio
from io import BytesIO
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
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
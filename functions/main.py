from flask import Flask, request, jsonify, send_file, Response
import tempfile
import os
import shutil
import logging
import uuid
import datetime
from firebase_admin import initialize_app, storage, credentials, firestore
import google.auth
from google.auth import iam
from google.auth import impersonated_credentials
from google.auth.transport import requests as google_requests
import google.auth.credentials
import subprocess
from pathlib import Path
import base64
from midi2audio import FluidSynth
from svglib.svglib import svg2rlg
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
import verovio
from io import BytesIO
import importlib.util
import mido

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin
try:
    initialize_app(options={
        'storageBucket': 'fastscore-b82f4.firebasestorage.app'
    })
except ValueError:
    pass

app = Flask(__name__)

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

    return str(output_path)

def process_audio_request(model_type='basic_pitch', preprocessing=False):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    if request.method != 'POST':
        return ('Method not allowed', 405, headers)
    
    try:
        import basic_pitch_convert
        import crepe_convert
        
        if 'file' not in request.files:
            return ('No file provided', 400, headers)
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return ('No file selected', 400, headers)
        
        user_id = request.form.get('user_id')
        title = request.form.get('title', uploaded_file.filename)
        duration = request.form.get('duration', '0:00')
        
        default_format = 'MP3'
        if uploaded_file.filename:
            ext = os.path.splitext(uploaded_file.filename)[1].lower()
            if ext == '.wav':
                default_format = 'WAV'
        audio_format = request.form.get('format', default_format)
        color = request.form.get('color')
        image_url = request.form.get('imageUrl')
        image_asset = request.form.get('imageAsset')

        temp_dir = tempfile.mkdtemp()
        original_filename = uploaded_file.filename or "audio.mp3"
        audio_file_path = os.path.join(temp_dir, original_filename)
        uploaded_file.save(audio_file_path)
        
        # Handle .opus or other formats that need conversion
        if original_filename.lower().endswith('.opus'):
             logger.info("Detected .opus file, converting to .wav")
             audio_file_path = convert_opus_to_wav(audio_file_path)

        logger.info(f"Starting conversion using model: {model_type}")
        
        if model_type == 'crepe':
             xml_file_path, midi_file_path = crepe_convert.convert(audio_file_path, preprocessing=preprocessing)
        else:
             # Default to basic pitch
             xml_file_path, midi_file_path = basic_pitch_convert.convert(audio_file_path)

        with open(xml_file_path, "r", encoding="utf-8") as f:
            xml_data = f.read()
            
        with open(midi_file_path, "rb") as f:
            midi_bytes = f.read()
        midi_b64 = base64.b64encode(midi_bytes).decode("ascii")
            
        bucket = storage.bucket()
        unique_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(original_filename)[0]
        
        storage_path_xml = f"conversions/{timestamp}_{unique_id}/{base_name}.musicxml"
        storage_path_midi = f"conversions/{timestamp}_{unique_id}/{base_name}.mid"
        storage_path_audio = f"conversions/{timestamp}_{unique_id}/{original_filename}"
        
        blob_xml = bucket.blob(storage_path_xml)
        blob_xml.upload_from_filename(xml_file_path)
        
        blob_midi = bucket.blob(storage_path_midi)
        blob_midi.upload_from_filename(midi_file_path)

        blob_audio = bucket.blob(storage_path_audio)
        blob_audio.upload_from_filename(audio_file_path)
        
        credentials, project_id = google.auth.default()
        service_account_email = 'default'
        if hasattr(credentials, 'service_account_email'):
            service_account_email = credentials.service_account_email
            
        if not service_account_email or service_account_email == 'default':
            try:
                auth_request = google_requests.Request()
                credentials.refresh(auth_request)
                service_account_email = credentials.service_account_email
            except Exception:
                pass

        if not service_account_email or service_account_email == 'default':
            try:
                import requests
                metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
                metadata_headers = {"Metadata-Flavor": "Google"}
                response = requests.get(metadata_url, headers=metadata_headers, timeout=2)
                if response.status_code == 200:
                    service_account_email = response.text.strip()
            except Exception:
                pass
        
        signing_credentials = credentials
        if not hasattr(credentials, 'sign_bytes'):
            try:
                if service_account_email == 'default':
                     raise ValueError("Cannot setup IAM signer with 'default' service account email")
                
                signing_credentials = impersonated_credentials.Credentials(
                    source_credentials=credentials,
                    target_principal=service_account_email,
                    target_scopes=['https://www.googleapis.com/auth/cloud-platform'],
                    lifetime=3600
                )
            except Exception as e:
                logger.error(f"Could not setup IAM signer: {e}")
                pass

        try:
            xml_url = blob_xml.generate_signed_url(
                version='v4',
                expiration=datetime.timedelta(days=7), 
                method='GET',
                service_account_email=service_account_email,
                credentials=signing_credentials
            )
            midi_url = blob_midi.generate_signed_url(
                version='v4',
                expiration=datetime.timedelta(days=7), 
                method='GET',
                service_account_email=service_account_email,
                credentials=signing_credentials
            )
            audio_url = blob_audio.generate_signed_url(
                version='v4',
                expiration=datetime.timedelta(days=7), 
                method='GET',
                service_account_email=service_account_email,
                credentials=signing_credentials
            )
        except Exception as e:
            logger.error(f"Failed to generate signed URLs: {e}")
            xml_url = ""
            midi_url = ""
            audio_url = ""
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        firestore_id = None
        if user_id:
            try:
                db = firestore.client()
                doc_ref = db.collection('users').document(user_id).collection('songs').document()
                
                song_data = {
                    'userId': user_id,
                    'date': datetime.datetime.now().strftime("%Y-%m-%d"),
                    'title': title,
                    'duration': duration,
                    'format': audio_format,
                    'color': color,
                    'imageUrl': image_url,
                    'imageAsset': image_asset,
                    'xmlUrl': xml_url,
                    'midiUrl': midi_url,
                    'audioUrl': audio_url,
                    'fileName': base_name,
                    'storagePathXml': storage_path_xml,
                    'storagePathMidi': storage_path_midi,
                    'storagePathAudio': storage_path_audio,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'model': model_type
                }
                
                song_data = {k: v for k, v in song_data.items() if v is not None}
                
                doc_ref.set(song_data)
                firestore_id = doc_ref.id
            except Exception as e:
                logger.error(f"Error saving to Firestore: {e}")
        
        response_data = {
            "xml": xml_data,
            "midi_base64": midi_b64,
            "xml_url": xml_url,
            "midi_url": midi_url,
            "audio_url": audio_url,
            "filename": base_name,
            "firestoreId": firestore_id
        }
        
        return (jsonify(response_data), 200, headers)
        
    except Exception as e:
        logger.error(f"Error processing audio file: {str(e)}")
        import traceback
        traceback.print_exc()
        return (f'Error processing audio file: {str(e)}', 500, headers)

@app.route('/', methods=['POST', 'OPTIONS'])
@app.route('/audio-to-xml', methods=['POST', 'OPTIONS'])
def audio_to_xml():
    # Default endpoint, uses basic_pitch or whatever is in form
    model = request.form.get('model', 'basic_pitch')
    return process_audio_request(model)

@app.route('/convert-bp', methods=['POST', 'OPTIONS'])
def convert_bp():
    return process_audio_request('basic_pitch')

@app.route('/convert-crepe', methods=['POST', 'OPTIONS'])
def convert_crepe():
    return process_audio_request('crepe', preprocessing=False)

@app.route('/convert-crepe-preproc', methods=['POST', 'OPTIONS'])
def convert_crepe_preproc():
    return process_audio_request('crepe', preprocessing=True)

@app.route('/convert-melody-ext', methods=['POST', 'OPTIONS'])
def convert_melody_ext():
    # Fallback to basic pitch for now
    return process_audio_request('basic_pitch')

@app.route("/midi-to-audio", methods=['POST', 'OPTIONS'])
def midi_to_audio():
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    if request.method != 'POST':
        return ('Method not allowed', 405, headers)

    try:
        midi_path_arg = request.args.get('midi_path')
        
        # If midi_path is provided (from previous conversion), download it from storage
        if midi_path_arg:
             # This part is tricky because we don't have easy access to the file system of the previous request
             # unless we use shared storage or download from the bucket.
             # For simplicity, let's assume the user uploads the MIDI file again or we download from bucket.
             # But the frontend code suggests it might be sending a file or a path.
             # Let's support file upload first as it is more robust.
             pass

        if 'midi_file' in request.files:
            midi_file = request.files['midi_file']
            original_filename = midi_file.filename or "upload.mid"
        elif 'file' in request.files:
             midi_file = request.files['file']
             original_filename = midi_file.filename or "upload.mid"
        else:
            return ('No midi file provided', 400, headers)

        temp_dir = tempfile.mkdtemp()
        midi_path = Path(temp_dir) / original_filename
        midi_file.save(midi_path)
        
        file_size = os.path.getsize(midi_path)
        logger.info(f"Saved MIDI file to {midi_path}, size: {file_size} bytes")
        
        try:
            mid = mido.MidiFile(midi_path)
            logger.info(f"MIDI file loaded successfully. Type: {mid.type}, Length: {mid.length} seconds, Tracks: {len(mid.tracks)}")
            
            # Log first few messages to verify content
            sample_messages = []
            for i, track in enumerate(mid.tracks[:3]):  # First 3 tracks
                sample_messages.append(f"Track {i}: {len(track)} messages")
                if len(track) > 0:
                    sample_messages.append(f"  First: {track[0]}")
                    if len(track) > 1:
                        sample_messages.append(f"  Last: {track[-1]}")
            logger.info("MIDI content sample:\n" + "\n".join(sample_messages))
        except Exception as e:
            logger.error(f"Failed to parse MIDI file with mido: {e}")

        wav_path = midi_path.with_suffix(".wav")
        
        # Use the soundfont installed in the Docker image
        soundfont_path = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
        if not os.path.exists(soundfont_path):
             logger.warning(f"Soundfont not found at {soundfont_path}, searching /usr/share/sounds/sf2/")
             found_sf2 = False
             if os.path.exists("/usr/share/sounds/sf2/"):
                 for f in os.listdir("/usr/share/sounds/sf2/"):
                     if f.endswith(".sf2"):
                         soundfont_path = os.path.join("/usr/share/sounds/sf2/", f)
                         logger.info(f"Found alternative soundfont: {soundfont_path}")
                         found_sf2 = True
                         break
             
             if not found_sf2:
                # Fallback to local directory
                soundfont_path = "FluidR3_GM.sf2" 
                logger.warning(f"No soundfont found in system paths, trying local fallback: {soundfont_path}")

        logger.info(f"Using soundfont: {soundfont_path}")
        
        # Direct fluidsynth call for better debugging and control
        # Note: -F automatically outputs WAV format (not raw)
        cmd = [
            "fluidsynth",
            "-ni",           # No shell, no interactive
            "-g", "1.0",     # Gain
            "-R", "0",       # Reverb OFF
            "-C", "0",       # Chorus OFF
            "-r", "44100",   # Sample rate
            "-F", str(wav_path), # Output file (WAV format by default)
            soundfont_path,
            str(midi_path)
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Fluidsynth failed with return code {result.returncode}")
            logger.error(f"Stdout: {result.stdout}")
            logger.error(f"Stderr: {result.stderr}")
            return (f"Fluidsynth failed: {result.stderr}", 500, headers)
            
        logger.info(f"Fluidsynth stdout: {result.stdout}")
        # logger.info(f"Fluidsynth stderr: {result.stderr}") # Stderr contains the rendering progress logs

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
             logger.error(f"WAV file generation failed or file too small. Size: {os.path.getsize(wav_path) if os.path.exists(wav_path) else 'Not Found'}")
             return ("WAV generation failed", 500, headers)

        with open(wav_path, "rb") as f:
            wav_bytes = f.read()
        
        logger.info(f"Generated WAV size: {len(wav_bytes)} bytes")
        shutil.rmtree(temp_dir, ignore_errors=True)

        return Response(wav_bytes, mimetype="audio/wav", headers=headers)
    except Exception as e:
        logger.error(f"Error converting MIDI to audio: {e}")
        import traceback
        traceback.print_exc()
        return (f"Error: {e}", 500, headers)

@app.route("/xml-to-pdf", methods=['POST', 'OPTIONS'])
def xml_to_pdf():
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    if request.method != 'POST':
        return ('Method not allowed', 405, headers)

    try:
        xml_content = request.form.get('xml')
        if not xml_content:
             # Try getting from file
             if 'file' in request.files:
                 xml_content = request.files['file'].read().decode('utf-8')
             elif 'xml_path' in request.args:
                 # Not supported directly without bucket access logic
                 return ('xml_path not supported directly, please upload content', 400, headers)
        
        if not xml_content or not xml_content.strip():
            return ('Empty xml content', 400, headers)

        tk = verovio.toolkit()
        
        # Set resource path for fonts
        try:
            spec = importlib.util.find_spec("verovio")
            if spec and spec.origin:
                verovio_base = os.path.dirname(spec.origin)
                resource_path = os.path.join(verovio_base, "data")
                if os.path.exists(resource_path):
                    logger.info(f"Setting Verovio resource path to: {resource_path}")
                    tk.setResourcePath(resource_path)
                else:
                    logger.error(f"Verovio data directory not found at: {resource_path}")
                    logger.info(f"Contents of {verovio_base}: {os.listdir(verovio_base)}")
        except Exception as e:
            logger.error(f"Error setting Verovio resource path: {e}")

        # Configure Verovio options based on api.py
        options = {
            "scale": 80,
            "footer": "none",
            "header": "none",
            "pageHeight": 2970,
            "pageWidth": 2100,
            "unit": 10,
        }
        tk.setOptions(options)

        if not tk.loadData(xml_content):
            logger.error("Verovio failed to load XML data")
            logger.error(f"XML content preview: {xml_content[:200]}")
            return ('Verovio failed to load XML data', 400, headers)

        page_count = tk.getPageCount()
        logger.info(f"Verovio generated {page_count} pages")

        if page_count == 0:
             return ('Verovio generated 0 pages', 400, headers)

        packet = BytesIO()

        pdf_w, pdf_h = 595.0, 842.0
        c = canvas.Canvas(packet, pagesize=(pdf_w, pdf_h))

        for page in range(1, page_count + 1):
            svg = tk.renderToSVG(page)
            if not svg:
                logger.warning(f"Empty SVG for page {page}")
                continue
                
            svg = svg.replace("#00000", "#000000")
            
            try:
                drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
                if not drawing:
                     logger.warning(f"svg2rlg returned None for page {page}")
                     continue

                # Scaling logic from api.py
                scale_x = pdf_w / 21000
                scale_y = pdf_h / 29700
                scale = min(scale_x, scale_y)

                drawing.scale(scale, scale)
                
                # Offset calculation from api.py
                offset_y = -drawing.height * scale + pdf_h

                renderPDF.draw(drawing, c, 0, offset_y)
                c.showPage()
            except Exception as e:
                logger.error(f"Error rendering page {page}: {e}")

        c.save()
        packet.seek(0)
        
        pdf_content = packet.read()
        logger.info(f"Generated PDF size: {len(pdf_content)} bytes")
        
        return Response(pdf_content, mimetype="application/pdf", headers=headers)

    except Exception as e:
        logger.error(f"Verovio render error: {e}")
        import traceback
        traceback.print_exc()
        return (f"Verovio render error: {e}", 500, headers)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

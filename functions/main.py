from flask import Flask, request, jsonify
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

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin
# On Cloud Run, it uses the default service account credentials automatically
try:
    initialize_app(options={
        'storageBucket': 'fastscore-b82f4.firebasestorage.app'
    })
except ValueError:
    # App already initialized
    pass

app = Flask(__name__)


@app.route('/', methods=['POST', 'OPTIONS'])
@app.route('/audio-to-xml', methods=['POST', 'OPTIONS'])
def audio_to_xml():
    """
    HTTP endpoint to convert audio file to MusicXML
    Accepts: multipart/form-data with 'file' field containing audio
    Returns: JSON with MusicXML content and download URLs for XML and MIDI
    """
    
    # Set CORS headers for preflight request
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    # Set CORS headers for main request
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    # Only allow POST requests
    if request.method != 'POST':
        return ('Method not allowed', 405, headers)
    
    try:
        # Import here to avoid loading heavy dependencies during cold start
        import basic_pitch_convert
        
        # Get the uploaded file from the request
        if 'file' not in request.files:
            logger.warning("No file provided in request")
            return ('No file provided. Please upload a file with field name "file"', 400, headers)
        
        uploaded_file = request.files['file']
        
        if uploaded_file.filename == '':
            logger.warning("No filename selected")
            return ('No file selected', 400, headers)
        
        logger.info(f"Received file: {uploaded_file.filename}")
        
        # Get metadata from request
        user_id = request.form.get('user_id')
        title = request.form.get('title', uploaded_file.filename)
        duration = request.form.get('duration', '0:00')
        
        # Determine format from extension if not provided
        default_format = 'MP3'
        if uploaded_file.filename:
            ext = os.path.splitext(uploaded_file.filename)[1].lower()
            if ext == '.wav':
                default_format = 'WAV'
                
        audio_format = request.form.get('format', default_format)
        color = request.form.get('color')
        image_url = request.form.get('imageUrl')
        image_asset = request.form.get('imageAsset')

        # Save uploaded file to temporary location
        temp_dir = tempfile.mkdtemp()
        original_filename = uploaded_file.filename or "audio.mp3"
        audio_file_path = os.path.join(temp_dir, original_filename)
        
        uploaded_file.save(audio_file_path)
        logger.info(f"Saved temp file to {audio_file_path}")
        
        # Convert audio to MusicXML
        logger.info("Starting conversion...")
        xml_file_path, midi_file_path = basic_pitch_convert.convert(audio_file_path)
        logger.info("Conversion completed")
        
        # Read the generated MusicXML file
        with open(xml_file_path, "r", encoding="utf-8") as f:
            xml_data = f.read()
            
        # Upload to Firebase Storage
        bucket = storage.bucket()
        unique_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(original_filename)[0]
        
        # Define storage paths
        storage_path_xml = f"conversions/{timestamp}_{unique_id}/{base_name}.musicxml"
        storage_path_midi = f"conversions/{timestamp}_{unique_id}/{base_name}.mid"
        storage_path_audio = f"conversions/{timestamp}_{unique_id}/{original_filename}"
        
        # Upload XML
        blob_xml = bucket.blob(storage_path_xml)
        blob_xml.upload_from_filename(xml_file_path)
        logger.info(f"Uploaded XML to {storage_path_xml}")
        
        # Upload MIDI
        blob_midi = bucket.blob(storage_path_midi)
        blob_midi.upload_from_filename(midi_file_path)
        logger.info(f"Uploaded MIDI to {storage_path_midi}")

        # Upload Original Audio
        blob_audio = bucket.blob(storage_path_audio)
        blob_audio.upload_from_filename(audio_file_path)
        logger.info(f"Uploaded Audio to {storage_path_audio}")
        
        # Get service account email for signing
        credentials, project_id = google.auth.default()
        service_account_email = 'default'
        
        if hasattr(credentials, 'service_account_email'):
            service_account_email = credentials.service_account_email
            
        if not service_account_email or service_account_email == 'default':
            # Try to refresh to get the email
            try:
                auth_request = google_requests.Request()
                credentials.refresh(auth_request)
                service_account_email = credentials.service_account_email
            except Exception as e:
                logger.warning(f"Could not refresh credentials to get email: {e}")

        # Fallback: Try to get email from metadata server directly
        if not service_account_email or service_account_email == 'default':
            try:
                import requests
                metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
                metadata_headers = {"Metadata-Flavor": "Google"}
                response = requests.get(metadata_url, headers=metadata_headers, timeout=2)
                if response.status_code == 200:
                    service_account_email = response.text.strip()
            except Exception as e:
                logger.warning(f"Could not get email from metadata server: {e}")
        
        logger.info(f"Using service account email for signing: {service_account_email}")

        # Setup IAM signing if needed (for Cloud Run where credentials don't have private key)
        signing_credentials = credentials
        if not hasattr(credentials, 'sign_bytes'):
            try:
                if service_account_email == 'default':
                     raise ValueError("Cannot setup IAM signer with 'default' service account email")
                
                logger.info(f"Setting up impersonated credentials for signing as {service_account_email}")
                signing_credentials = impersonated_credentials.Credentials(
                    source_credentials=credentials,
                    target_principal=service_account_email,
                    target_scopes=['https://www.googleapis.com/auth/cloud-platform'],
                    lifetime=3600
                )
            except Exception as e:
                logger.error(f"Could not setup IAM signer: {e}")
                raise RuntimeError(f"Failed to setup IAM signer: {e}")

        # Generate signed URLs (valid for 7 days)
        # Note: The service account must have 'Service Account Token Creator' role
        # Using version='v4' is required when using Cloud Run service account credentials (no private key)
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
        
        # Clean up temporary files
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Save to Firestore if user_id is provided
        firestore_id = None
        if user_id:
            try:
                db = firestore.client()
                # Create a document in the user's 'songs' subcollection
                doc_ref = db.collection('users').document(user_id).collection('songs').document()
                
                song_data = {
                    'userId': user_id,
                    'date': datetime.datetime.now().strftime("%Y-%m-%d"), # Format as YYYY-MM-DD for display
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
                    'createdAt': firestore.SERVER_TIMESTAMP
                }
                
                # Remove None values
                song_data = {k: v for k, v in song_data.items() if v is not None}
                
                doc_ref.set(song_data)
                firestore_id = doc_ref.id
                logger.info(f"Saved song metadata to Firestore for user {user_id}, doc ID: {firestore_id}")
            except Exception as e:
                logger.error(f"Error saving to Firestore: {e}")
                # Don't fail the whole request if Firestore save fails, but log it
        
        # Return JSON response
        response_data = {
            "xml_content": xml_data,
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
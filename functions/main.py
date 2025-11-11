from firebase_functions import https_fn
from firebase_functions.options import set_global_options, CorsOptions
from firebase_admin import initialize_app
import tempfile
import os
import shutil

set_global_options(max_instances=10)

initialize_app()


@https_fn.on_request(
    memory=1024,  # Increase memory to 1GB for TensorFlow
    timeout_sec=540,  # Increase timeout to 9 minutes for audio processing
    cpu=2,  # Use 2 CPUs for faster processing
    cors=CorsOptions(
        cors_origins=["*"],
        cors_methods=["GET", "POST", "OPTIONS"]
    )
)
def audio_to_xml(req: https_fn.Request) -> https_fn.Response:
    """
    Cloud Function to convert audio file to MusicXML
    Accepts: multipart/form-data with 'file' field containing audio
    Returns: MusicXML content
    """
    
    # Handle OPTIONS request for CORS preflight
    if req.method == "OPTIONS":
        return https_fn.Response(
            "",
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization",
                "Access-Control-Max-Age": "3600",
            }
        )
    
    # Only allow POST requests
    if req.method != "POST":
        return https_fn.Response(
            "Method not allowed", 
            status=405,
            headers={"Access-Control-Allow-Origin": "*"}
        )
    
    try:
        # Import here to avoid loading heavy dependencies during deployment analysis
        import basic_pitch_convert
        
        # Get the uploaded file from the request
        files = req.files
        if not files or 'file' not in files:
            return https_fn.Response(
                "No file provided. Please upload a file with field name 'file'",
                status=400,
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        uploaded_file = files['file']
        
        # Save uploaded file to temporary location
        temp_dir = tempfile.mkdtemp()
        audio_file_path = os.path.join(temp_dir, uploaded_file.filename or "audio.mp3")
        
        uploaded_file.save(audio_file_path)
        
        # Convert audio to MusicXML
        xml_file_path, midi_file_path = basic_pitch_convert.convert(audio_file_path)
        
        # Read the generated MusicXML file
        with open(xml_file_path, "r", encoding="utf-8") as f:
            xml_data = f.read()
        
        # Clean up temporary files
        shutil.rmtree(temp_dir, ignore_errors=True)
        if os.path.exists(xml_file_path):
            os.remove(xml_file_path)
        
        # Return MusicXML response
        return https_fn.Response(
            xml_data,
            status=200,
            headers={
                "Content-Type": "application/xml",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except Exception as e:
        print(f"Error processing audio file: {str(e)}")
        return https_fn.Response(
            f"Error processing audio file: {str(e)}",
            status=500,
            headers={"Access-Control-Allow-Origin": "*"}
        )
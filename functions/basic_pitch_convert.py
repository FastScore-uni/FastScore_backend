import shutil
import tempfile
import os
from basic_pitch.inference import predict_and_save
from basic_pitch import ICASSP_2022_MODEL_PATH
from pathlib import Path
from music21 import converter


def generate_midi(audio_path):
    """Generate MIDI file from audio using Basic Pitch"""
    output_dir = Path(tempfile.gettempdir()) / "basic_pitch_output"
    
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()
    
    predict_and_save(
        [audio_path],
        output_dir,
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=True,
        model_path=ICASSP_2022_MODEL_PATH
    )
    
    generated_midi_path = str(output_dir / f"{Path(audio_path).stem}_basic_pitch.mid")
    return generated_midi_path


def convert(audio_path):
    """Convert audio file to MusicXML format"""
    midi_path = generate_midi(audio_path)
    score = converter.parse(midi_path)
    
    # Create output file in temp directory
    output_path = os.path.join(tempfile.gettempdir(), "output.musicxml")
    score.write("musicxml", output_path)
    
    return output_path, midi_path

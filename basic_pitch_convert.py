import shutil

from basic_pitch.inference import predict_and_save
from basic_pitch import ICASSP_2022_MODEL_PATH
from pathlib import Path
from music21 import converter

_output_dir = "basic_pitch_output"

def generate_midi(audio_path):
    output_dir = Path(_output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()
    predict_and_save(
        [audio_path],           # lista plików audio
        output_dir,              # katalog wyjściowy
        save_midi=True,          # czy zapisywać MIDI
        sonify_midi=False,       # czy zapisywać podgląd audio z MIDI
        save_model_outputs=False,# czy zapisywać raw output modelu
        save_notes=True,        # czy zapisywać nuty w CSV
        model_or_model_path=ICASSP_2022_MODEL_PATH # None = domyślny model
    )
    generated_midis_dict = str(output_dir / f"{Path(audio_path).stem}_basic_pitch.mid")
    return generated_midis_dict

def convert(audio_path):
    output_filename = "output.musicxml"
    midi_path = generate_midi(audio_path)
    score = converter.parse(midi_path)
    score.write("musicxml", output_filename)
    return output_filename, midi_path

if __name__ == "__main__":
    convert("melodia.wav")
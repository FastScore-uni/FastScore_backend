from basic_pitch.inference import predict_and_save
from basic_pitch import ICASSP_2022_MODEL_PATH
from pathlib import Path
import shutil
from music21 import converter

_output_dir = "basic_pitch_output"

def _generate_midi(audio_path):
    # results, midi_data, note_events = model_inference(
    #     audio,
    #     sr,
    #     model_or_model_path=ICASSP_2022_MODEL_PATH,
    # )
    # midi_data.tempo = 120   # BPM

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
    midi_path = str(output_dir / f"{Path(audio_path).stem}_basic_pitch.mid")
    return midi_path

def convert(audio_path, output_filename="output.musicxml"):
    midi_path = _generate_midi(audio_path)
    score = converter.parse(midi_path)
    score.write("musicxml", output_filename)
    return output_filename, midi_path

if __name__ == "__main__":
    convert("preprocessed.wav")
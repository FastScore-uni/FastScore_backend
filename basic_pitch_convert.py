from basic_pitch.inference import predict_and_save
from basic_pitch import ICASSP_2022_MODEL_PATH
from pathlib import Path
import shutil
from music21 import converter
import mido

import notes_tools

_output_dir = "basic_pitch_output"

def _generate_midi(audio_path):
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

def _set_midi_tempo(midi_path, bpm, out_path=None):
    if out_path is None:
        out_path = midi_path

    mid = mido.MidiFile(midi_path)

    # Convert BPM to microseconds per beat
    tempo = mido.bpm2tempo(bpm)

    # Modify existing tempo messages, or insert a new one
    changed = False
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                msg.tempo = tempo
                changed = True

    # If there was no tempo event, insert it at start of track 0
    if not changed:
        mid.tracks[0].insert(0, mido.MetaMessage('set_tempo', tempo=tempo, time=0))

    mid.save(out_path)
    return out_path


def convert(audio_path, output_filename="output.musicxml"):
    midi_path = _generate_midi(audio_path)
    bpm = notes_tools.predict_tempo(audio_path)
    _set_midi_tempo(midi_path, bpm)
    xml_path = notes_tools.generate_xml(midi_path, output_filename)
    return xml_path, midi_path

if __name__ == "__main__":
    convert("preprocessed.wav")
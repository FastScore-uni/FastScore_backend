import librosa
import essentia
import essentia.standard as es
import numpy as np
from music21 import converter
import notes_tools

_output_dir = "melodia_output"

def _audio_to_midi_melodia(audio_path):
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    audio = essentia.array(y.astype(np.float32))
    melody = es.PredominantMelody()
    f0, confidence = melody(audio)

    hop_size = 128
    time_step = hop_size / sr
    time = np.arange(len(f0)) * time_step

    bpm = notes_tools.predict_tempo(audio_path)
    time_step = 0.01

    notes = notes_tools.generate_notes(y, sr, time, f0, confidence, time_step)
    return notes_tools.save_notes_to_midi(notes, _output_dir, bpm=bpm)

# ------------------------------------------------
# Metody publiczne:
# ------------------------------------------------

def convert(audio_path, output_filename="output.musicxml"):
    midi_path = _audio_to_midi_melodia(audio_path)
    score = converter.parse(midi_path)
    score.write("musicxml", output_filename)
    return output_filename, midi_path

if __name__ == "__main__":
    convert("Tytuł.wav")
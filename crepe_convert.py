import librosa
import crepe
from music21 import converter
import notes_tools

_output_dir = "crepe_output"

def _audio_to_midi_crepe(audio_path):
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    bpm = notes_tools.predict_tempo(y, sr)
    print(f"Audio załadowane: {len(y)/sr:.2f} s, {sr} Hz")

    time, f0, confidence, activation = crepe.predict(y, sr, viterbi=True)
    print("CREPE zakończony:", len(f0), "ramek")
    time_step = 0.01


    notes = notes_tools.generate_notes(y, sr, time, f0, confidence, time_step)
    return notes_tools.save_notes_to_midi(notes, _output_dir, bpm=bpm)

# ------------------------------------------------
# Metody publiczne:
# ------------------------------------------------

def convert(audio_path, output_filename="output.musicxml"):
    midi_path = _audio_to_midi_crepe(audio_path)
    score = converter.parse(midi_path)
    score.write("musicxml", output_filename)
    return output_filename, midi_path

if __name__ == "__main__":
    convert("Tytuł.wav")
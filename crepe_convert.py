import crepe
from music21 import converter
import notes_tools
import audio_preprocessing

_output_dir = "crepe_output"

def _audio_to_midi_crepe(y, sr, bpm):
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
    y, sr = audio_preprocessing.preprocess_audio(audio_path)
    bpm = notes_tools.predict_tempo(audio_path)
    midi_path = _audio_to_midi_crepe(y, sr, bpm)
    score = converter.parse(midi_path)
    score.write("musicxml", output_filename)
    return output_filename, midi_path

if __name__ == "__main__":
    convert("uploads/recording_1.wav")
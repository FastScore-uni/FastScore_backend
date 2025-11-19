import numpy as np
import librosa
import crepe
import scipy.signal
from mido import Message, MidiFile, MidiTrack, bpm2tempo
from pathlib import Path
import shutil
from music21 import converter

_output_dir = "crepe_output"

# ================================================
# CREPE Notes – implementacja na podstawie pracy: Riley & Dixon (2023)
# ================================================

def _generate_notes(audio_path):
    """
    Method for generating notes from music file

    :param audio_path: Path to wav file
    :return: Tempo in bpm; List of notes in format: (onset_time, offset_time, midi_val, amp)
    """

    # 1. Wczytanie pliku audio
    # ------------------------------------------------
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    print(f"Audio załadowane: {len(y)/sr:.2f} s, {sr} Hz")

    # 2. Ekstrakcja f0 i confidence przy użyciu CREPE
    # ------------------------------------------------
    time, f0, confidence, activation = crepe.predict(y, sr, viterbi=True)
    time_step = 0.01
    print("CREPE zakończony:", len(f0), "ramek")

    # 3. Konwersja częstotliwości na skalę MIDI (logarytmiczną)
    # ------------------------------------------------
    # Unikamy log(0) -> pomijamy wartości zerowe lub bardzo małe
    f0_safe = np.copy(f0)
    f0_safe[f0_safe < 1] = np.nan
    midi_pitch = 69 + 12 * np.log2(f0_safe / 440.0)
    print(midi_pitch)

    # 4. Obliczenie gradientu wysokości dźwięku (pitch gradient)
    # ------------------------------------------------
    pitch_grad = np.abs(np.gradient(midi_pitch))
    pitch_grad = np.nan_to_num(pitch_grad)  # usuń NaNy
    pitch_grad /= np.max(pitch_grad)        # normalizacja [0..1]

    # 5. Odwrócenie confidence i połączenie sygnałów
    # ------------------------------------------------
    inv_conf = 1.0 - confidence
    combined = inv_conf * pitch_grad

    # 6. Detekcja pików w sygnale łączonym (kandydaci na granice nut)
    # ------------------------------------------------
    threshold = 0.002  # wartość domyślna z artykułu
    peaks, _ = scipy.signal.find_peaks(combined, height=threshold)
    note_boundaries = time[peaks]
    print("Znaleziono kandydatów na granice nut:", len(note_boundaries))

    # 7. Segmentacja według granic
    # ------------------------------------------------
    segments = []
    start = 0
    for boundary in peaks:
        end = boundary
        segments.append((start, end))
        start = end
    segments.append((start, len(f0)))  # ostatni segment

    # 8. Scalanie sąsiednich segmentów jeśli różnica < 1 półtonu
    # ------------------------------------------------
    merged_segments = []
    prev_seg = segments[0]
    for seg in segments[1:]:
        s1, e1 = prev_seg
        s2, e2 = seg
        med1 = np.nanmedian(midi_pitch[s1:e1])
        med2 = np.nanmedian(midi_pitch[s2:e2])
        if abs(med1 - med2) < 1:  # mniej niż 1 półton
            prev_seg = (s1, e2)
        else:
            merged_segments.append(prev_seg)
            prev_seg = seg
    merged_segments.append(prev_seg)

    print("Po scaleniu:", len(merged_segments), "segmentów")

    # 9. (Opcjonalne) wykrywanie powtórzonych nut
    # ------------------------------------------------
    # Użycie detekcji onsetów z Librosa jako wsparcie
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True)
    onset_times = librosa.frames_to_time(onsets, sr=sr)
    # Można użyć tych onsetów do podziału długich segmentów, jeśli zachodzi potrzeba.

    # 10. Amplituda, odfiltrowanie cichych i krótkich nut
    # ------------------------------------------------
    velocity_threshold = 0.02
    min_duration = 0.03       # 30 ms
    notes = []

    for (s, e) in merged_segments:
        seg_audio = y[int(s*sr*0.01):int(e*sr*0.01)]  # 0.01s = 10ms
        if len(seg_audio) == 0:
            continue
        amp = np.max(np.abs(seg_audio))
        dur = (e - s) * 0.01
        if amp < velocity_threshold or dur < min_duration:
            continue
        midi_val = np.nanmedian(np.round(midi_pitch[s:e]))
        onset_time = s * 0.01
        offset_time = e * 0.01
        notes.append((onset_time, offset_time, midi_val, amp))

    print("Ostateczna liczba nut:", len(notes))
    return tempo, notes

def _save_notes_to_midi(notes, output_file_name="output.mid", bpm=120):
    """
    Zapisuje listę nut (onset, offset, pitch, velocity)
    do pliku MIDI.

    notes: [(onset_s, offset_s, midi_pitch, amplitude)]
    """
    output_dir = Path(_output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    midi = MidiFile()
    track = MidiTrack()
    midi.tracks.append(track)

    # tempo (mikrosekundy na kwartę)
    tempo = bpm2tempo(bpm)
    ticks_per_beat = midi.ticks_per_beat

    def seconds_to_ticks(sec):
        # przeliczenie czasu w sekundach na tzw. "ticks" MIDI
        return int(sec * (1_000_000 / tempo) * ticks_per_beat)

    current_time = 0
    for onset, offset, pitch, amp in notes:
        velocity = int(min(max(amp * 127, 0), 127))  # skala 0–127

        # czas w tickach
        onset_ticks = seconds_to_ticks(onset)
        offset_ticks = seconds_to_ticks(offset)

        delta_on = onset_ticks - current_time
        delta_off = offset_ticks - onset_ticks

        # komunikaty NOTE ON i NOTE OFF
        track.append(Message('note_on', note=int(pitch), velocity=velocity, time=max(delta_on, 0)))
        track.append(Message('note_off', note=int(pitch), velocity=0, time=max(delta_off, 1)))

        current_time = offset_ticks

    output_path = output_dir / output_file_name
    midi.save(output_path)
    print(f"✅ Zapisano {len(notes)} nut do pliku: {output_path}")
    return output_path

# ------------------------------------------------
# Metody publiczne:
# ------------------------------------------------

def convert(audio_path, output_filename="output.musicxml"):
    bpm, notes = _generate_notes(audio_path)
    midi_path = _save_notes_to_midi(notes, bpm=bpm)
    score = converter.parse(midi_path)
    score.write("musicxml", output_filename)
    return output_filename, midi_path

if __name__ == "__main__":
    convert("melodia.wav")
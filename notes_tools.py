# ================================================
# CREPE Notes – implementacja na podstawie pracy: Riley & Dixon (2023)
# ================================================

import numpy as np
import librosa
import scipy.signal
from mido import Message, MidiFile, MidiTrack, bpm2tempo
from pathlib import Path
import shutil
import essentia.standard as es
import matplotlib.pyplot as plt
from music21 import converter

def generate_notes(y, sr, time, f0, confidence, time_step):
    """
    Method for generating note events from values extracted from an audio file.

    :param y: Audio time-series samples
    :param sr: Sampling rate of the audio signal
    :param time: Time axis corresponding to the analyzed features
    :param f0: Fundamental frequency (pitch) values over time
    :param confidence: Confidence values for each f0 estimate
    :param time_step: Temporal resolution between consecutive f0 frames
    :return: List of notes in format: (onset_time, offset_time, midi_val, amplitude)
    """

    # 1. Konwersja częstotliwości na skalę MIDI (logarytmiczną)
    # ------------------------------------------------
    # Unikamy log(0) -> pomijamy wartości zerowe lub bardzo małe
    f0_safe = np.copy(f0)
    f0_safe[f0_safe < 1] = np.nan
    midi_pitch = 69 + 12 * np.log2(f0_safe / 440.0)

    # 2. Obliczenie gradientu wysokości dźwięku (pitch gradient)
    # ------------------------------------------------
    pitch_grad = np.abs(np.gradient(midi_pitch))
    pitch_grad = np.nan_to_num(pitch_grad)  # usuń NaNy
    pitch_grad /= np.max(pitch_grad)        # normalizacja [0..1]

    # 3. Odwrócenie confidence i połączenie sygnałów
    # ------------------------------------------------
    inv_conf = 1.0 - confidence
    combined = inv_conf * pitch_grad

    # 4. Detekcja pików w sygnale łączonym (kandydaci na granice nut)
    # ------------------------------------------------
    threshold = 0.002  # wartość domyślna z artykułu
    confidence_threshold = 0.2
    peaks, _ = scipy.signal.find_peaks(combined, height=threshold)
    peaks = [p for p in peaks if confidence[p]>confidence_threshold]
    note_boundaries = time[peaks]
    print("Znaleziono kandydatów na granice nut:", len(note_boundaries))

    # 5. Segmentacja według granic
    # ------------------------------------------------
    segments = []
    start = 0
    for boundary in peaks:
        end = boundary
        segments.append((start, end))
        start = end
    segments.append((start, len(f0)))  # ostatni segment

    # 6. Scalanie krótkich i sąsiednich segmentów jeśli różnica < 1 półtonu
    # ------------------------------------------------
    merged_segments = []
    prev_seg = segments[0]
    min_duration = 0.06       # 80 ms
    for seg in segments[1:]:
        s1, e1 = prev_seg
        s2, e2 = seg
        if (e1 - s1) * time_step < min_duration:
            prev_seg = s1, e2
        else:
            med1 = np.nanmedian(midi_pitch[s1:e1])
            med2 = np.nanmedian(midi_pitch[s2:e2])
            if abs(med1 - med2) < 0.8:  # mniej niż 1 półton
                prev_seg = (s1, e2)
            else:
                merged_segments.append(prev_seg)
                prev_seg = seg
    merged_segments.append(prev_seg)

    print("Po scaleniu:", len(merged_segments), "segmentów")

    # 7. (Opcjonalne) wykrywanie powtórzonych nut
    # ------------------------------------------------
    # Użycie detekcji onsetów z Librosa jako wsparcie
    # onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    # onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True)
    # onset_times = librosa.frames_to_time(onsets, sr=sr)
    # Można użyć tych onsetów do podziału długich segmentów, jeśli zachodzi potrzeba.

    # 8. Amplituda, odfiltrowanie cichych i krótkich nut
    # ------------------------------------------------
    confidence_threshold_2 = 0.5
    mean_velocity = np.mean([np.max(np.abs(y[int(s*sr*time_step):int(e*sr*time_step)])) for s, e in merged_segments])
    velocity_threshold = mean_velocity / 20 # 5% of mean velocity
    print(f"velocity threshold {velocity_threshold}")
    notes = []

    for (s, e) in merged_segments:
        if np.nanmedian(confidence[s:e]) < confidence_threshold_2:
            continue
        seg_audio = y[int(s*sr*time_step):int(e*sr*time_step)]  # 0.01s = 10ms
        if len(seg_audio) == 0:
            continue
        amp = np.max(np.abs(seg_audio))
        dur = (e - s) * time_step
        if amp < velocity_threshold or dur < min_duration:
            continue
        midi_val = np.nanmedian(np.round(midi_pitch[s:e]))
        onset_time = s * time_step
        offset_time = e * time_step
        notes.append((onset_time, offset_time, midi_val, amp))
        print(f"onset_time {onset_time}, offset_time {offset_time}, midi_val {midi_val}, amp {amp}, duration:{dur}")

    target_mean = 50.0
    min_velocity = 20.0
    max_velocity = 80.0
    old_mean = float(np.nanmean([amp for _, _, _, amp in notes]))
    notes = [(val1, val2, val3, max(min_velocity, min(max_velocity, (amp * target_mean / old_mean))))
             for val1, val2, val3, amp in notes]

    print("Ostateczna liczba nut:", len(notes))
    # plt.figure(figsize=(12, 6))
    #
    # plt.subplot(4, 1, 4)
    # plt.plot(y, label="y")
    # plt.title("4. Wysokość dźwięku")
    # plt.xlabel("Czas [s]")
    # plt.ylabel("y pitch")
    #
    # plt.subplot(4, 1, 1)
    # plt.plot(time, midi_pitch, label="Pitch (MIDI)")
    # plt.title("1. Wysokość dźwięku (CREPE)")
    # plt.xlabel("Czas [s]");
    # plt.ylabel("MIDI pitch")
    #
    # plt.subplot(4, 1, 2)
    # plt.plot(time, confidence, label="Confidence", color="orange")
    # plt.title("2. Confidence (CREPE)")
    # plt.xlabel("Czas [s]");
    # plt.ylabel("Confidence")
    #
    # plt.subplot(4, 1, 3)
    # plt.plot(time, combined, label="Combined", color="green")
    # plt.scatter(time[peaks], combined[peaks], color="red", label="Peaks")
    # plt.title("3. Combined = (1 - confidence) * |gradient|")
    # plt.xlabel("Czas [s]")
    # plt.ylabel("Połączony sygnał")
    # plt.legend()
    # plt.tight_layout()
    # plt.show()
    return notes

def save_notes_to_midi(notes, output_dir, output_file_name="output.mid", bpm=120):
    """
    Saves a list of notes to a MIDI file.

    :param notes: List in the format: [(onset_s, offset_s, midi_pitch, amplitude)]
    :param output_dir: Path to the output directory
    :param output_file_name: Target MIDI file name
    :param bpm: Tempo of the piece in beats per minute
    :return: Path to the resulting MIDI file
    """

    output_dir = Path(output_dir)
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

def predict_tempo(filepath):
    """
    Estimates the tempo (beats per minute) of an audio signal.

    :param filepath: Path to an audiofile
    :return: Estimated tempo in BPM
    """
    try:
        audio = es.MonoLoader(filename=filepath)()
        bpm, _, _, _ = es.RhythmExtractor()(audio)
        print(f"Wykryte tempo: {bpm}bpm")
    except Exception:
        bpm = 0

    if bpm <= 0:
        y, sr = librosa.load(librosa.ex('choice'), duration=10)
        [bpm], _ = librosa.beat.beat_track(y=y, sr=sr)
        print(f"Wykryte tempo (librosa): {bpm}")
        if bpm <= 0:
            bpm = 120
            print(f"Tempo zastąpione domyślną wartością: {bpm}")
    bpm = int(round(bpm, 0))
    return bpm

def generate_xml(midi_path, output_filename):
    score = converter.parse(midi_path)
    for p in score.parts:
        p.partName = ""
        p.partAbbreviation = ""
    score.write("musicxml", output_filename)
    return output_filename
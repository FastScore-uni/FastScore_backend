import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf
import scipy.signal as sps

def preprocess_audio(
    path: str,
    only_load: bool = False,
    target_sr: int = 16000,
    target_lufs: float = -23.0
):
    """
    Preprocessing:
    - load & resample
    - trim silence
    - noise reduction
    - LUFS loudness normalization
    - clipping prevention
    Returns y, sr
    """

    # === Load ===
    y, sr = librosa.load(path, sr=target_sr)
    if only_load:
        return y, sr

    # === 2. Remove DC offset ===
    y = y - np.mean(y)

    # === LUFS normalize ===
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(y)
    y = pyln.normalize.loudness(y, loudness, target_lufs)

    # === 4. Denoise (prosta metoda spectral gating) ===
    # tutaj używamy wbudowanej redukcji szumu w librosa
    # możesz użyć: noisereduce, wiener, spectral subtraction itd.
    stft = librosa.stft(y)
    magnitude, phase = np.abs(stft), np.angle(stft)
    noise_profile = np.mean(magnitude[:, :10], axis=1, keepdims=True)
    magnitude_clean = np.maximum(magnitude - noise_profile, 0.0)
    y = librosa.istft(magnitude_clean * np.exp(1j*phase))

    # === 5. Remove clicks (median filtering) ===
    y = sps.medfilt(y, kernel_size=5)

    # === 6. Remove silence ===
    silence_thresh = 40
    clips = librosa.effects.split(y, top_db=silence_thresh)
    y = np.concatenate([y[start:end] for start, end in clips])

    # === Anti clipping ===
    y = np.clip(y, -1.0, 1.0)
    print(max(y))

    sf.write("preprocessed.wav", y, sr)
    return y, sr

if __name__=="__main__":
    preprocess_audio("uploads_arch/Tytuł.wav", preprocess=True)
# Use Python 3.11 base image with GPU support (CUDA 11.8 for TensorFlow 2.12)
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Install Python 3.11 and ffmpeg
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    ffmpeg \
    fluidsynth \
    fluid-soundfont-gm \
    build-essential \
    meson \
    ninja-build \
    pkg-config \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Download Crepe models during build to avoid runtime download errors
# Run a dummy prediction to trigger the model download
RUN python3 -c "import numpy as np; import crepe; crepe.predict(np.zeros(16000), 16000, viterbi=True, model_capacity='full', verbose=0)"

# Copy application code
COPY . .

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Run the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app

def crepe_worker(conn):
    import crepe_convert
    while True:
        audio = conn.recv()
        if audio is None:
            break
        result = crepe_convert.convert(audio_path=audio)
        conn.send(result)

def basic_pitch_worker(conn):
    import basic_pitch_convert
    while True:
        audio = conn.recv()
        if audio is None:
            break
        result = basic_pitch_convert.convert(audio_path=audio)
        conn.send(result)

def melody_ext_worker(conn):
    import melodia_convert
    while True:
        audio = conn.recv()
        if audio is None:
            break
        result = melodia_convert.convert(audio_path=audio)
        conn.send(result)
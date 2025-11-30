def crepe_worker(conn):
    import crepe_convert
    while True:
        audio = conn.recv()
        if audio is None:
            return
        try:
            result = crepe_convert.convert(audio_path=audio)
            conn.send(result)
        except Exception as e:
            print(f"Crepe worker exception: {e}")
            conn.send("", "")

def basic_pitch_worker(conn):
    import basic_pitch_convert
    while True:
        audio = conn.recv()
        if audio is None:
            return
        try:
            result = basic_pitch_convert.convert(audio_path=audio)
            conn.send(result)
        except Exception as e:
            print(f"Crepe worker exception: {e}")
            conn.send("", "")

def melody_ext_worker(conn):
    import melodia_convert
    while True:
        audio = conn.recv()
        if audio is None:
            return
        try:
            result = melodia_convert.convert(audio_path=audio)
            conn.send(result)
        except Exception as e:
            print(f"Crepe worker exception: {e}")
            conn.send("", "")
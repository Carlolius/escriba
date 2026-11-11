"""Nombrar hablantes y escribir la transcripción final.

Lo comparten el modo local (whisper + pyannote, local.py) y el modo nube
(nube.py): los dos producen segmentos de texto y turnos de hablante con
tiempos, y a partir de ahí el resultado es el mismo .txt y el mismo
.speakers.json que luego se revisa (revisar.py).

- segments:      [(inicio_s, fin_s, texto)]
- speaker_turns: [(inicio_s, fin_s, id_hablante)]
"""
import json
import os

from . import voiceprints


def _nombre_sin_match(hablante_list, n):
    return hablante_list[n - 1] if n <= len(hablante_list) else f"Hablante {n}"


def nombrar_hablantes(audio, salida, speaker_turns, proyecto, hablante_list):
    """Devuelve {id_hablante: nombre}. Con proyecto, identifica por voz contra
    voiceprints/<proyecto>.json y guarda el sidecar .speakers.json; sin él,
    usa hablante_list en orden de aparición."""
    speaker_ids = sorted(set(s for _, _, s in speaker_turns))
    speaker_map = {}

    if not proyecto:
        for i, spk in enumerate(speaker_ids):
            speaker_map[spk] = _nombre_sin_match(hablante_list, i + 1)
        return speaker_map

    import numpy as np
    import soundfile as sf
    from resemblyzer import VoiceEncoder

    libreria = voiceprints.cargar_libreria(proyecto)
    if not libreria:
        print(f"AVISO: el proyecto {proyecto} aún no tiene voces guardadas: sin identificación por voz")
    encoder = VoiceEncoder()
    by_speaker = {}
    for s, e, spk in speaker_turns:
        by_speaker.setdefault(spk, []).append((s, e))

    cluster_info = {}
    sin_match = 0
    audio_abs = os.path.abspath(audio)
    for spk, segs in by_speaker.items():
        segs_ordenados = sorted(segs, key=lambda x: x[1] - x[0], reverse=True)
        origen_s, origen_e = segs_ordenados[0]
        origen_e = min(origen_e, origen_s + 8.0)
        trozos, recogido = [], 0.0
        with sf.SoundFile(audio) as f:
            sr = f.samplerate
            for s, e in segs_ordenados:
                if recogido >= 15.0:
                    break
                dur = min(e - s, 8.0)
                f.seek(int(s * sr))
                trozos.append(f.read(int(dur * sr), dtype="float32"))
                recogido += dur
        if not trozos:
            sin_match += 1
            speaker_map[spk] = _nombre_sin_match(hablante_list, sin_match)
            continue
        emb = encoder.embed_utterance(np.concatenate(trozos))
        nombre, sim = voiceprints.identificar(emb, libreria)
        if nombre:
            speaker_map[spk] = nombre
            print(f"  {spk} -> {nombre} (similitud {sim:.2f})")
        else:
            sin_match += 1
            speaker_map[spk] = _nombre_sin_match(hablante_list, sin_match)
            print(f"  {spk} -> sin identificar (mejor similitud {sim:.2f}) -> {speaker_map[spk]}")
        cluster_info[spk] = {
            "nombre": speaker_map[spk],
            "similitud": sim,
            "duracion_hablada": sum(e - s for s, e in segs),
            "embedding": emb.tolist(),
            "origen": {"audio": audio_abs, "inicio": origen_s, "fin": origen_e},
        }

    sidecar = os.path.splitext(salida)[0] + ".speakers.json"
    with open(sidecar, "w", encoding="utf-8") as sf_out:
        json.dump({"proyecto": proyecto, "clusters": cluster_info}, sf_out, ensure_ascii=False)
    print(f"  Guardado {sidecar} (para revisar los hablantes luego)")
    return speaker_map


def escribir_transcripcion(salida, segments, speaker_turns=None, speaker_map=None):
    """Escribe el .txt. Con turnos de hablante, a cada segmento le toca el
    hablante con más solapamiento temporal y se pone cabecera al cambiar."""
    def get_speaker(start, end):
        best_spk, best_overlap = None, 0.0
        for t0, t1, spk in speaker_turns:
            overlap = min(end, t1) - max(start, t0)
            if overlap > best_overlap:
                best_overlap, best_spk = overlap, spk
        return speaker_map.get(best_spk, best_spk) if best_spk else "?"

    with open(salida, "w", encoding="utf-8") as f:
        prev_speaker = None
        for start, end, text in segments:
            if speaker_turns:
                speaker = get_speaker(start, end)
                if speaker != prev_speaker:
                    line = f"\n[{int(start)}s] {speaker}:\n{text}"
                    prev_speaker = speaker
                else:
                    line = f"[{int(start)}s] {text}"
            else:
                line = f"[{int(start)}s] {text}"
            print(line)
            f.write(line + "\n")

    print(f"\nGuardado: {salida}")

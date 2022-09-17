import os
import base64
import torch
import numpy as np
import tensorflow as tf
from scipy.io import wavfile
import io
from nemo.collections.tts.models import TalkNetSpectModel
from nemo.collections.tts.models import TalkNetPitchModel
from nemo.collections.tts.models import TalkNetDursModel
from core.talknet_singer import TalkNetSingerModel
import traceback
import time
from core import extract, vocoder, reconstruct
from core.download import download_from_drive, download_reconst
from dataclasses import dataclass
from typing import Optional, Iterable, Dict
import json
from pathlib import Path
from collections import defaultdict


DEVICE = "cpu"
CPU_PITCH = True
RUN_PATH = os.path.dirname(os.path.realpath(__file__))
torch.set_grad_enabled(False)
if CPU_PITCH:
    tf.config.set_visible_devices([], "GPU")

extract_dur = extract.ExtractDuration(RUN_PATH, DEVICE)
extract_pitch = extract.ExtractPitch()
reconstruct_inst = reconstruct.Reconstruct(
    DEVICE,
    os.path.join(
        RUN_PATH,
        "core",
        "vqgan_config.yaml",
    ),
    os.path.join(
        RUN_PATH,
        "models",
        "vqgan32_universal_57000.ckpt",
    ),
)


def analyse_file(fpath: str) -> tuple:
    # (f0_with_silence | current-f0s, f0_wo_silence | current-f0s-nosilence)
    return extract_pitch.get_pitch(
        fpath+'_conv.wav',
        legacy=True,
    )

def debug_pitch(fpath: str):
    current_f0s, _ = analyse_file(fpath)
    return extract_pitch.f0_to_audio(current_f0s)

@dataclass
class CachedModel:
    tnmodel: TalkNetSingerModel
    tnpitch: TalkNetPitchModel
    tndurs: TalkNetDursModel
    tnpath: str
    #
    voc: vocoder.HiFiGAN
    vocoder_path: str

def load_model(drive_id: str, custom_model=None):
    if custom_model is not None: raise NotImplementedError('custom models not allowed')
    load_error, talknet_path, vocoder_path = download_from_drive(
        drive_id, custom_model, RUN_PATH
    )
    if load_error is not None: raise RuntimeError(load_error)
    #
    with torch.no_grad():
        def tn_subpath(fname: str):
            return os.path.join(
                os.path.dirname(talknet_path), fname
            )
        durs_path   = tn_subpath("TalkNetDurs.nemo")
        pitch_path  = tn_subpath("TalkNetPitch.nemo")
        singer_path = tn_subpath("TalkNetSinger.nemo")
        #
        tnmodel = TalkNetSingerModel.restore_from(singer_path)\
            if os.path.exists(singer_path) else\
            TalkNetSpectModel.restore_from(talknet_path)
        #
        if os.path.exists(durs_path):
            tndurs = TalkNetDursModel.restore_from(durs_path)
            tnmodel.add_module("_durs_model", tndurs)
            tnpitch = TalkNetPitchModel.restore_from(pitch_path)
            tnmodel.add_module("_pitch_model", tnpitch)
        else: tndurs,tnpitch = None,None
        #
        tnmodel.eval()
        voc = vocoder.HiFiGAN(vocoder_path, "config_v1", DEVICE)
    return CachedModel(tnmodel, tnpitch, tndurs, talknet_path, voc, vocoder_path)

# all_dict[source][is_singing][name][drive_id] == json_source
all_dict = defaultdict(lambda: (defaultdict(dict), defaultdict(dict)))
for filename in Path('model_lists').iterdir():
    if filename.suffix.lower() != '.json':
        continue
    with open(filename) as f:
        for s in json.load(f):
            d = all_dict[s["source"]]
            for c in s["characters"]:
                # this is extremely unperformant, but model lists are small, so:
                d[c['is_singing']][c["name"]][c["drive_id"]] = filename.stem

name_to_driveid = {}
model_options = []
from functools import lru_cache
MODEL_CACHE_SIZE = 4
PRELOAD_MODELS = True
@lru_cache(maxsize=MODEL_CACHE_SIZE)
def get_model(model_name: str, custom_model=None):
    drive_id = name_to_driveid.get(model_name, None)
    if drive_id is None: raise ValueError(f'Model {model_name} not found!')
    return load_model(drive_id, custom_model)

def add_opt(title: str, disabled=False):
    model_options.append({'title': title, 'disabled': disabled})
def iterate_through_characters(characters: Dict[str,Dict[str,str]]):
    for name,models in sorted(characters.items()):
        if len(models) == 1:
            add_opt(name)
            name_to_driveid[name] = next(iter(models.keys()))
            if PRELOAD_MODELS: get_model(name)
        else:
            for drive_id, json_source in sorted(models.items()):
                fullname = f'{name} [{json_source}]'
                add_opt(fullname)
                name_to_driveid[fullname] = drive_id
                if PRELOAD_MODELS: get_model(fullname)

#TODO: style (greyed out)
for source, (talking,singing) in sorted(all_dict.items()):
    add_opt(f'--- {source} MODELS{bool(singing)*" (TALKING)"} ---',True)
    iterate_through_characters(talking)
    if singing:
        add_opt(f'--- {source} MODELS (SINGING) ---',True)
        iterate_through_characters(singing)
with open('static/model_list.json', 'w') as f:
    json.dump(model_options,f)

sr_path = os.path.join(RUN_PATH, "models", "hifisr")
if not os.path.exists(sr_path): # force load at least one model to download hifisr
    get_model(next(iter(name_to_driveid.keys())))
sr_voc = vocoder.HiFiGAN(sr_path, "config_32k", DEVICE)
download_reconst(RUN_PATH)
rec_voc = vocoder.HiFiGAN(
    os.path.join(RUN_PATH, "models", "hifirec"), "config_v1", DEVICE
)

def generate_audio(
    model_name: str,
    custom_model: Optional[str],
    transcript: str,
    pitch_options: Iterable[str],
    pitch_factor: int,
    wav_name: Optional[str],
):
    global sr_voc, rec_voc
    m = get_model(model_name, custom_model)
    tnmodel,tndurs,tnpitch,voc = (
        m.tnmodel, m.tndurs, m.tnpitch, m.voc
    )
    #
    if wav_name is not None:
        f0s, f0s_wo_silence = analyse_file(wav_name)
    try:
        with torch.no_grad():
            # Generate spectrogram
            token_list, tokens, arpa = extract_dur.get_tokens(transcript)
            if "dra" in pitch_options:
                if tndurs is None or tnpitch is None:
                    return [None,
                        "This model doesn't support pitch prediction (?)",
                        None]
                spect = tnmodel.generate_spectrogram(tokens=tokens)
            else:
                durs = extract_dur.get_duration('../'+wav_name, transcript, token_list)

                # Change pitch
                if "pf" in pitch_options:
                    f0_factor = np.power(np.e, (0.0577623 * float(pitch_factor)))
                    f0s = [x * f0_factor for x in f0s]
                    f0s_wo_silence = [x * f0_factor for x in f0s_wo_silence]

                spect = tnmodel.force_spectrogram(
                    tokens=tokens,
                    durs=torch.from_numpy(durs)
                    .view(1, -1)
                    .type(torch.LongTensor)
                    .to(DEVICE),
                    f0=torch.FloatTensor(f0s).view(1, -1).to(DEVICE),
                )

            # Vocoding
            audio, audio_torch = voc.vocode(spect)

            # Reconstruction
            if "srec" in pitch_options:
                load_error = download_reconst(RUN_PATH)
                if load_error is not None:
                    raise RuntimeError(load_error)
                new_spect = reconstruct_inst.reconstruct(spect)
                audio, audio_torch = rec_voc.vocode(new_spect)

            # Auto-tuning
            if "pc" in pitch_options and "dra" not in pitch_options:
                audio = extract_pitch.auto_tune(audio, audio_torch, f0s_wo_silence)

            # Super-resolution
            sr_mix, new_rate = sr_voc.superres(audio, 22050)

            # Create buffer
            buffer = io.BytesIO()
            wavfile.write(buffer, new_rate, sr_mix.astype(np.int16))
            b64 = base64.b64encode(buffer.getvalue())
            sound = "data:audio/x-wav;base64," + b64.decode("ascii")

            output_name = "TalkNet_" + str(int(time.time()))
            return [sound, arpa, output_name]
    except Exception:
        raise RuntimeError(str(traceback.format_exc()))



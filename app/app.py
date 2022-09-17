from marshmallow import Schema, fields, ValidationError
import os
import ffmpeg
import controllable_talknet as ctn

def wav_path_from_ID(audio_id: str):
    if not audio_id.isalnum():
        raise TypeError('Invalid audio ID provided.')
    res = f'./uploads/{audio_id}.wav'
    if not os.path.exists(res):
        raise FileNotFoundError(f'Audio file for {audio_id=} does not exist.')
    return res

class PitchSchema(Schema):
    pf = fields.Bool(required=True)
    pc = fields.Bool(required=True)
    dra = fields.Bool(required=True)
    srec = fields.Bool(required=True)
    pitch_factor = fields.Int(default=0)

class SubmitSchema(Schema):
    model = fields.Str(required=True)
    pitch_options = fields.Nested(PitchSchema(), required=True)
    transcript = fields.Str(required=True)
    audio_id = fields.Str()

def generate_audio(self):
    pitch_options, model,transcript,audio_id = self['pitch_options'], self['model'], self['transcript'],self['audio_id']
    #
    wav_path = wav_path_from_ID(audio_id) if audio_id else None
    if model is None or model == '':
        raise TypeError("No character selected")
    if transcript is None or transcript.strip() == '':
        raise TypeError("No transcript entered")
    if len(transcript) > 320:
        raise ValueError("Transcript was too long.")
    #
    pitch_checkboxes = set()
    for opt in ['pf', 'pc', 'dra', 'srec']:
        if pitch_options[opt]: pitch_checkboxes.add(opt)
    if wav_path is None and "dra" not in pitch_checkboxes:
        raise TypeError("Reference audio desired but no reference audio given.")

    sound, arpa, _ = ctn.generate_audio(model_name=model, custom_model=None,
                       transcript=transcript,
                       pitch_options=pitch_checkboxes,
                       pitch_factor=pitch_options['pitch_factor'],
                       wav_name=wav_path)
    return sound,arpa


from flask import Flask,render_template,request,current_app

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024*1024*10

@app.route("/")
def index(): # slightly inefficient
    return current_app.send_static_file('index.html')


from hashlib import md5
@app.route("/api/upload_audio", methods=['POST'])
def upload_audio():
    f = request.files['file']
    h = md5(f.read()).hexdigest();
    f.seek(0)
    f.save(f'./uploads/{h}.wav')
    # for later
    ffmpeg.input(f'./uploads/{h}.wav').output(
        f'./uploads/{h}.wav_conv.wav',
        ar="22050",
        ac="1",
        acodec="pcm_s16le",
        map_metadata="-1",
        fflags="+bitexact",
    ).overwrite_output().run(quiet=True)
    return {'audio_id': h}

@app.route("/api/debug_audio/<audio_id>")
def debug_audio(audio_id: str):
    try:
        wav_path = wav_path_from_ID(audio_id)
        return ctn.debug_pitch(wav_path)
    except Exception as e:
        return {'error': str(e)}, 400

@app.route("/api/submit", methods=['POST'])
def submit_handler():
    schema = SubmitSchema()
    if not request.json: # actually this doesn't work
        return {'error': 'json required'}, 400
    try: submission = schema.load(request.json)
    except ValidationError as e:
        return {'error': e.messages}, 400
    try:
        sound,arpa = generate_audio(submission)
        return {'audio': sound, 'msg': arpa}, 200
    except Exception as e:
        return {'error': str(e)}, 400


if __name__ == '__main__':
    app.debug = True;
    app.run(debug=True, threaded=True, host='0.0.0.0', port=8050)

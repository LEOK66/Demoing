from flask import Flask, request, render_template, send_from_directory, jsonify, url_for
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from pydub import AudioSegment
from pydub.effects import normalize
import subprocess


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        uploaded_files = request.files.getlist("file[]")
        file_paths = []
        for file in uploaded_files:
            if file and len(file_paths) < 5:
                original_ext = os.path.splitext(file.filename)[1]
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = secure_filename(f"{timestamp}{original_ext}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                file_paths.append(file_path)

        return jsonify(file_paths)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/edit', methods=['POST'])
def edit_track():
    data = request.get_json()
    print(data)
    filename = data['filename']
    start = int(data['start']) * 1000
    end = int(data['end']) * 1000

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    track = AudioSegment.from_file(file_path)

    edited_track = track[start:end]

    edited_filename = 'edited_' + filename
    edited_file_path = os.path.join(app.config['UPLOAD_FOLDER'], edited_filename)
    edited_track.export(file_path, format="mp3")

    return jsonify({'filename': filename})

def apply_eq_with_ffmpeg(input_file, output_file, eq_settings):

    cmd = [
        'ffmpeg', '-i', input_file,
        '-af', f'equalizer=f=320:t=h:width=200:g={eq_settings["low"]},equalizer=f=1000:t=h:width=200:g={eq_settings["mid"]},equalizer=f=3200:t=h:width=200:g={eq_settings["high"]}',
        output_file
    ]
    subprocess.run(cmd, check=True)

def apply_eq(track, low_gain, mid_gain, high_gain):

    low_freq = 250
    mid_freq = 2000
    high_freq = 6000

    low_part = track.low_pass_filter(low_freq)
    mid_part = track.high_pass_filter(low_freq).low_pass_filter(high_freq)
    high_part = track.high_pass_filter(high_freq)

    low_part = low_part + low_gain
    mid_part = mid_part + mid_gain
    high_part = high_part + high_gain

    combined = low_part.overlay(mid_part).overlay(high_part)

    return normalize(combined)

@app.route('/export', methods=['POST'])
def export_tracks():
    data = request.get_json()
    track_list = data['tracks']
    eq_settings = data['eq']
    reverb_type = data.get('reverb', 'plate')

    combined = AudioSegment.silent(duration=0)
    added_tracks = set()
    for filename in track_list:
        if filename not in added_tracks:
            track_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(track_path):
                track = AudioSegment.from_file(track_path)
                track = apply_eq(track, eq_settings['low'], eq_settings['mid'], eq_settings['high'])
                combined += track
                added_tracks.add(filename)
    progress_info['progress'] = 25

    intermediate_filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'combined_track.mp3')
    combined.export(intermediate_filepath, format='mp3')
    progress_info['progress'] = 50

    compressed_filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'compressed_track.mp3')
    apply_compression(intermediate_filepath, compressed_filepath)
    progress_info['progress'] = 75

    reverb_params = get_reverb_params(reverb_type)
    output_filename = 'processed_track.mp3'
    output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    apply_effects(compressed_filepath, output_filepath, reverb_params)
    progress_info['progress'] = 100
    return jsonify({'downloadUrl': url_for('uploaded_file', filename=output_filename)})

def apply_compression(input_file, output_file):
    cmd = [
        'ffmpeg', '-y', '-i', input_file,
        '-af', 'acompressor=threshold=0.1:ratio=3:attack=50:release=1000',
        output_file
    ]
    subprocess.run(cmd, check=True)

def get_reverb_params(reverb_type):

    if reverb_type == 'hall':
        return 'aecho=0.8:0.9:1000:0.3'
    elif reverb_type == 'room':
        return 'aecho=0.8:0.88:60:0.4'
    elif reverb_type == 'plate':
        return 'aecho=0.6:0.7:40:0.5'
    else:

        return ''


def apply_effects(input_file, output_file, reverb_params):
    cmd = ['ffmpeg', '-y', '-i', input_file]

    if reverb_params:
        cmd += ['-af', reverb_params]

    cmd += [output_file]

    subprocess.run(cmd, check=True)

progress_info = {'progress': 0}

@app.route('/progress')
def get_progress():
    return jsonify(progress_info)

@app.route('/export-uncompressed', methods=['POST'])
def export_uncompressed_tracks():
    data = request.get_json()
    track_list = data['tracks']
    eq_settings = data['eq']

    combined = AudioSegment.silent(duration=0)
    added_tracks = set()
    for filename in track_list:
        if filename not in added_tracks:
            track_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(track_path):
                track = AudioSegment.from_file(track_path)
                track = apply_eq(track, eq_settings['low'], eq_settings['mid'], eq_settings['high'])
                combined += track
                added_tracks.add(filename)

    output_filename = 'uncompressed_track.mp3'
    output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    combined.export(output_filepath, format='mp3')

    return jsonify({'downloadUrl': url_for('uploaded_file', filename=output_filename)})


if __name__ == '__main__':
    app.run(debug=True)

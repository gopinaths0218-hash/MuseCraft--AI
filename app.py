import os, re, json, sqlite3, hashlib, tempfile, subprocess
from difflib import SequenceMatcher
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
import requests

ROOT=Path(__file__).resolve().parent
app=Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH']=25*1024*1024
DB=ROOT/'musecraft.db'
API_KEY=os.getenv('OPENAI_API_KEY','').strip()
CHAT_MODEL=os.getenv('OPENAI_MODEL','gpt-4o-mini')

def db():
    con=sqlite3.connect(DB); con.execute('''CREATE TABLE IF NOT EXISTS outputs(id INTEGER PRIMARY KEY, user_id TEXT, feature TEXT, prompt_hash TEXT, content TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''); return con

def prior(user, feature, limit=8):
    con=db(); rows=con.execute('SELECT content FROM outputs WHERE user_id=? AND feature=? ORDER BY id DESC LIMIT ?', (user,feature,limit)).fetchall(); con.close(); return [x[0] for x in rows]

def save(user, feature, prompt, content):
    con=db(); con.execute('INSERT INTO outputs(user_id,feature,prompt_hash,content) VALUES(?,?,?,?)',(user,feature,hashlib.sha256(prompt.encode()).hexdigest(),content)); con.commit(); con.close()

def ai(messages, temperature=0.95, max_tokens=2800):
    if not API_KEY: raise RuntimeError('Backend is running, but OPENAI_API_KEY is not configured. Add it to the server environment.')
    r=requests.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json'},json={'model':CHAT_MODEL,'messages':messages,'temperature':temperature,'max_tokens':max_tokens},timeout=120)
    if not r.ok: raise RuntimeError('AI provider error: '+r.text[:700])
    return r.json()['choices'][0]['message']['content'].strip()

SYSTEM='You are MuseCraft AI, a creative media co-writer. Produce substantial, detailed, vivid, specific output. Never reuse wording, plot beats, examples, hooks, titles, or structures from the recent-generation archive. Do not give generic short answers. Honor the requested language and format. Make each generation distinctly original.'
@app.get('/')
def home(): return send_from_directory(ROOT/'static','index.html')
@app.get('/api/health')
def health(): return jsonify({'ok':True,'ai_configured':bool(API_KEY),'model':CHAT_MODEL})
@app.post('/api/generate')
def generate():
    d=request.get_json(force=True); feature=str(d.get('feature','content')); prompt=str(d.get('prompt','')).strip(); user=str(d.get('user_id','guest'))[:100]; lang=str(d.get('language','English')); length=str(d.get('length','Detailed')); count=max(1,min(4,int(d.get('count',1))))
    if len(prompt)<2: return jsonify(error='Please enter a clear idea or topic.'),400
    allowed={'story','script','content','game','character'}
    if feature not in allowed: return jsonify(error='Unknown creative feature.'),400
    history=prior(user,feature,8)
    archive='\n\n--- RECENT CONTENT TO AVOID (do not imitate or repeat) ---\n'+'\n---\n'.join(x[:1300] for x in history)
    specs={
      'story':f'Write a complete original story, not an outline. Length: {length}. Include a compelling opening, developed scenes, character motivations, surprising but logical turns, and a satisfying ending. Idea and constraints: {prompt}',
      'script':f'Write a production-ready script, not a summary. Length: {length}. Include scene headings, action, distinct character names, dialogue, pacing, and a memorable ending. Idea: {prompt}',
      'content':f'Create a fresh content package for the requested platform/audience. Length: {length}. Include a strong hook, useful/entertaining main content, and a natural call to action when appropriate. Topic and requirements: {prompt}',
      'game':f'Create the next playable interactive story scene. Include vivid narration, consequence-rich choices, and exactly 3 distinct choices labelled A, B, C. Do not resolve the entire game yet. Current story/player choice: {prompt}',
      'character':f'Create a distinctive character profile and/or reply in character. Include voice, values, quirks, motivations, and believable conversational response. User message / character brief: {prompt}'
    }
    try:
      results=[]
      for i in range(count):
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':f'{specs[feature]}\nLanguage: {lang}\n\n{archive}\n\nVariation number {i+1}: invent a new concept and approach, not a paraphrase.'}]
        out=ai(messages,temperature=1.0,max_tokens=3600 if length in ('Long','Very long') else 2600)
        # Retry if it is nearly identical to recent output; similarity guard complements the model instruction.
        if any(SequenceMatcher(None,out.lower(),old.lower()).ratio()>.78 for old in history[-5:]):
          messages.append({'role':'assistant','content':out}); messages.append({'role':'user','content':'This is too similar to earlier output. Discard it and create a completely different concept, structure, details and wording. Make it substantially longer and richer.'}); out=ai(messages,temperature=1.15,max_tokens=3600)
        results.append(out); save(user,feature,prompt,out); history.append(out)
      return jsonify(results=results,feature=feature)
    except Exception as e: return jsonify(error=str(e)),502

@app.post('/api/dub')
def dub():
    if not API_KEY: return jsonify(error='Set OPENAI_API_KEY on the backend first.'),503
    f=request.files.get('media'); target=request.form.get('language','Tamil'); narration=request.form.get('voice','alloy')
    if not f: return jsonify(error='Choose an audio or video file.'),400
    suffix=Path(f.filename).suffix.lower(); allowed={'.mp3','.wav','.m4a','.webm','.mp4','.mov','.mpeg','.mpga','.ogg','.flac'}
    if suffix not in allowed: return jsonify(error='Unsupported file type. Use MP3, WAV, M4A, MP4, MOV, WEBM or similar media.'),400
    with tempfile.TemporaryDirectory() as td:
      src=Path(td)/('upload'+suffix); f.save(src); audio=src
      if suffix in {'.mp4','.mov','.webm'}:
        dest=Path(td)/'audio.mp3'
        try: subprocess.run(['ffmpeg','-y','-i',str(src),'-vn','-acodec','libmp3lame',str(dest)],capture_output=True,check=True,timeout=90); audio=dest
        except Exception: return jsonify(error='Video audio extraction failed. Install ffmpeg on the server or upload an audio file.'),400
      with open(audio,'rb') as stream:
        tr=requests.post('https://api.openai.com/v1/audio/transcriptions',headers={'Authorization':'Bearer '+API_KEY},data={'model':'whisper-1','response_format':'verbose_json'},files={'file':(audio.name,stream,'audio/mpeg')},timeout=180)
      if not tr.ok: return jsonify(error='Transcription error: '+tr.text[:500]),502
      raw=tr.json(); text=raw.get('text','').strip()
      translated=ai([{'role':'system','content':'Translate the transcript faithfully into the requested language. Preserve meaning, names, tone and speaker intent. Return only translated transcript, no explanation.'},{'role':'user','content':f'Target language: {target}\nTranscript:\n{text}'}],.3,2500)
      # Build a useful downloadable subtitle file with a single transcript cue when detailed timestamps are unavailable.
      srt='1\n00:00:00,000 --> 00:10:00,000\n'+translated+'\n'
      speech=requests.post('https://api.openai.com/v1/audio/speech',headers={'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json'},json={'model':'tts-1','voice':narration,'input':translated},timeout=180)
      audio_url=None
      if speech.ok:
        import base64; audio_url='data:audio/mpeg;base64,'+base64.b64encode(speech.content).decode()
      return jsonify(original=text,translated=translated,srt=srt,audio=audio_url)

@app.errorhandler(413)
def too_big(e): return jsonify(error='File too large. Maximum upload size is 25 MB.'),413
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=False)

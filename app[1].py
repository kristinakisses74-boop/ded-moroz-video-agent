import os, uuid, subprocess
from pathlib import Path
from flask import Flask, request, render_template, send_file, flash
from openai import OpenAI

BASE=Path(__file__).parent
UPLOADS=BASE/"uploads"; OUTPUTS=BASE/"outputs"
UPLOADS.mkdir(exist_ok=True); OUTPUTS.mkdir(exist_ok=True)
app=Flask(__name__); app.secret_key=os.environ.get("FLASK_SECRET","change-me")

def script_for(name, interests, extra):
    c=OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    p=f"""Напиши тёплое поздравление от Деда Мороза для ребёнка {name}.
Он любит: {interests or "игрушки и чудеса"}.
Дополнительно: {extra or "нет"}.
110–140 русских слов, примерно 45–60 секунд. Голос и стиль: добрый, тёплый,
пожилой мужчина, немного сказочный, но естественный. Начни с имени и закончи
«С Новым годом, {name}!». Не упоминай ИИ."""
    r=c.responses.create(model=os.getenv("OPENAI_TEXT_MODEL","gpt-5.6-luna"), input=p)
    return r.output_text.strip()

def voice(text, out):
    c=OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with c.audio.speech.with_streaming_response.create(
        model=os.getenv("OPENAI_TTS_MODEL","gpt-4o-mini-tts"),
        voice=os.getenv("OPENAI_TTS_VOICE","onyx"),
        input=text,
        instructions="Низкий, тёплый, спокойный голос пожилого Деда Мороза, слегка сказочный.",
        response_format="mp3") as r:
        r.stream_to_file(out)

def video(images, audio, out):
    d=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(audio)]))
    per=max(4,d/max(1,len(images)))
    args=["ffmpeg","-y"]; 
    for im in images: args += ["-loop","1","-t",str(per),"-i",str(im)]
    f=[]
    for i in range(len(images)):
        f.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0007,1.10)':d=1:s=1080x1920:fps=30,setsar=1[v{i}]")
    f.append("".join(f"[v{i}]" for i in range(len(images)))+f"concat=n={len(images)}:v=1:a=0,format=yuv420p[v]")
    args += ["-i",str(audio),"-filter_complex",";".join(f),"-map","[v]","-map",f"{len(images)}:a","-c:v","libx264","-crf","23","-preset","veryfast","-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(out)]
    subprocess.run(args,check=True)

@app.route("/",methods=["GET","POST"])
def index():
    if request.method=="POST":
        name=request.form.get("name","").strip()
        interests=request.form.get("interests","").strip()
        extra=request.form.get("extra","").strip()
        photos=request.files.getlist("photos")
        if not name: flash("Введите имя ребёнка."); return render_template("index.html")
        if not photos or not photos[0].filename: flash("Добавьте фото."); return render_template("index.html")
        if not os.getenv("OPENAI_API_KEY"): flash("На сервере не задан OPENAI_API_KEY."); return render_template("index.html")
        job=uuid.uuid4().hex; folder=UPLOADS/job; folder.mkdir()
        imgs=[]
        for i,f in enumerate(photos[:12]):
            p=folder/f"img_{i:02d}{Path(f.filename).suffix.lower() or '.jpg'}"; f.save(p); imgs.append(p)
        try:
            text=script_for(name,interests,extra); audio=folder/"voice.mp3"; voice(text,audio)
            out=OUTPUTS/f"{job}.mp4"; video(imgs,audio,out)
        except Exception:
            app.logger.exception("generation failed"); flash("Не удалось создать видео. Проверьте настройки сервера."); return render_template("index.html")
        return render_template("result.html",script=text,filename=out.name)
    return render_template("index.html")

@app.route("/download/<filename>")
def download(filename):
    p=OUTPUTS/Path(filename).name
    return send_file(p,as_attachment=True,download_name=p.name,mimetype="video/mp4") if p.exists() else ("Не найдено",404)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))

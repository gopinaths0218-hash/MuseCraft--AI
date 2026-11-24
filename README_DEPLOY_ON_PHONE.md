# Publish MuseCraft AI from an Android phone

1. Open https://github.com in Chrome and sign in.
2. Tap +, choose New repository. Name it `musecraft-ai`; choose Private; create it.
3. On the new repository, use Add file > Upload files.
4. Upload the project files and folders from this package (not the ZIP file itself):
   - `app.py`
   - `requirements.txt`
   - `Procfile`
   - `render.yaml`
   - `.gitignore`
   - the `static` folder, including `index.html` and `original-prototype.html`
   Commit the upload.
5. Open https://render.com in Chrome and sign in using GitHub.
6. Choose New > Web Service, connect the `musecraft-ai` repository, and deploy.
   The included `render.yaml` describes the build and start commands.
7. In the Render service's Environment settings, add `OPENAI_API_KEY` as a secret value if you want AI features. Never put this key in GitHub files or share it in chat.
8. After deployment succeeds, Render displays the public `https://...onrender.com` URL. Open that URL in Chrome.

If Android's file picker cannot upload a folder, upload the two files inside `static` by creating a `static` folder in GitHub first (Add file > Create new file, name it `static/index.html`), then upload/paste the file contents. Do not upload the ZIP as a single repository file.

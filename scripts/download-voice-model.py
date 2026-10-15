"""Download the official small English Vosk model once, outside application updates."""
import shutil, tempfile
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
root=Path(__file__).resolve().parent.parent
models=root/'models';models.mkdir(exist_ok=True)
name='vosk-model-small-en-us-0.15'
if (models/name/'am/final.mdl').is_file():
    print('Offline model already installed.')
else:
    with tempfile.TemporaryDirectory(dir=models) as tmp:
        archive=Path(tmp)/'model.zip'
        print('Downloading the 40 MB offline speech model…',flush=True)
        with urlopen('https://alphacephei.com/vosk/models/'+name+'.zip',timeout=60) as response, archive.open('wb') as output:
            shutil.copyfileobj(response,output)
        with ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist())>200*1024**2:raise ValueError('Unexpected model size')
            for item in z.infolist():
                dest=(Path(tmp)/item.filename).resolve()
                if not dest.is_relative_to((Path(tmp)/name).resolve()):raise ValueError('Unsafe model archive')
            z.extractall(tmp)
        if not (Path(tmp)/name/'am/final.mdl').is_file():raise ValueError('Incomplete model download')
        if (models/name).exists():raise ValueError('Incomplete model folder already exists; move it aside and retry.')
        (Path(tmp)/name).replace(models/name)
    print('Offline speech model ready.')

"""Read scanned adverts (PDFs that only contain a picture) with Windows' built-in OCR.

The largest image on each of the first pages is taken out with pypdf/Pillow, turned
upright, made greyscale and resized to what the recognizer handles well, then passed to
Windows.Media.Ocr through Windows PowerShell. Nothing is installed or sent anywhere.
"""
import logging
import os
import re
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger(__name__)
PAGES = 3
MAX_SIDE = 3200       # Windows OCR accepts up to 10000 px; ~3000 px keeps newspaper text legible and fast
MIN_SIDE = 600        # logos and stamps are skipped
GOOD_READING = 25     # words of 4+ letters; below this a page is retried at other angles
MARKER = '=====UGW-PAGE====='

# Image paths arrive as arguments; nothing from the PDF is ever interpreted as code.
OCR_SCRIPT = r'''
param([string[]]$Paths)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] > $null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] > $null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] > $null
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'No OCR language is installed in Windows.' }
foreach ($path in $Paths) {
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $stream.Dispose()
  Write-Output '=====UGW-PAGE====='
  Write-Output ($result.Lines | ForEach-Object { $_.Text })
}
'''


def available():
    return sys.platform == 'win32'


def words(text):
    return len(re.findall(r'[A-Za-z]{4,}', text or ''))


def page_images(content, pages=PAGES):
    """The largest picture on each of the first pages, turned the way the page is displayed."""
    from PIL import Image
    out = []
    for page in PdfReader(BytesIO(content)).pages[:pages]:
        turn = int(page.get('/Rotate', 0) or 0) % 360
        best = None
        for image in page.images:
            try:
                picture = image.image if image.image is not None else Image.open(BytesIO(image.data))
            except Exception:
                continue
            if min(picture.size) < MIN_SIDE: continue
            if best is None or picture.size[0] * picture.size[1] > best.size[0] * best.size[1]: best = picture
        # PDF /Rotate turns the page clockwise for display; Pillow rotates anticlockwise.
        if best is not None: out.append(best.rotate(-turn, expand=True) if turn else best)
    return out


def recognize(images):
    """Text of each image, in order (one string per image); [] when OCR is unavailable or fails."""
    if not images or not available(): return []
    powershell = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    with tempfile.TemporaryDirectory(prefix='ugw-ocr-') as folder:
        paths = []
        for n, picture in enumerate(images):
            picture = picture.convert('L')
            picture.thumbnail((MAX_SIDE, MAX_SIDE))
            path = Path(folder) / f'page{n}.png'
            picture.save(path)
            paths.append(str(path))
        script = Path(folder) / 'ocr.ps1'
        script.write_text(OCR_SCRIPT, encoding='utf-8-sig')
        try:
            result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Paths', *paths],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning('OCR could not run: %s', exc)
            return []
        if result.returncode:
            log.warning('OCR failed: %s', (result.stderr.strip().splitlines() or ['unknown error'])[-1][:200])
            return []
        return [part.strip() for part in (result.stdout or '').split(MARKER)[1:]]


def ocr_pdf(content):
    """Recognize each scanned page. A page that reads poorly is retried at the other angles
    (scanners and PDF makers do not always record rotation) and the best reading is kept."""
    try:
        images = page_images(content)
        texts = recognize(images)
        if len(texts) != len(images): return ''
        for n, (picture, text) in enumerate(zip(images, texts)):
            if words(text) >= GOOD_READING: continue
            retries = recognize([picture.rotate(angle, expand=True) for angle in (90, 270, 180)])
            texts[n] = max([text] + retries, key=words)
        return '\n'.join(texts)
    except Exception:
        log.exception('Reading a scanned advert failed')
        return ''

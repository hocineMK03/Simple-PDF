# Simple PDF

A free, offline, open-source PDF toolkit built with **PySide6** and **PyMuPDF**. No accounts, no uploads — everything runs locally on your machine.

![License](https://img.shields.io/github/license/hocineMK03/Simple-PDF)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Stars](https://img.shields.io/github/stars/hocineMK03/Simple-PDF?style=social)
![Last Commit](https://img.shields.io/github/last-commit/hocineMK03/Simple-PDF)

## Disclaimer

This tool processes files entirely on your local machine, except for the **AI Summarizer**, which sends extracted PDF text to whichever LLM API endpoint you configure. Review that provider's terms before sending sensitive documents through it.

## Features

- **Compress PDF** — shrink file size with Lossless, Recommended, or Maximum presets by downscaling and re-encoding embedded images.
- **Images → PDF** — combine JPG/PNG/BMP/WEBP/TIFF images into a single PDF, with page size and orientation options.
- **PDF → Images** — export PDF pages as PNG or JPEG, packaged into a zip.
- **Watermark** — stamp a text or image watermark across one or more PDFs, tiled or centered, with adjustable opacity and rotation.
- **AI Summarizer** — generate a short, medium, or detailed summary of a PDF using your own OpenAI-compatible LLM API (base URL + API key + model).

All tools support batch processing where it makes sense (multiple files in, one output per file).

---

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt` (PySide6, PyMuPDF, Pillow, pikepdf, pypdf, img2pdf, ...)

### Setup

```bash
python -m venv venv
```

**Windows (PowerShell):**

```powershell
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

```bash
python main.py
```

This opens the app's home screen with a grid of tools. Click an enabled tool card to open it; disabled cards ("Soon") aren't implemented yet.

### AI Summarizer setup

The first time you open **AI Summarizer**, you'll be asked for:

1. **API base URL** — e.g. `https://api.openai.com/v1`, or the URL of any OpenAI-compatible endpoint (local LLM server, OpenRouter, etc.)
2. **API key**
3. **Model** — e.g. `gpt-4o-mini`

Click **Save** to unlock the rest of the tool. These details are stored locally via `QSettings` and reused on future runs.

---

## Output

Converted/processed files are saved next to your source files by default (with a suffix like `_compressed.pdf`, `_watermarked.pdf`), or you can pick a custom destination file/folder before running each tool.

---

## Project Status

This project is under active development.

### Current Features

- ✅ Compress PDF
- ✅ Images → PDF
- ✅ PDF → Images
- ✅ Watermark (text & image)
- ✅ AI Summarizer

### Planned (cards visible on the home screen, not yet wired up)

- 🚧 Merge PDF
- 🚧 Split PDF
- 🚧 Rotate
- 🚧 Protect (password encryption)
- 🚧 PDF → Word
- 🚧 Translate PDF

---

## Roadmap

### Completed

- [x] App shell, routing, and shared dark theme
- [x] Compress PDF
- [x] Images → PDF
- [x] PDF → Images
- [x] Watermark
- [x] AI Summarizer

### In Progress / Planned

- [ ] Merge PDF
- [ ] Split PDF
- [ ] Rotate PDF
- [ ] Protect PDF (password encryption)
- [ ] PDF → Word
- [ ] Translate PDF
- [ ] Packaged desktop builds (Windows installer, etc.)

## License

This project is open source under the MIT License.

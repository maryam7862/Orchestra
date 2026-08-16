# Orchestra — Multimodal Image Generation Studio

Project 3 · a full-stack app that turns a text prompt into a verified,
quality-checked image using **Hugging Face's free-tier Inference
Providers** — no paid API key required.

---

## 1. What this is

You type a prompt. The app:

1. builds an exact, validated request (resolution, aspect ratio, style)
2. sends it to Hugging Face with real network timeouts and retry logic
3. runs it through two safety gates
4. saves the result using memory-safe binary handling
5. verifies the file isn't corrupted by fully decoding every pixel
6. scores it for aesthetic quality and prompt alignment
7. only then shows it to you, with a download button and export packages
   for Unreal Engine 5 / Blender / Polycam

Every step above is real — not a UI animation pretending something
happened. See section 13 ("No Fake Features") for what that means in
practice.

---

## 2. Hugging Face integration & the free tier

- Primary and only image-generation provider: **Hugging Face**, via the
  `huggingface_hub` Python SDK's `InferenceClient.text_to_image()`.
- Default model: `black-forest-labs/FLUX.1-schnell`, a fast, openly
  licensed text-to-image model commonly available through Hugging Face
  Inference Providers. **Hugging Face's supported model/provider catalog
  changes over time** — before relying on this, check
  <https://huggingface.co/docs/inference-providers> and update `HF_MODEL`
  in `.env` if needed.
- The only required credential is `HF_TOKEN`, a **free** Hugging Face
  User Access Token (Settings → Access Tokens → New token, "Read" scope
  is enough).
- Free accounts get a **limited monthly amount of included Inference
  Provider credit** — this is not unlimited generation. When it runs out,
  the app does not silently switch to a paid provider or charge you
  anything. It fails with a clear message:
  *"No Hugging Face token configured"* / a provider error surfaced
  honestly in the UI.
- No OpenAI, Stability AI, or Alibaba Cloud key is required or used for
  generation.

### Why FLUX.1-schnell and not the model matrix from the slides
The original slides reference `gpt-image` (Azure/Foundry), `Stable Image
Core` (Stability AI), and `Wan Text-to-Image v2` (Alibaba Cloud) as a
**model matrix** — those are preserved below as documentation, but none
of them offer a free, no-payment-required API. The working
implementation swaps in Hugging Face to satisfy the "must be free"
requirement, behind the same `generate_image()` abstraction
(`services/image_provider.py`) so any of the matrix providers could be
added later as a second implementation without touching the rest of the
app.

| Provider | Model | Prompt limit | Output |
|---|---|---|---|
| Azure/Foundry | gpt-image series | 4,000 chars | Base64 JSON |
| Stability AI | Stable Image Core | 10,000 chars | RAW bytes / Base64 |
| Alibaba Cloud | Wan Text-to-Image v2 | 1,000 chars | URL or PNG binary |
| **Hugging Face (implemented)** | FLUX.1-schnell | ~2,000 chars (app-enforced) | PIL image object |

---

## 3. What "diffusion" means here (and what we don't claim)

Diffusion models don't read your prompt as literal instructions. The
text is encoded into a high-dimensional semantic representation that
steers a reverse denoising process — the model starts from random noise
and repeatedly refines it toward something that matches that
representation. **This app does not implement that math.** It calls a
hosted model that does, and orchestrates everything around the request:
validation, retries, security, storage, verification, and QA.

---

## 4. Installation (Windows)

**Step 1 — Install Python** (3.10+) from python.org, checking "Add
Python to PATH" during install.

**Step 2 — Open the project folder**
```
cd path\to\project-3-image-generation-studio
```

**Step 3 — Create a virtual environment**
```
python -m venv venv
```

**Step 4 — Activate it**
```
venv\Scripts\activate
```

**Step 5 — Install dependencies**
```
pip install -r requirements.txt
```

**Step 6 — Create your `.env` file**
Copy `.env.example` to `.env` in the project root.

**Step 7 — Paste your token**
Open `.env` and set:
```
HF_TOKEN=your_token_here
```

**Step 8 — Run the app**
```
python app.py
```

**Step 9 — Open your browser**
```
http://127.0.0.1:5000
```

(macOS/Linux: same steps, but activate with `source venv/bin/activate`.)

---

## 5. Aspect ratio → exact resolution mapping

| Ratio | Resolution | Pixel volume | Intended use |
|---|---|---|---|
| 16:9 | 1344 × 768 | 1,032,192 | Web banners / presentations |
| 1:1 | 1024 × 1024 | 1,048,576 | Avatars / product grids |
| 9:16 | 768 × 1344 | 1,032,192 | Mobile reels / wallpapers |

These exact numbers are hard-coded in `config.py` and never overridden by
arbitrary user input — `services/payload_builder.py` maps your aspect
ratio selection to these values before anything is sent to Hugging Face,
because sending unsupported dimensions can cause an immediate API
failure. FLUX.1-schnell accepts arbitrary width/height in multiples of 8,
so all three targets are sent exactly as-is; if you swap in a model with
fixed resolution buckets, set `REQUIRE_DIMENSION_COMPATIBILITY_CHECK =
True` in `config.py` so the app snaps to the nearest supported bucket and
reports the discrepancy instead of silently claiming false dimensions.

---

## 6. Timeout strategy

Python's `requests` library has **no default timeout** — without one, a
hung connection can wait forever. This app always sets:

```python
timeout = (3.05, 60)   # (connection timeout, read timeout)
```

- **3.05 seconds** to connect: just over the common 3-second TCP
  retransmission window, giving one retransmit a chance to land before
  giving up.
- **60 seconds** to read: image generation can queue on a shared/free
  GPU pool, so this is generous on purpose.

Both are centralized in `config.py` (`CONNECTION_TIMEOUT`,
`READ_TIMEOUT`) — nowhere in the codebase makes an HTTP call without
them.

---

## 7. Retry strategy

Only these are retried, with **exponential backoff + random jitter**,
capped at `MAX_RETRY_ATTEMPTS` (default 4):

- Connection timeout
- Read timeout
- HTTP 429 (Too Many Requests)
- HTTP 503 (Service Unavailable)

These are **never** retried (fail fast instead):

- Invalid/missing token (401/403)
- Invalid prompt / unsupported parameter
- Security-gate rejection

**Exponential backoff** means each retry waits roughly twice as long as
the last (0.75s, 1.5s, 3s, ...), capped at 20 seconds. **Jitter** adds a
small random +/- adjustment to that wait so that if many requests fail
at once, they don't all retry at exactly the same moment and hammer the
server simultaneously.

---

## 8. Security gates

**Gate 1 (pre-generation)** — `services/security.py` checks the prompt
before it's ever sent to Hugging Face. A rejected prompt never reaches
the network stage (reported as `sentinel_block`).

**Gate 2 (post-generation)** — inspects the provider's own response for
a moderation signal (the provider equivalent of `content_policy_violation`
or `finish_reason=FILTER`) before the image is allowed to become the
displayed/downloadable asset (reported as `moderation_blocked`).

Both gates fail safely with a plain message — internal provider details
are never exposed to the user.

---

## 9. Binary handling & streaming

`InferenceClient.text_to_image()` returns a **`PIL.Image` object
directly**, already fully decoded in memory by the SDK — not a remote
URL. So for the primary flow, there is no remote HTTP download to stream;
that's stated plainly rather than pretended away. The image is written
to disk directly (`services/downloader.py`).

The **memory-safe streaming path is still implemented and used** for the
case a provider *does* return a remote URL (`services/api_gateway.py`):

```python
with requests.get(url, stream=True, timeout=(3.05, 60)) as response:
    response.raise_for_status()
    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
```

65,536 bytes (64 KiB) per chunk — large images are never pulled fully
into RAM via `response.content`.

---

## 10. Image integrity: why `Image.open()` isn't enough

`Image.open()` only reads the file header. A truncated download can have
a perfectly valid PNG header and still be missing most of its pixel
data — `Image.open()` alone won't catch that.

`Image.load()` forces Pillow to decode every pixel. If the data is
incomplete or corrupted, **this** is where it throws (`OSError`), not at
`open()` time:

```python
with Image.open(path) as image:
    image.load()          # the real check
    width, height = image.width, image.height
```

Verified in `tests/test_integrity.py`: a real PNG truncated to 25% of
its bytes passes `Image.open()` but fails `Image.load()`, and the
pipeline deletes the corrupted file and (if attempts remain) regenerates.

After a successful decode, a SHA-256 checksum is computed (in 64 KiB
chunks, same memory-safety principle) and stored alongside width,
height, format, and byte size — an *additional* integrity record, not a
replacement for the pixel-level decode.

---

## 11. Automated QA — two lenses, and an honest adaptation

The Project 3 slides specify CLIP ViT-L/14 embeddings scored by a linear
classifier (aesthetic, threshold >7.0/10) and PickScore/CLIP-TQA for
semantic alignment. Two real (never random) implementations exist:

**Default mode — local heuristic (no heavy dependencies):**
- *Aesthetic*: a deterministic 0–10 score from real pixel statistics —
  edge/sharpness energy, luminance contrast, and channel colorfulness
  (`services/aesthetic_qa.py`). Same image always produces the same
  score (verified in `tests/test_qa.py`).
- *Semantic*: honestly reported as **not evaluated** rather than faked
  from keyword matching — the pipeline treats this as a pass-through,
  and the UI clearly labels it "Not evaluated (heuristic mode)".

**Optional mode — `ENABLE_CLIP_QA=true` in `.env`:**
- Requires `pip install torch transformers` (commented out in
  `requirements.txt` by default) and a one-time ~600MB CLIP model
  download.
- *Aesthetic*: CLIP image embedding through a lightweight linear head.
  The exact proprietary classifier from the slides has no public
  downloadable weights, so this is a documented stand-in, not a claim of
  matching a specific published model.
- *Semantic*: real CLIP cosine similarity between the image and prompt
  embeddings — the same underlying technique PickScore/CLIP-TQA are
  built on.

Threshold: aesthetic score must exceed **7.0/10** or the image is
rejected and (if attempts remain) regenerated. Semantic threshold is
configurable (`SEMANTIC_THRESHOLD` in `config.py`, default 5.0/10).

---

## 12. Regeneration loop

Up to `MAX_GENERATION_ATTEMPTS` (default 3) full attempts per request.
Each attempt runs: generate → security gate 2 → save → integrity check →
QA. Any rejection at any stage triggers a fresh attempt if one remains;
otherwise the request fails with a specific, honest error code.

---

## 13. No fake features

If the pipeline monitor shows "Success" for a stage, that stage's
backend function actually ran and actually returned success — there is
no cosmetic-only status anywhere in this app. Concretely:

- "Retrying" only appears when `services/retry.py` is genuinely sleeping
  and re-attempting.
- "Integrity Verified" only appears after `Image.load()` has genuinely
  succeeded.
- "QA Passed" only appears after real aesthetic/semantic scoring ran.
- Scores are never `random.random()` — see section 11.

**One honest limitation to know about:** the backend runs the full
pipeline synchronously and returns a complete, real event log in one
HTTP response. The frontend then replays that log with short delays so
the pipeline monitor reads as "live." This is **not** a websocket
streaming the events as they happen — it's a client-side replay of
real, already-completed backend events. That trade-off keeps the app
simple to run with plain Flask; it's called out here rather than
presented as live streaming.

---

## 14. Project structure

```
project-3-image-generation-studio/
├── app.py                      Flask routes
├── config.py                   every timeout/threshold/path/mapping lives here
├── requirements.txt
├── .env / .env.example
├── .gitignore
├── services/
│   ├── image_provider.py       abstract provider interface
│   ├── huggingface_provider.py the only file that talks to Hugging Face
│   ├── api_gateway.py          timeouts, retry classification, streaming
│   ├── payload_builder.py      Stage 1: validation + aspect-ratio mapping
│   ├── retry.py                exponential backoff + jitter
│   ├── security.py             Gate 1 / Gate 2
│   ├── downloader.py           Stage 4: memory-safe save
│   ├── integrity.py            Stage 5: pixel-level decode + checksum
│   ├── aesthetic_qa.py         QA lens 1
│   ├── semantic_qa.py          QA lens 2
│   ├── qa.py                   Stage 6 orchestrator
│   ├── pipeline.py             ties all six stages + regeneration loop together
│   └── history.py              JSON-backed generation history
├── integrations/
│   ├── unreal.py                UE5 texture handoff package
│   ├── blender.py                image + runnable material-setup script
│   └── polycam.py                manual handoff package
├── utils/
│   ├── checksum.py, file_utils.py, logging_utils.py
├── templates/index.html
├── static/css/style.css, static/js/app.js
├── generated_assets/           saved images + history.json (gitignored)
├── exports/                    UE5/Blender/Polycam export packages (gitignored)
├── logs/                       app.log (gitignored)
└── tests/
    ├── test_payload.py, test_retry.py, test_integrity.py,
    ├── test_validation.py, test_qa.py
```

---

## 15. Complete data flow

```
User enters prompt
  → Frontend (fetch POST /api/generate)
  → Flask route
  → payload_builder: validate + map aspect ratio → exact resolution
  → security.pre_generation_check (Gate 1)
  → huggingface_provider.generate(), wrapped in retry.run_with_retry
      (3.05s connect / 60s read timeout, backoff+jitter on 429/503/timeouts)
  → security.post_generation_check (Gate 2)
  → downloader.save_provider_result (memory-safe save)
  → integrity.verify_and_fingerprint (Image.open + Image.load + SHA-256)
  → qa.run_qa (aesthetic + semantic lenses)
  → accept → history.add_entry → JSON response
  → Frontend replays the real event log into the pipeline monitor
  → Image displayed, downloadable, exportable
```

If any stage rejects and attempts remain, the loop in
`services/pipeline.py` starts over from the network stage. If all
attempts are exhausted, a specific error code and message come back —
never a generic crash.

---

## 16. GitHub safety

**Safe to commit:** all source code, `templates/`, `static/`,
`requirements.txt`, `README.md`, `.env.example`, `tests/`.

**Never commit:** `.env` (your real token lives here), anything in
`generated_assets/`, `exports/`, or `logs/` (already covered by
`.gitignore`).

The token is read once in `config.py` from the environment and never
appears in HTML, CSS, JavaScript, or log output (`utils/logging_utils.py`
redacts anything matching `token`/`authorization`/`api_key`/`secret`
before it's written to `app.log`).

---

## 17. Testing

```
pip install pytest
pytest tests/
```

Covers: prompt/negative-prompt/aspect-ratio/count validation, exact
resolution mapping, retry backoff/jitter/selective-retry behavior,
path-traversal protection, corrupted-image detection via `Image.load()`,
and deterministic (non-random) QA scoring.

Manual test scenarios matching the original spec (invalid token,
connection timeout, 429, 503, corrupted image, low aesthetic score) are
exercised by mocking the relevant layer — see the docstrings in each
test file for which one to look at for a given scenario.

---

## 18. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `MISSING_HF_TOKEN` error | `.env` doesn't have `HF_TOKEN` set, or the app wasn't restarted after editing `.env` |
| `AUTH_FAILURE` error | Token is invalid, expired, or lacks Inference Providers access |
| Generation always ends in `HTTP_503` after retries | Free-tier credit likely exhausted, or the model is temporarily unavailable — try again later or check the model status on huggingface.co |
| `MISSING_DEPENDENCY` error | Run `pip install -r requirements.txt` inside the activated venv |
| Aesthetic score always similar | Expected — the default heuristic mode measures real but simple image statistics; set `ENABLE_CLIP_QA=true` for the CLIP-based mode if you want richer scoring |

---

## 19. Required API keys

```
[✓] Hugging Face token — free to create
    Variable: HF_TOKEN
    File:     .env
    Location: project root

[✓] No OpenAI key required
[✓] No Stability AI key required
[✓] No Alibaba Cloud key required
[✓] No paid provider key required
```

Create your token at <https://huggingface.co/settings/tokens> ("Read"
permission is sufficient). Paste it into `.env` as `HF_TOKEN=...`. Never
put it in HTML, CSS, JavaScript, or push `.env` to GitHub.

---

## 20. Project 3 in 15 simple sentences

1. This app turns a written description into a picture.
2. It uses Hugging Face, a free AI hosting service, to actually generate the image.
3. You pick a shape (landscape, square, or vertical) and the app sends the exact right size.
4. Every network request has a time limit so the app never hangs forever.
5. If a request fails for a fixable reason, the app tries again a few times, waiting a bit longer each time.
6. If a request fails for an unfixable reason, like a bad password, it stops immediately instead of wasting time.
7. Before generating, the app checks your prompt isn't asking for something unsafe.
8. After generating, it checks the result isn't flagged as unsafe either.
9. The finished image is saved to disk in small, safe pieces instead of all at once.
10. The app then fully opens the image file to make sure it isn't broken or cut off.
11. It also creates a unique fingerprint (checksum) of the file, like a digital signature.
12. The image is then scored for how good it looks and how well it matches your prompt.
13. If it fails any of those checks, the app quietly tries generating it again, up to three times.
14. Once an image passes everything, you can preview it, download it, and even export it for use in 3D tools like Blender or Unreal Engine.
15. Nothing about this costs money, and nothing about the process is faked — every checkmark you see actually happened.

---

## 21. How to run — quick checklist

1. Install Python 3.10+
2. Open the project folder in a terminal
3. `python -m venv venv`
4. `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux)
5. `pip install -r requirements.txt`
6. Copy `.env.example` → `.env`
7. Paste your free token: `HF_TOKEN=...`
8. `python app.py`
9. Open `http://127.0.0.1:5000`
10. Test an image: type a prompt, pick 16:9, click Generate
11. Test aspect ratios: repeat with 1:1 and 9:16, confirm the resolution shown matches section 5's table
12. Test QA: watch the pipeline monitor reach "Automated QA" and check the aesthetic score shown in the result panel
13. Test download: click the download icon on a successful result
14. Test errors: temporarily clear `HF_TOKEN` from `.env`, restart the app, and confirm you get a clear `MISSING_HF_TOKEN` message instead of a crash
15. Test history: switch to the History tab after a few successful generations

You can visit the site https://orchestra-qrz388cge-maryam-saleem-s-projects.vercel.app/ here

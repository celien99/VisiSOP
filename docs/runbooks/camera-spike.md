# Camera spike (HIKROBOT MV-CH120-20GC, GigE)

Run this once on the demo machine, before tuning any thresholds. It proves the
camera, NIC, and GenTL producer work together and records the numbers the B1
acceptance checklist asks for.

## 1. Install and verify MVS

1. Install the HIKROBOT MVS SDK (with the GigE Vision driver) on Windows.
2. Open **MVS** and confirm the camera appears. If it does not: check PoE or the
   12 V supply, the camera IP subnet vs. the NIC subnet, and Windows Firewall.
3. Find the GenTL producer: usually
   `C:\Program Files\MVS\Runtime\Win64_x64\MvProducerGEV.cti`. Use the path the
   installed SDK actually has; the demo config points at this default.

## 2. Network

- Dedicate a NIC to the camera; no DHCP on that adapter.
- Set the NIC MTU/jumbo frames to **9014** and the camera packet size to
  **8192** (see `packet_size` in the config). Both ends must match.
- Allocate the camera a static IP in the NIC subnet (MVS → camera → network
  settings).

## 3. Configure the spike

Edit `runtime/config.demo.yaml` (or a copy):

```yaml
camera:
  camera_id: cam-01
  role: overview
  source:
    kind: mvs       # HIKROBOT SDK; `gige` uses harvesters over a GenTL producer
    serial: DA9184675  # preferred; `ip` also works; with neither, first GigE camera
    exposure_us: 8000  # the runtime writes exposure and gain only
    gain_db: 0.0
```

`kind: mvs` is the supported path for this camera: the MVS GenTL producer
returns device metadata in a non-UTF-8 codepage that genicam 1.6 cannot decode
on CPython 3.12 (`UnicodeDecodeError` in `Port.url_info_list`). The generic
`kind: gige` source stays for producers that return UTF-8 metadata; it needs
`cti_path`, e.g.
`C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64/MvProducerGEV.cti`
(the path differs from the MVS application install directory).

The MVS source deliberately does not change resolution, pixel format,
triggering, or packet size: set those on the camera in MVS and the runtime
streams whatever the camera produces. For correct colour, select
**RGB8Packed** in MVS so the camera applies its own white balance; the runtime
passes that buffer through as BGR (this producer's packed formats arrive in
the opposite byte order to their names). `BayerRG8` is decoded too, but without
white balance, so warm lighting turns it yellow.

`EVIDENCE_DIR` is required by the config loader even though the spike writes no
evidence:

```bash
cd runtime
export EVIDENCE_DIR=C:/VisiSOP/evidence
uv sync                  # --extra gige only for source.kind: gige
uv run python -m video_runtime.tools.camera_spike \
  --config config.demo.yaml --frames 100 --save-dir spike/
```

## 4. Read the output

- `fps` — sustained capture rate. B1 requires **≥ 10 FPS at 2048×1536 BayerRG8**
  and stability over 60 s (run the spike with `--frames 600` for that).
- `brightness` — mean pixel value of the first frame. `0` means a black frame:
  lens cap, closed iris, or `exposure_us` too low.
- `spike/sample-00.jpg` … `sample-04.jpg` — five unannotated frames. Open them and
  check focus, bottle visibility, and where the pickup/target zones will sit.
- If the spike exits non-zero with `no frames captured`, the producer, serial/IP,
  or pixel format is wrong.

## 5. Record for acceptance

Write these into `docs/runbooks/acceptance-b1.md`:

- MVS version and GenTL `cti_path`
- camera serial and IP
- achieved FPS at 2048×1536 BayerRG8 over 60 s
- exposure/gain that produced a usable image
- the five sample JPEGs (keep them in `runtime/spike/`, not in git)

## 6. Calibrate the zones

With the live preview open (`http://127.0.0.1:8001/stream/cam-01` after starting
the runtime), set `zones[].rect` to the normalized `[x1, y1, x2, y2]` of the
pickup and target areas. A detection counts when its bbox center falls inside
the rectangle.

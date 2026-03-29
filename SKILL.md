---
name: comfyui-generator
description: CLI-based tool for ComfyUI image/video generation. Use comfyui_runner.py for all operations. Requires comfyui-service-manager.
user-invocable: true
metadata: {
  "emoji": "🎨",
  "os": ["darwin", "linux", "win32"],
  "requires": {
    "python": ">=3.8",
    "packages": ["requests", "Pillow"],
    "services": ["comfyui-service-manager"]
  },
  "primaryEnv": "COMFYUI_URL",
  "notes": "Service manager address must be same host as ComfyUI (e.g., 192.168.1.179:9999)"
}
---

# ComfyUI Generator Skill

CLI-based tool for generating images, editing images, and creating videos using ComfyUI workflows with automatic service switching.

**Primary Interface:** `comfyui_runner.py` command-line script
**Requirements:**
- ComfyUI server running
- comfyui-service-manager running (enabled by default)

## Features

- **Command-Line First**: Designed for CLI usage via `comfyui_runner.py`
- **Text-to-Image**: Generate images from text prompts
- **Image Editing**: Edit images with text instructions
- **Image-to-Video**: Create videos from images
- **Add Audio to Video**: Add AI-generated audio to videos using MMAudio
- **Automatic Service Switching**: Automatically switches between `normal` and `no-cache` services
- **Smart LoRA Control**: Automatically enable/disable LoRAs based on prompt keywords
- **Model Presets**: Switch between `default` and `smooth` video models via `--model`

## Quick Start

```bash
# Service manager is enabled by default
python comfyui_runner.py t2i "a beautiful sunset"

# Disable if needed:
python comfyui_runner.py t2i "a beautiful sunset" --disable-service-manager
```

## Configuration

### Required: Service Manager

This skill uses comfyui-service-manager by default. The service manager must be on the **same host** as ComfyUI. Use `--disable-service-manager` to disable.

```python
from comfyui_runner import ComfyUIConfig, ComfyUIRunner

# Required configuration
config = ComfyUIConfig(
    server_address="192.168.1.179:8188",
    service_manager_enabled=True,  # Required
    service_manager_address="192.168.1.179:9999"  # Same host as ComfyUI, port 9999
)

runner = ComfyUIRunner(config)
```

### Environment Variables

- `COMFYUI_URL`: ComfyUI server address (default: `http://192.168.1.179:8188`)
- `SERVICE_MANAGER_URL`: Service manager address - **must be same host as ComfyUI** (default: `192.168.1.179:9999`)

**Important**: The service manager runs on the same server as ComfyUI, using port 9999 for HTTP API control.

## Usage

**Primary Usage: Command-Line Interface**

This skill is designed to be used primarily via the `comfyui_runner.py` command-line script. The Python API is also available for advanced users.

### Text-to-Image Generation

Generate images from text descriptions.

```python
from comfyui_runner import ComfyUIRunner

config = ComfyUIConfig(
    server_address="192.168.1.179:8188",
    service_manager_enabled=True,
    service_manager_address="192.168.1.179:9999"
)
runner = ComfyUIRunner(config)

images = runner.generate_image(
    prompt="a beautiful sunset over mountains, golden hour lighting",
    negative_prompt="low quality, blurry, distorted",
    width=928,
    height=1664,
    output_dir="./outputs"
)

print(f"Generated {len(images)} images")
```

**CLI:**
```bash
python comfyui_runner.py t2i "a beautiful sunset over mountains" \
  --negative "low quality, blurry" \
  --width 928 --height 1664 \
  --service-manager 192.168.1.179:9999
```

### Image Editing

Edit existing images with text instructions.

```python
edited = runner.edit_image(
    image_path="input.jpg",
    edit_prompt="make the sky more dramatic with colorful clouds",
    negative_prompt="low quality",
    output_dir="./outputs"
)
```

**CLI:**
```bash
python comfyui_runner.py edit input.jpg "make the sky blue"
```

### Image-to-Video Generation

Create videos from images with motion prompts.

```python
videos = runner.generate_video(
    image_path="input.jpg",
    prompt="camera slowly pans across the landscape from left to right",
    width=480,
    height=832,
    length=81,  # Number of frames
    output_dir="./outputs"
)
```

**CLI:**
```bash
python comfyui_runner.py i2v input.jpg "camera pans across the landscape"
```

**Smart LoRA Control** (Automatic):

The video generation automatically detects keywords in your prompt and enables relevant LoRAs:

```python
# Built-in keyword mappings (can be customized in comfyui_runner.py)
LORA_KEYWORD_MAPPING = {
    "Instagirl": ["portrait", "selfie", "girl", "woman", "face"],
    "r3v3rs3_c0wg1rl": ["cowgirl", "riding", "sex"],
    "Lenovo": ["phone", "mobile", "smartphone"],
    "cyberpunk": ["cyberpunk", "neon", "futuristic"],
    # ... add more mappings
}
```

Example prompts:
- `"A woman in cowgirl position"` → Enables Instagirl + r3v3rs3_c0wg1rl LoRAs
- `"A portrait with phone"` → Enables Instagirl + Lenovo LoRAs
- `"A cyberpunk city"` → Enables cyberpunk LoRA

To disable automatic LoRA detection (use workflow defaults):
```python
videos = runner.generate_video(
    image_path="input.jpg",
    prompt="your prompt",
    lora_keywords=False  # Disable auto-detection
)
```

## Automatic Service Switching

The skill automatically selects the optimal service by default:

| Operation | Target Service | Reason |
|-----------|---------------|--------|
| Text-to-Image | `normal` | Uses cache for faster generation |
| Image Editing | `normal` | Uses cache for faster generation |
| Image-to-Video | `no-cache` | Saves memory, prevents OOM |
| Add Audio to Video | `normal` | Uses cache for faster generation |

**Service manager is enabled by default** for optimal performance and memory usage.

### Video Model Presets (--model)

| Preset | Model Files | Best For |
|--------|------------|---------|
| `default` | Wan2.2-I2V-A14B (High/Low Noise) | General purpose, realistic style |
| `smooth` | smoothMixWan22I2VV20 (High/Low) | **Fantasy race content** (elves, orcs, demons, dragon-kin and other non-human characters) |

**Tip**: Use `--model smooth` when generating videos involving fantasy races (elf, orc, demon, dragon-kin, etc.) for better results.

```bash
# Fantasy race content -> use smooth model
python comfyui_runner.py i2v input.jpg "an elf princess walking" --model smooth

# General content -> use default model
python comfyui_runner.py i2v input.jpg "a woman walking" --model default
```

Manual service override:
```bash
python comfyui_runner.py i2v input.jpg "camera pans" \
  --disable-service-manager
```

## Parameters

### Text-to-Image Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | **Required** | Positive text prompt |
| `negative_prompt` | str | "低分辨率，低画质..." | Negative prompt |
| `width` | int | 928 | Image width |
| `height` | int | 1664 | Image height |
| `steps` | int | 4 | Sampling steps |
| `cfg` | float | 1.0 | CFG scale |
| `seed` | int | Random | Random seed |

### Image Edit Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_path` | str | **Required** | Input image path |
| `edit_prompt` | str | **Required** | Edit instruction |
| `negative_prompt` | str | "" | Negative prompt |
| `steps` | int | 4 | Sampling steps |
| `cfg` | float | 1.0 | CFG scale |
| `seed` | int | Random | Random seed |

### Image-to-Video Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_path` | str | **Required** | Input image path |
| `prompt` | str | **Required** | Motion description |
| `negative_prompt` | str | "色调艳丽，过曝..." | Negative prompt |
| `width` | int | 480 | Video width |
| `height` | int | 832 | Video height |
| `length` | int | 81 | Number of frames |
| `fps` | int | 16 | Frames per second |
| `steps` | int | 4 | Sampling steps |
| `cfg` | float | 1.0 | CFG scale |
| `seed` | int | Random | Random seed |
| `lora_keywords` | bool | True | Enable automatic LoRA keyword detection |
| `lora_mapping` | dict | {} | Custom keyword mapping (overrides default) |
| `model` | str | "default" | Model preset: `"default"` or `"smooth"` |

### Add Audio to Video Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `video_path` | str | **Required** | Input video path |
| `prompt` | str | "" | Audio description prompt |
| `negative_prompt` | str | "" | Negative prompt |
| `steps` | int | 100 | Sampling steps |
| `cfg` | float | 6.0 | CFG scale |
| `source_fps` | int | 16 | Source video FPS |
| `target_fps` | int | 25 | Target output FPS |
| `filename_prefix` | str | "MMAudio" | Output filename prefix |
| `seed` | int | Random | Random seed |

## CLI Reference

```bash
python comfyui_runner.py <command> <input> [prompt] [options]

Commands:
  t2i         Text-to-image generation
  edit        Image editing
  i2v         Image-to-video generation
  audio       Add AI-generated audio to video

Arguments:
  input       For t2i: prompt text
              For edit/i2v: input image path
              For audio: input video path
  prompt      For edit/i2v: prompt text
              For audio: audio description (optional)

Flags:
  --disable-service-manager  Disable service manager (enabled by default)

Optional Options:
  --server ADDRESS       ComfyUI server address (default: 192.168.1.179:8188)
  --service-manager ADDR Service manager address (default: 192.168.1.179:9999)
  --output DIR           Output directory (default: ./outputs)
  --seed INT             Random seed
  --width INT            Width
  --height INT           Height
  --negative TEXT        Negative prompt
  --service NAME         Force specific service (overrides auto-switch)
```

## Examples

### Example 1: Generate Portrait

```python
config = ComfyUIConfig(
    server_address="192.168.1.179:8188",
    service_manager_enabled=True,
    service_manager_address="192.168.1.179:9999"
)
runner = ComfyUIRunner(config)

images = runner.generate_image(
    prompt="beautiful young woman with long flowing hair, "
           "soft natural lighting, professional portrait photography",
    negative_prompt="ugly, deformed, blurry, bad anatomy",
    width=768,
    height=1024
)
```

### Example 2: Edit Photo

```python
# Change sky color
edited = runner.edit_image(
    image_path="landscape.jpg",
    edit_prompt="replace the sky with a vibrant orange sunset",
    negative_prompt="low quality resolution"
)
```

### Example 3: Create Cinematic Video

```python
# Slow motion video from photo
videos = runner.generate_video(
    image_path="portrait.jpg",
    prompt="slow camera push-in towards the subject, "
           "subtle parallax effect on background",
    length=121  # ~7.5 seconds at 16fps
)
```

## Output

Generated files are saved with timestamps and seeds:

```
outputs/
├── t2i_20260325_212058_seed29459_Qwen-Image-2512_00001_.png
├── edit_20260325_213015_seed12345_Qwen-Image-2512_00002_.png
└── i2v_20260325_213530_seed67890_Wan2.2_i2v_00035_.mp4
```

## Error Handling

The skill handles common errors automatically:

- **Connection Error**: Checks if ComfyUI and service manager are running
- **Validation Error**: Provides details about invalid parameters
- **Timeout**: Configurable timeout for long generations (video)
- **Download Error**: Retries file downloads

## Tips

1. **Service manager is enabled by default**: No flag needed, Use `--disable-service-manager` to disable
2. **For high quality images**: Use higher resolution (1024x1024 or above)
3. **For video**: Start with good quality input images
4. **Negative prompts**: Use descriptive negative prompts for better results
5. **Batch operations**: Reuse runner instance for multiple generations
6. **LoRA keywords**: Add custom keyword mappings in `LORA_KEYWORD_MAPPING` (top of comfyui_runner.py)

### Example 4: Add Audio to Video

```python
# Add AI-generated audio to video
outputs = runner.add_audio(
    video_path="input_video.mp4",
    prompt="ambient music with gentle piano",
    source_fps=16,
    target_fps=25,
    output_dir="./outputs"
)
```

**CLI:**
```bash
python comfyui_runner.py audio input.mp4 "ambient music with gentle piano"
```

## Troubleshooting

### Service manager not responding
- Check service manager is running: `curl http://192.168.1.179:9999/status`
- Restart service: `sudo systemctl restart comfyui-service-manager`

### Generation fails with 400 error
- Check prompt doesn't contain invalid characters
- Verify workflow JSON is valid

### Video generation OOM
- Service manager auto-switches to `no-cache` by default to save memory
- Or use smaller resolution (480x832)

## Workflow Files

Workflows are located in the `workflows/` directory:
- `image_workflow.json` - Text-to-image nodes
- `edit_workflow.json` - Image editing nodes
- `video_workflow.json` - Image-to-video nodes (with EasyLoraStack support)
- `audio_workflow.json` - Audio generation nodes (MMAudio)

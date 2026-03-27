# ComfyUI Generator Skill

Generate images, edit images, and create videos using ComfyUI workflows.

## Installation

```bash
# Extract tarball
tar -xzf comfyui-generator.tar.gz
cd comfyui-generator

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### CLI Usage

```bash
# Text to Image
python comfyui_runner.py t2i "a beautiful sunset" --output ./outputs

# Image Edit
python comfyui_runner.py edit input.jpg "make the sky blue"

# Image to Video
python comfyui_runner.py i2v input.jpg "camera pans across the landscape"
```

### Python API

```python
from comfyui_runner import ComfyUIRunner

runner = ComfyUIRunner()

# Generate image
images = runner.generate_image("a beautiful sunset")

# Edit image
edited = runner.edit_image("input.jpg", "make the sky blue")

# Generate video
videos = runner.generate_video("input.jpg", "camera pans")
```

## Configuration

Default ComfyUI server: `192.168.1.179:8188`

To change server:

```python
from comfyui_runner import ComfyUIConfig, ComfyUIRunner

config = ComfyUIConfig(server_address="your-server:8188")
runner = ComfyUIRunner(config)
```

Or via CLI:

```bash
python comfyui_runner.py t2i "prompt" --server your-server:8188
```

## Features

- **Text-to-Image**: Generate images from text prompts
- **Image Editing**: Edit images with text instructions
- **Image-to-Video**: Create videos from images
- **Automatic Service Switching**: Optimize resource usage

## Requirements

- Python 3.8+
- ComfyUI server running
- See `requirements.txt` for dependencies

import argparse
import os
from pathlib import Path

# Resolve assets from the project and Tacotron2 checkout, independent of cwd.
project_dir = Path(__file__).resolve().parents[1]
tacotron2_dir = (
    project_dir
    / "DeepLearningExamples"
    / "PyTorch"
    / "SpeechSynthesis"
    / "Tacotron2"
)


def project_path(env_name: str) -> str:
    """Resolve a required asset path from the environment."""
    value = os.getenv(env_name)
    if not value:
        raise RuntimeError(f"Required environment variable {env_name} is not set")
    path = Path(value)
    if not path.is_absolute():
        path = project_dir / path
    return str(path)


# # Set Inference Arguments

parser = argparse.ArgumentParser(prog = 'ProgramName', description = 'What the program does',epilog = 'Text at the bottom of help')
args = parser.parse_args()
args.tacotron2 = project_path("TACOTRON2_CHECKPOINT")
args.vocoder='univnet'
# args.vocoder='WaveGlow'
# args.waveglow=f"""models/checkpoint_WaveGlow_700.pt"""
args.wn_channels=256
args.univnet = project_path("UNIVNET_CHECKPOINT")
args.univnet_config=str(tacotron2_dir / "univnet" / "config" / "config_bs24.yaml")
args.upload_to_s3=False
args.fp16=False
args.cpu=True
args.include_warmup=False
args.use_ground_truth_mels=False
args.log_file=None
args.output_audio_vector=True

# Set Audio Parameters for Tacotron2

args.sampling_rate=22050
args.stft_hop_length=256
args.max_wav_value=32768.0
args.filter_length=1024
args.hop_length=256
args.win_length=1024
args.mel_fmin=0
args.mel_fmax=8000

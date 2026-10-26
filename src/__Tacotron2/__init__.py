"""Expose the checked-out Tacotron2 folder under the fork's expected alias."""

from pathlib import Path

__path__ = [
    str(
        Path(__file__).resolve().parents[2]
        / "DeepLearningExamples"
        / "PyTorch"
        / "SpeechSynthesis"
        / "Tacotron2"
    )
]

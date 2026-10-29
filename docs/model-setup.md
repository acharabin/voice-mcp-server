# Model setup

This guide covers the speech models used by the Voice AI server. The model checkpoints are not included in the repository and must be downloaded separately.

## Models and checkpoints

Speech generation uses two models in sequence:

1. [Tacotron 2](https://arxiv.org/pdf/1712.05884) converts text into a mel spectrogram, a time-frequency representation of audio.
2. [UnivNet](https://arxiv.org/abs/2106.07889) synthesizes audio from that mel spectrogram.

The AC voice Tacotron 2 and UnivNet checkpoints are available in this [Google Drive folder](https://drive.google.com/drive/folders/1Mp3I33caVRm7YkGYd5z3TXNdgIUF10U-). Place them at these paths from the project root:

```text
models/checkpoint_Tacotron2_1000.pt
models/univ_c32_AC_2141.pt
```

The environment configuration expects those exact paths:

```dotenv
TACOTRON2_CHECKPOINT=models/checkpoint_Tacotron2_1000.pt
UNIVNET_CHECKPOINT=models/univ_c32_AC_2141.pt
```

Details on training are in the forked [NVIDIA Tacotron 2 repository](https://github.com/acharabin/DeepLearningExamples). The Ubuntu installation guide covers fetching the Tacotron 2 source, installing inference dependencies, and running the server.

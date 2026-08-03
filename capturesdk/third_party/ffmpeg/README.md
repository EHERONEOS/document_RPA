# FFmpeg Runtime Layout

CaptureSDK V1 distributes FFmpeg with the SDK ZIP. A system-wide FFmpeg installation is not required.

Expected runtime layout:

```text
third_party/
└── ffmpeg/
    └── bin/
        ├── ffmpeg.exe
        ├── avcodec-*.dll
        ├── avformat-*.dll
        ├── avutil-*.dll
        ├── swscale-*.dll
        └── swresample-*.dll
```

The Phase 5 command `capturesdk diagnose-ffmpeg` searches this layout. FFmpeg DLL names and their licenses must be included in the final release package.

Current status: runtime discovery, encoder policy, H264 encoder interface, output temporary-file lifecycle, and error handling are implemented. Actual GPU-frame-to-FFmpeg libavcodec bridging is intentionally deferred until `Frame` owns or references the captured D3D11 texture. Without that bridge, a valid MP4 video must not be claimed or emitted.

export interface RecordedAudio {
  blob: Blob;
  file_name: string;
}

const SUPPORTED_AUDIO_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

function preferredAudioMimeType(): string | undefined {
  return SUPPORTED_AUDIO_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

/** 최종 UI와 무관하게 브라우저 마이크 답변을 녹음하는 모듈입니다. */
export class BrowserAnswerRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  get isRecording(): boolean {
    return this.recorder?.state === "recording";
  }

  start(stream: MediaStream, timesliceMs = 250): void {
    if (this.recorder && this.recorder.state !== "inactive") {
      throw new Error("이미 음성 녹음이 진행 중입니다.");
    }

    const audioStream = new MediaStream(stream.getAudioTracks());
    if (!audioStream.getAudioTracks().length) {
      throw new Error("사용 가능한 마이크가 없습니다.");
    }

    const mimeType = preferredAudioMimeType();
    this.recorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined);
    this.chunks = [];
    this.recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    });
    this.recorder.start(timesliceMs);
  }

  stop(): Promise<RecordedAudio> {
    return new Promise((resolve, reject) => {
      const recorder = this.recorder;
      if (!recorder || recorder.state === "inactive") {
        reject(new Error("진행 중인 음성 녹음이 없습니다."));
        return;
      }

      recorder.addEventListener(
        "stop",
        () => {
          const mimeType = recorder.mimeType || "audio/webm";
          const extension = mimeType.includes("mp4") ? "m4a" : "webm";
          const blob = new Blob(this.chunks, { type: mimeType });
          this.recorder = null;
          this.chunks = [];
          resolve({ blob, file_name: `answer.${extension}` });
        },
        { once: true },
      );
      recorder.addEventListener(
        "error",
        () => {
          this.recorder = null;
          this.chunks = [];
          reject(new Error("음성 녹음에 실패했습니다."));
        },
        { once: true },
      );
      recorder.stop();
    });
  }

  cancel(): void {
    if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
    this.recorder = null;
    this.chunks = [];
  }
}

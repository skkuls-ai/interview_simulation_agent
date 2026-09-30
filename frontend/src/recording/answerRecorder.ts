export const ANSWER_AUDIO_MIME_TYPE = "audio/webm;codecs=opus";

export interface RecordedAudio {
  blob: Blob;
  file_name: "answer.webm";
}

export type RecordingStopReason = "completed" | "time_limit" | "microphone_disconnected" | "cancelled";

export interface RecordingResult {
  audio: RecordedAudio | null;
  reason: RecordingStopReason;
}

/** 답변을 webm/opus로 녹음하고 장치 중단 전까지의 조각을 보존합니다. */
export class BrowserAnswerRecorder {
  private recorder: MediaRecorder | null = null;
  private audioTrack: MediaStreamTrack | null = null;
  private chunks: Blob[] = [];
  private stopReason: RecordingStopReason = "completed";
  private completion: Promise<RecordingResult> | null = null;
  private resolveCompletion: ((result: RecordingResult) => void) | null = null;
  private rejectCompletion: ((error: Error) => void) | null = null;

  get isRecording(): boolean {
    return this.recorder?.state === "recording";
  }

  start(stream: MediaStream, timesliceMs = 1_000): Promise<RecordingResult> {
    if (this.recorder && this.recorder.state !== "inactive") {
      throw new Error("이미 음성 녹음이 진행 중입니다.");
    }
    if (!MediaRecorder.isTypeSupported(ANSWER_AUDIO_MIME_TYPE)) {
      throw new Error("이 브라우저는 webm/opus 녹음을 지원하지 않습니다.");
    }
    const track = stream.getAudioTracks()[0];
    if (!track || track.readyState === "ended") throw new Error("사용 가능한 마이크가 없습니다.");

    this.chunks = [];
    this.stopReason = "completed";
    this.audioTrack = track;
    this.audioTrack.addEventListener("ended", this.handleTrackEnded);
    this.recorder = new MediaRecorder(new MediaStream([track]), { mimeType: ANSWER_AUDIO_MIME_TYPE });
    this.completion = new Promise<RecordingResult>((resolve, reject) => {
      this.resolveCompletion = resolve;
      this.rejectCompletion = reject;
    });
    this.recorder.addEventListener("dataavailable", this.handleDataAvailable);
    this.recorder.addEventListener("stop", this.handleStop, { once: true });
    this.recorder.addEventListener("error", this.handleError, { once: true });
    this.recorder.start(timesliceMs);
    return this.completion;
  }

  stop(reason: "completed" | "time_limit" = "completed"): Promise<RecordingResult> {
    if (!this.completion) return Promise.reject(new Error("진행 중인 음성 녹음이 없습니다."));
    if (this.recorder?.state !== "inactive") {
      this.stopReason = reason;
      this.recorder?.stop();
    }
    return this.completion;
  }

  cancel(): void {
    if (this.recorder?.state !== "inactive") {
      this.stopReason = "cancelled";
      this.recorder?.stop();
      return;
    }
    this.releaseResources();
  }

  private readonly handleDataAvailable = (event: BlobEvent): void => {
    if (event.data.size > 0) this.chunks.push(event.data);
  };

  private readonly handleTrackEnded = (): void => {
    if (this.recorder?.state === "recording") {
      this.stopReason = "microphone_disconnected";
      this.recorder.stop();
    }
  };

  private readonly handleStop = (): void => {
    const blob = new Blob(this.chunks, { type: ANSWER_AUDIO_MIME_TYPE });
    this.resolveCompletion?.({
      audio: blob.size > 0 && this.stopReason !== "cancelled" ? { blob, file_name: "answer.webm" } : null,
      reason: this.stopReason,
    });
    this.releaseResources();
  };

  private readonly handleError = (): void => {
    this.rejectCompletion?.(new Error("음성 녹음에 실패했습니다."));
    this.releaseResources();
  };

  private releaseResources(): void {
    this.audioTrack?.removeEventListener("ended", this.handleTrackEnded);
    this.recorder?.removeEventListener("dataavailable", this.handleDataAvailable);
    this.audioTrack = null;
    this.recorder = null;
    this.chunks = [];
    this.resolveCompletion = null;
    this.rejectCompletion = null;
  }
}

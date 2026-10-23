// 從語音頻道分別接收每個人的聲音，停頓後切成一段送給 Python
import { EndBehaviorType } from '@discordjs/voice';
import OpusScript from 'opusscript';

const SILENCE_MS = 1000; // 停頓多久算一句話結束
const MAX_SECONDS = 15; // 一直講的話，最多每 15 秒切一段
const MIN_SECONDS = 0.4; // 太短的聲音（咳嗽、按鍵）直接略過

const SAMPLE_RATE = 48000;
const CHANNELS = 2;
const BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * 2;

// Discord 給的是 48kHz 雙聲道，Whisper 要 16kHz 單聲道：兩聲道平均、每 3 個取樣平均成 1 個
export function toMono16k(pcm) {
  const frames = Math.floor(pcm.length / 4 / 3);
  const out = Buffer.alloc(frames * 2);
  for (let i = 0; i < frames; i++) {
    let sum = 0;
    for (let k = 0; k < 3; k++) {
      const offset = (i * 3 + k) * 4;
      sum += pcm.readInt16LE(offset) + pcm.readInt16LE(offset + 2);
    }
    out.writeInt16LE(Math.round(sum / 6), i * 2);
  }
  return out;
}

export class Recorder {
  #listening = new Set();
  #onSpeaking = (userId) => this.#listen(userId);

  /**
   * @param {import('@discordjs/voice').VoiceConnection} connection
   * @param {(userId: string, pcm: Buffer) => void} onSegment 收到 16kHz 單聲道音訊時呼叫
   */
  constructor(connection, onSegment) {
    this.connection = connection;
    this.onSegment = onSegment;
  }

  start() {
    this.connection.receiver.speaking.on('start', this.#onSpeaking);
  }

  stop() {
    this.connection.receiver.speaking.off('start', this.#onSpeaking);
    for (const stream of this.connection.receiver.subscriptions.values()) stream.destroy();
    this.#listening.clear();
  }

  #listen(userId) {
    if (this.#listening.has(userId)) return;
    this.#listening.add(userId);

    const stream = this.connection.receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.AfterSilence, duration: SILENCE_MS },
    });
    const decoder = new OpusScript(SAMPLE_RATE, CHANNELS, OpusScript.Application.AUDIO);
    let chunks = [];
    let bytes = 0;

    const flush = () => {
      if (bytes >= MIN_SECONDS * BYTES_PER_SECOND) {
        this.onSegment(userId, toMono16k(Buffer.concat(chunks)));
      }
      chunks = [];
      bytes = 0;
    };

    stream.on('data', (packet) => {
      let pcm;
      try {
        pcm = Buffer.from(decoder.decode(packet));
      } catch {
        return; // 加密金鑰切換時偶爾會有壞掉的封包，略過就好
      }
      chunks.push(pcm);
      bytes += pcm.length;
      if (bytes >= MAX_SECONDS * BYTES_PER_SECOND) flush();
    });

    const finish = () => {
      if (!this.#listening.delete(userId)) return;
      flush();
      decoder.delete();
    };
    stream.once('end', finish);
    stream.once('close', finish);
    stream.once('error', (err) => {
      console.warn(`收音錯誤（${userId}）：${err.message}`);
      finish();
    });
  }
}

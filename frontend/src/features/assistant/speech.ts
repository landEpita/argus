/**
 * Voice through the browser: dictation (Web Speech recognition) and reading
 * answers aloud (speech synthesis). Nothing goes through Argus' server; note
 * that some browsers (Chrome) send dictated audio to their vendor's service.
 */

interface RecognitionResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}

export interface Recognizer {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: RecognitionResultEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type RecognizerCtor = new () => Recognizer;

interface SpeechWindow {
  SpeechRecognition?: RecognizerCtor;
  webkitSpeechRecognition?: RecognizerCtor;
  speechSynthesis?: SpeechSynthesis;
}

export function recognizerCtor(w: SpeechWindow | undefined): RecognizerCtor | null {
  return w?.SpeechRecognition ?? w?.webkitSpeechRecognition ?? null;
}

export function canSpeak(w: SpeechWindow | undefined): boolean {
  return Boolean(w?.speechSynthesis);
}

/** The words heard so far, final and interim, as one line. */
export function transcriptOf(e: RecognitionResultEvent): string {
  let text = "";
  for (let i = 0; i < e.results.length; i++) {
    const alternative = e.results[i]?.[0];
    if (alternative) text += alternative.transcript;
  }
  return text.trim();
}

/** Text fit for reading aloud: units spelled so they are not read as letters. */
export function speakable(text: string): string {
  return text.replaceAll("%", " percent").replaceAll("−", "minus ").replace(/\s+/g, " ").trim();
}

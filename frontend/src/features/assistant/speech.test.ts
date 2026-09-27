import { describe, expect, it } from "vitest";
import { canSpeak, recognizerCtor, speakable, transcriptOf } from "./speech";

describe("voice", () => {
  it("finds the recognizer under either name", () => {
    class R {}
    expect(recognizerCtor({ webkitSpeechRecognition: R as never })).toBe(R);
    expect(recognizerCtor({})).toBeNull();
    expect(recognizerCtor(undefined)).toBeNull();
    expect(canSpeak({ speechSynthesis: {} as SpeechSynthesis })).toBe(true);
    expect(canSpeak({})).toBe(false);
  });

  it("joins final and interim results", () => {
    const results = [
      Object.assign([{ transcript: "What is happening " }], { isFinal: true }),
      Object.assign([{ transcript: "in the Red Sea" }], { isFinal: false }),
    ];
    expect(transcriptOf({ results })).toBe("What is happening in the Red Sea");
  });

  it("spells units for reading aloud", () => {
    expect(speakable("Brent −8.59 % at  97.44")).toBe("Brent minus 8.59 percent at 97.44");
  });
});

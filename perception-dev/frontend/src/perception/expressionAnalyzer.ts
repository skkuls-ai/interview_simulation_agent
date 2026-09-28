export type BlendshapeScores = Record<string, number>;

export interface ExpressionFrame {
  tracked_scores: BlendshapeScores;
}

export interface ExpressionAnalyzer {
  analyze(blendshapes: BlendshapeScores): ExpressionFrame;
}

export const TRACKED_BLENDSHAPES = [
  "mouthSmileLeft",
  "mouthSmileRight",
  "browInnerUp",
  "browDownLeft",
  "browDownRight",
] as const;

export class BlendshapeExpressionAnalyzer implements ExpressionAnalyzer {
  analyze(blendshapes: BlendshapeScores): ExpressionFrame {
    return {
      tracked_scores: Object.fromEntries(
        TRACKED_BLENDSHAPES.map((name) => [name, blendshapes[name] ?? 0]),
      ),
    };
  }
}

const STOP_WORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "for",
  "from", "had", "has", "have", "he", "her", "his", "in", "is", "it", "its", "of",
  "on", "or", "she", "that", "the", "their", "them", "they", "this", "those", "to",
  "was", "were", "which", "who", "with",
]);

function stem(word) {
  if (word.length > 5 && word.endsWith("ies")) return `${word.slice(0, -3)}y`;
  if (word.length > 5 && word.endsWith("ing")) return word.slice(0, -3);
  if (word.length > 4 && word.endsWith("ed")) return word.slice(0, -2);
  if (word.length > 4 && word.endsWith("es")) return word.slice(0, -2);
  if (word.length > 4 && word.endsWith("s") && !word.endsWith("ss")) return word.slice(0, -1);
  return word;
}

export function terms(text) {
  return [...String(text ?? "").toLowerCase().matchAll(/[a-z0-9]+/g)]
    .map((match) => match[0])
    .filter((word) => word.length > 1 && !STOP_WORDS.has(word))
    .map(stem);
}

function unique(values) {
  return [...new Set(values)];
}

function splitSentences(text) {
  return String(text ?? "")
    .trim()
    .split(/(?<=[.!?])\s+|\n+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

export function splitClaims(text) {
  return splitSentences(text)
    .flatMap((sentence) => sentence.split(/\s*;\s*/))
    .map((claim) => claim.trim())
    .filter((claim) => claim.length >= 8);
}

function normalizedNumbers(text) {
  return [...String(text ?? "").matchAll(/\b(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\b/g)]
    .map((match) => match[0].replaceAll(",", ""));
}

function years(text) {
  return [...String(text ?? "").matchAll(/\b(?:1[0-9]{3}|20[0-9]{2}|2100)\b/g)]
    .map((match) => match[0]);
}

function capitalizedEntities(text) {
  const matches = [...String(text ?? "").matchAll(/\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b/g)]
    .map((match) => match[0])
    .filter((entity) => !["The", "This", "That", "It", "A", "An"].includes(entity));
  return unique(matches);
}

function bigrams(tokens) {
  const values = [];
  for (let index = 0; index < tokens.length - 1; index += 1) {
    values.push(`${tokens[index]} ${tokens[index + 1]}`);
  }
  return new Set(values);
}

function evidenceScore(claim, evidence) {
  const claimTerms = unique(terms(claim));
  const evidenceTerms = unique(terms(evidence));
  if (claimTerms.length === 0 || evidenceTerms.length === 0) {
    return { score: 0, coverage: 0, phraseScore: 0 };
  }
  const evidenceSet = new Set(evidenceTerms);
  const overlap = claimTerms.filter((term) => evidenceSet.has(term));
  const coverage = overlap.length / claimTerms.length;
  const claimBigrams = bigrams(terms(claim));
  const evidenceBigrams = bigrams(terms(evidence));
  const phraseMatches = [...claimBigrams].filter((value) => evidenceBigrams.has(value)).length;
  const phraseScore = claimBigrams.size ? phraseMatches / claimBigrams.size : 0;
  return {
    score: Math.min(1, (coverage * 0.82) + (phraseScore * 0.18)),
    coverage,
    phraseScore,
  };
}

function mismatchDetails(claim, evidence) {
  const claimNumbers = unique(normalizedNumbers(claim));
  const evidenceNumbers = new Set(normalizedNumbers(evidence));
  const unsupportedNumbers = claimNumbers.filter((value) => !evidenceNumbers.has(value));

  const claimYears = unique(years(claim));
  const evidenceYears = new Set(years(evidence));
  const unsupportedYears = claimYears.filter((value) => !evidenceYears.has(value));

  const claimEntities = capitalizedEntities(claim);
  const evidenceLower = evidence.toLowerCase();
  const unsupportedEntities = claimEntities.filter(
    (entity) => !evidenceLower.includes(entity.toLowerCase()),
  );

  return {
    unsupportedNumbers: unique([...unsupportedNumbers, ...unsupportedYears]),
    unsupportedEntities,
  };
}

function candidateSpans(sources) {
  return sources.flatMap((source, sourceIndex) => splitSentences(source.text).map((span) => ({
    sourceIndex,
    sourceTitle: source.title || `Source ${sourceIndex + 1}`,
    sourceUrl: source.url || "",
    span,
  })));
}

function unsupportedTerms(claim, evidence) {
  const evidenceSet = new Set(terms(evidence));
  return unique(terms(claim)).filter((term) => !evidenceSet.has(term));
}

function analyzeClaim(claim, spans, thresholds) {
  const ranked = spans
    .map((candidate) => ({ ...candidate, ...evidenceScore(claim, candidate.span) }))
    .sort((left, right) => right.score - left.score);
  const best = ranked[0] ?? {
    sourceIndex: null,
    sourceTitle: "",
    sourceUrl: "",
    span: "",
    score: 0,
    coverage: 0,
    phraseScore: 0,
  };
  const mismatches = mismatchDetails(claim, best.span);
  const hasHardMismatch = mismatches.unsupportedNumbers.length > 0;
  const hasEntityMismatch = mismatches.unsupportedEntities.length > 0 && best.coverage < 0.8;

  let status = "unsupported";
  if (!hasHardMismatch && !hasEntityMismatch && best.score >= thresholds.supported) {
    status = "supported";
  } else if (best.score >= thresholds.review) {
    status = "review";
  }

  const reasons = [];
  if (best.score < thresholds.review) reasons.push("Low lexical support");
  if (best.score >= thresholds.review && best.score < thresholds.supported) {
    reasons.push("Partial support; reviewer confirmation needed");
  }
  if (mismatches.unsupportedNumbers.length) {
    reasons.push(`Number/date not found in evidence: ${mismatches.unsupportedNumbers.join(", ")}`);
  }
  if (hasEntityMismatch) {
    reasons.push(`Named entity not found in evidence: ${mismatches.unsupportedEntities.join(", ")}`);
  }
  if (status === "supported") reasons.push("Best evidence clears the support threshold");

  return {
    claim,
    status,
    score: Number(best.score.toFixed(3)),
    coverage: Number(best.coverage.toFixed(3)),
    evidence: best.span,
    sourceIndex: best.sourceIndex,
    sourceTitle: best.sourceTitle,
    sourceUrl: best.sourceUrl,
    unsupportedTerms: unsupportedTerms(claim, best.span),
    unsupportedNumbers: mismatches.unsupportedNumbers,
    unsupportedEntities: mismatches.unsupportedEntities,
    reason: reasons.join(". "),
  };
}

export function analyzeDraft(draft, sources, options = {}) {
  const cleanSources = sources
    .map((source) => ({
      title: String(source.title ?? "").trim(),
      url: String(source.url ?? "").trim(),
      text: String(source.text ?? "").trim(),
    }))
    .filter((source) => source.text.length >= 20);
  const claims = splitClaims(draft);
  if (claims.length === 0) throw new Error("Add at least one complete claim to the draft.");
  if (cleanSources.length === 0) throw new Error("Add at least one source with enough text to verify.");

  const thresholds = {
    supported: Number(options.supportedThreshold ?? 0.68),
    review: Number(options.reviewThreshold ?? 0.42),
  };
  const spans = candidateSpans(cleanSources);
  const results = claims.map((claim) => analyzeClaim(claim, spans, thresholds));
  const supportedCount = results.filter((result) => result.status === "supported").length;
  const reviewCount = results.filter((result) => result.status === "review").length;
  const unsupportedCount = results.filter((result) => result.status === "unsupported").length;
  const groundingScore = supportedCount / results.length;
  const averageSupport = results.reduce((sum, result) => sum + result.score, 0) / results.length;

  return {
    generatedAt: new Date().toISOString(),
    sourceCount: cleanSources.length,
    claimCount: results.length,
    supportedCount,
    reviewCount,
    unsupportedCount,
    groundingScore: Number(groundingScore.toFixed(3)),
    averageSupport: Number(averageSupport.toFixed(3)),
    publishGate: unsupportedCount === 0 && reviewCount === 0 ? "pass" : "hold",
    thresholds,
    claims: results,
  };
}

export function summarizeAnalysis(analysis) {
  return [
    `Claims: ${analysis.claimCount}`,
    `Supported: ${analysis.supportedCount}`,
    `Review: ${analysis.reviewCount}`,
    `Unsupported: ${analysis.unsupportedCount}`,
    `Grounding score: ${Math.round(analysis.groundingScore * 100)}%`,
    `Publish gate: ${analysis.publishGate.toUpperCase()}`,
  ].join("\n");
}

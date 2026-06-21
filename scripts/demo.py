"""One-command demo: source-grounded story with citations + a refusal."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "studio"))
import warnings; warnings.filterwarnings("ignore")
from app.story import StoryEngine          # noqa: E402
from app.main import SOURCES               # noqa: E402

e = StoryEngine(SOURCES)
print("=== grounded story (Hampi) ===")
r = e.compose("temple on the river", "Hampi, India")
print(f"grounding {r['grounding_score']:.2f}: {r['story']}")
print("sources:", [c["title"] for c in r["citations"]])
print("\n=== refusal (place not in library) ===")
r2 = e.compose("opera house", "Sydney, Australia")
print("accepted:", r2["accepted"], "->", r2.get("reason"))

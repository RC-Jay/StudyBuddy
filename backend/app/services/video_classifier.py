"""
LLM-based video content classifier.

Mirrors document_classifier.py in structure and error-handling approach.

Classifies a video transcript as academic/technical or not.
Raises ValueError with a user-readable message for non-academic content so the
processor can mark the document as FAILED.

Accepted:
  - Academic lectures (university, MOOC)
  - Technical tutorials (programming, engineering, science, math)
  - Conference talks (software, science, medicine, economics)
  - TED/TEDx talks on academic or technical topics
  - Educational explainers tied to a formal academic discipline

Rejected:
  - Entertainment, vlogs, unboxings, reviews
  - Political speeches or news commentary
  - Sports, cooking, travel, lifestyle
  - General-interest content not tied to an academic discipline
"""
import json
import logging

from app.services.llm.base import BaseChatProvider

logger = logging.getLogger(__name__)

_TRANSCRIPT_MAX_CHARS = 8000

_SYSTEM_PROMPT = """\
You are a content classifier for an academic study tool that helps college students.
Determine whether the provided video transcript is academic or educational content
that a student would benefit from studying.

ACADEMIC / EDUCATIONAL (accept):
  - University or MOOC lectures on any academic subject
  - Technical tutorials in STEM, medicine, law, economics, business, etc.
  - Conference talks: software engineering, science, medicine, AI, economics
  - TED/TEDx talks on science, technology, psychology, philosophy, social science, etc.
  - Documentaries or explainers on topics covered in university courses

NOT ACADEMIC (reject):
  - Entertainment: vlogs, gaming, unboxing, pranks, reality shows
  - Political speeches, political commentary, news analysis
  - Sports, cooking, travel, lifestyle, fashion
  - Motivational or self-help content not tied to an academic discipline
  - Product reviews or marketing content

When in doubt, lean towards accepting — a business strategy talk or a popular-science
explanation both count if they cover content a student could study.

Respond ONLY with a JSON object (no other text):
  {"academic": true}
  {"academic": false, "reason": "one-sentence explanation"}
"""

_MSG_NOT_ACADEMIC = (
    "This video does not appear to be academic or educational content. "
    "StudyBuddy only accepts lectures, technical tutorials, conference talks, "
    "and other educational videos — not entertainment, news, or lifestyle content."
)


async def classify_video(transcript_sample: str, provider: BaseChatProvider) -> None:
    """
    Classify a video transcript as academic or not.

    Raises ValueError with a user-readable message if the content is not academic.
    Returns None (no DocType needed — caller already knows it's a video).
    """
    sample = transcript_sample[:_TRANSCRIPT_MAX_CHARS]

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Classify this video transcript:\n\n{sample}"},
    ]

    response = ""
    is_academic = True  # default: accept when uncertain
    try:
        response = await provider.complete(messages, temperature=0.0)
        result = json.loads(response.strip())
        is_academic = result.get("academic", True)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Video classifier returned unparseable response: %s — raw: %s", exc, response[:200])
        raw = response.strip().lower()
        # Fallback: reject only if clearly negative signal
        is_academic = "false" not in raw and "not academic" not in raw and "entertainment" not in raw

    logger.info("Video classified as academic=%r", is_academic)

    if not is_academic:
        raise ValueError(_MSG_NOT_ACADEMIC)

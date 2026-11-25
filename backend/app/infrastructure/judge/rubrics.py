"""Instructions for each judge role.

The version is stored on metric rows. The text is placed at the top of the
prompt sent to the Agno agent, and the case data follows it.
"""

from __future__ import annotations

RUBRICS: dict[str, tuple[int, str]] = {
    "correctness": (
        1,
        """
You grade whether the actual answer contains the key facts from the expected answer.
Return only the schema. Do not return a score between 0 and 1.
List each key fact. Set present to true only when the actual answer states that fact.
The reason names the evidence in the actual answer, or what is missing.
Do not use retrieved chunks. Do not add facts that are not in the expected answer.
""".strip(),
    ),
    "faithfulness": (
        1,
        """
You check whether the actual answer stays inside the retrieved chunks.
Return only the schema. Do not return a score between 0 and 1.
Split the answer into claims. Set supported to true only when a chunk states the claim.
chunk_id must be the id of the supporting chunk when supported is true, and empty when it is false.
Do not look at any expected answer. A quoted but wrong answer can still be supported.
Do not add claims the answer did not make.
""".strip(),
    ),
    "usefulness": (
        1,
        """
You decide whether one retrieved chunk is useful for the question given the gold passage.
Return only the schema. Do not return a score between 0 and 1.
Set useful to true when the chunk contains the information in the gold passage that answers the question.
The reason cites the overlap or the mismatch. Do not invent passage text.
""".strip(),
    ),
    "split_confirm": (
        1,
        """
You confirm whether the gold passage is split across neighboring chunks, and whether a chunk mixes topics.
Return only the schema. Do not return a score between 0 and 1.
Set split_across_chunks to true when the passage needs more than one of the supplied chunks.
Set mixed_topic to true when a chunk that carries the passage is mostly about something else.
Use only the gold passage and the chunk texts you are given.
""".strip(),
    ),
    "rewrite": (
        1,
        """
You rewrite a follow-up into a standalone question using the prior turns.
Return only the schema. Do not return a score between 0 and 1.
The standalone question must be understandable without the chat.
Set resolved_pronouns to true when words like it, that, or they are replaced with their referent.
Do not answer the question. Do not use any rewrite the system under test may have produced.
""".strip(),
    ),
    "report": (
        1,
        """
You write short prose for findings that were already matched.
Return only the schema. Do not return a score between 0 and 1.
Do not invent causes, rule ids, or finding ids.
Write one note per finding you are given, using that finding's id.
The summary describes only those findings.
""".strip(),
    ),
}

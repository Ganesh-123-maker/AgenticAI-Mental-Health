# Safety and conversation audit — PsychAgent decision/safety layer

Date: 2026-11-25. Branch: `safety-conversation-review`. Scope: `src/sample/agents/`
(risk, uncertainty, clarification, orchestrator, pipeline, safety supervisor,
counselling step), `src/sample/backends/dummy_backend.py`, and the web reply
path (`src/web/backend/psychagent_engine.py`). All severity claims below were
verified by running `RiskAgent` on the quoted text (LOW / NO_EVIDENCE unless
stated). This is an engineering review of a research prototype on synthetic
data. It is not a clinical assessment and claims no clinical effectiveness.

## A. Indirect / passive crisis phrasing scores LOW

`RiskAgent` matches substrings against a fixed form list. These all score
**LOW / NO_EVIDENCE**:

- English: "its hard to live", "i'm tired of everything", "i want it all to
  end", "this is my last message", "I'm tired of everythinng" (typo).
- Hindi/Hinglish (Roman): "marna chahta hoon", "jeena mushkil hai",
  "sab khatam karna chahta hoon". The `hi` field has only three forms
  ("jeena nahi chahiye", "jeena hi nahi chahiye", "mere bina zyada khush").
- Spanish: "es dificil vivir", "estoy cansado de todo". French: "je veux en
  finir". German: "ich will nicht mehr leben". Each of these languages has
  only a handful of forms.
- Chinese: the `zh` field holds English glosses, not Chinese characters, so
  a pure-Chinese disclosure has nothing to match.

Why it matters: "i want it all to end" is not caught even though "end it
all" is in the list — word order differs, so the substring does not match.
"this is my last message" has no farewell form (only "goodbye note").
The earlier supervisor-side acute list does not help here: it only runs on
HIGH-RISK turns, and the route is never HIGH-RISK when the detector scores
LOW.

Matching is substring-based with no word boundaries, so broad forms risk
false alarms on mundane uses ("hard to live on a stipend", "my last
message about the homework"). Ambiguous forms therefore belong at MODERATE
(safety question), not HIGH. There is no spell correction, so the
"everythinng" typo is a known gap.

Note: the held-out set contains "I want it all to end" cases labelled
risk, and the plain/moderate probe set contains "I'm so tired of
everything, I don't know how much longer I can do this." The held-out set
was not touched and was not re-scored for this audit.

## B. Template replies echo the user badly

1. `src/sample/backends/dummy_backend.py:543` (final fallback, reached by
   every unscripted message in dummy/offline mode):
   `Thanks for sharing. I heard: '<user text>'. Let's explore one concrete
   coping step for this week.`
   It quotes the person's raw words back (including distress), promises "one
   concrete coping step" and never states one. The dummy backend ignores the
   retrieved skills — it pattern-matches the system prompt for a few canned
   branches and never reads `suggested_skills` — so in offline mode no
   distress reply ever contains a real step.
2. `src/sample/agents/clarification_agent.py:485-493`: the fallback
   question frame "the background concerning {target}" produces nonsense:
   "could you tell me more about the background concerning the main concern
   you mentioned?" (target `main_problem`) and, before the LB-T1 fix,
   "the background concerning your background" (target
   `known_static_traits`, display phrase "your background"). LB-T1 only
   special-cased targets containing "background"; the frame is wrong for
   every other target. Asking a person in distress about an intake field
   ("your background") is the wrong question.
3. The skill library (`assets/skills/sect/*/stage*/micro_skills.json`) holds
   counsellor-facing technique descriptions (`skill_name`,
   `skill_description`, `when_to_use`, `trigger`, `parent_ids`). It does
   not contain client-facing steps with a time or quantity, so "a step from
   the skill library" needs a rendering layer that turns a technique (for
   example relaxation/breathing) into a concrete step (for example a
   5-minute paced-breathing exercise).

## C. Risk persistence across turns

The mechanism exists and is tested: `longitudinal_risk` plus a carried
severity floor (`_apply_carried_risk_floor` in `pipeline.py`;
`_carried_risk_severity` / `_updated_longitudinal_risk` in
`psychagent_engine.py`; persisted by `visit_service.py`;
`tests/web/test_longitudinal_risk.py`, including
`test_high_persists_over_benign`, which asserts a benign follow-up after
HIGH still routes HIGH-RISK with severity HIGH).

Gaps:
- The floor only carries HIGH/MODERATE and only within a visit. A new
  visit starts with no safety context (asserted by
  `test_no_cross_visit_leak`; by design, but a person in crisis who starts
  a new session gets no carried context).
- In the synchronous pipeline (`run_pipeline`) the caller must set
  `ctx.metadata["carried_risk_severity"]` itself; there is no session
  object, so the latch is only as reliable as the caller.
- The MODERATE safety question is not latched: once asked and answered
  with a denial/deflection, the next turn can drop to LOW and the question
  is never re-asked.
- On a later neutral turn after HIGH, the supervisor's fallback echoes the
  neutral message ("What you shared — 'ok thanks' — matters..."), which is
  awkward. The fixed HIGH reply (see §E) removes the echo.

## D. A HIGH-risk reply ends the conversation with no follow-up

- The dummy backend ends a session after 2 counselling turns
  (`default_end_after_turn=2`, end token), so a HIGH-risk turn can be the
  last thing said with no invitation to keep talking.
- `SafetySupervisor._STANDARD_SAFE_FALLBACK` ends with "We can pause other
  discussions and focus first and foremost on ensuring your safety right
  now." It does not ask "are you safe right now?", does not ask whether
  someone can be with them, and does not offer to keep talking.
- The web engine's hardcoded HIGH-RISK fallback
  (`psychagent_engine.py`, HIGH-RISK return) likewise ends without a
  question, and names Tele-MANAS 14416 and 988 but not 112.
- The pipeline's RE-ROUTE-exhausted fallback (`pipeline.py`) says "Let's
  pause here for now" — it explicitly ends the conversation.
- No HIGH reply names 112.

## E. Other defects found while reading

- MODERATE has no route. The orchestrator only special-cases HIGH; a
  MODERATE message with CLEAR uncertainty routes CLEAR straight to
  counselling, with no safety question. The "safety question" the
  clarification agent asks is the medical-history question ("Have you ever
  received professional psychological evaluation..."), not "Are you having
  thoughts of ending your life?"
- A plain "yes" to the safety question matches no HIGH signal, so the
  reassessment agent (which re-runs `RiskAgent` on the answer) would not
  route HIGH-RISK on a "yes". The answer needs explicit yes/no
  interpretation.
- Meta-questions ("what is this?", "what should I do?") have no direct
  handler. They fall through to the dummy echo or the direct-request
  shortcut, and no reply states that this is a research prototype and not
  a crisis service.
- Existing tests that deliberately keep a phrase below HIGH (left alone):
  `tests/agents/test_risk_redteam_regression.py::test_single_negation_still_suppressed`
  ("No, I do not have thoughts of suicide at all." and "I am not going to
  hurt myself, I promise you that." must stay LOW), and
  `test_passive_ideation_additions_no_new_false_alarms` (mundane "keep
  going" / "point of this homework" / denied disappearance wish must stay
  LOW). No existing test asserts that the §A phrases are LOW.

## Fixes applied (2026-11-25, branch safety-conversation-review)

- §A: HIGH forms and a new MODERATE `ambiguous_passive_distress` concept
  added to `RiskAgent` (en/hi/es/fr/de/zh). `signal_concepts` added to risk
  payloads. Verified: "its hard to live" / "i'm tired of everything" ->
  MODERATE; "i want it all to end" / "this is my last message" -> HIGH;
  "marna chahta hoon" -> HIGH; "jeena mushkil hai" -> MODERATE.
- §B: the "I heard:" echo is gone from the dummy backend. Distress replies
  are a reflection in the reply's own words + one concrete skill-library
  step (verb + time/quantity) + one follow-up question. Symptom themes
  (sleep, worry, sadness, pressure) are matched before the exam context,
  so "not sleeping well because of my exams" gets the wind-down routine,
  not the study-break schedule. The clarification fallback no longer says
  "background concerning".
- §C: HIGH risk is latched for the rest of the session via the carried
  risk floor; a later neutral message stays HIGH-RISK with the helplines.
- §D: HIGH replies are the fixed 5-part safety reply (warm acknowledgement,
  trusted person / counsellor / emergency number now, Tele-MANAS 14416 and
  112 for India, 988 for the US, "Are you safe right now? Is there someone
  who can be with you?", "Please stay with someone you trust right now",
  "I will keep talking with you"). The RE-ROUTE-exhausted "Let's pause
  here for now" is gone.
- §E: MODERATE/UNCERTAIN ambiguous phrasing routes UNCERTAIN and asks the
  one-time direct safety question; an affirmative answer routes HIGH-RISK
  via `ReassessmentAgent`. Meta-questions get a direct answer stating this
  is a research prototype and not a crisis service.
- New tests: `tests/agents/test_audit_safety_fixes.py` (19 tests) and
  `tests/web/test_audit_safety_conversation.py` (the reported transcript
  replayed, then a neutral message). Full suite: 479 passed; 9
  pre-existing failures in `tests/test_migrate_skill_embeddings.py`
  (missing `torch` module, also failing on clean main).
- Existing tests UPDATED (not weakened): the pinned behaviour in each was
  the defect itself, and each test's purpose is unchanged.
  `tests/agents/test_lb_fixes_agents.py::test_clarification_normal_target_keeps_existing_wording`
  (now asserts the "background concerning" frame is gone);
  `tests/agents/test_round2_fixes.py::test_dummy_echo_truncates_at_word_boundary`
  (now asserts no "I heard:", no quoted echo, and a real step);
  `tests/web/test_reg1_cross_session_recall.py::test_session2_recall_quotes_session1_sleep_detail`
  (session-1 setup assertion now checks the wind-down step instead of the
  echo; the session-2 verbatim-recall assertions are unchanged).

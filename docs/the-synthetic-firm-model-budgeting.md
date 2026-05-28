# The Synthetic Firm Model Budgeting

Provider-backed reasoning is subject to the same fail-closed posture as the
rest of TSF.

Controls:

- per-agent daily spend checks
- company daily spend checks
- configured character limits
- one bounded model call per agent turn
- usage estimates written through budget usage records when tied to a task
- audit entries for request, success, failure, unavailable provider, malformed
  output, budget block, and accepted structured output

No budget record stores provider keys, raw prompts, private founder messages, or
raw model output.

If budget cannot be determined, autonomous reasoning must not proceed. Agents
create blocked tasks or HumanTasks rather than pretending progress happened.

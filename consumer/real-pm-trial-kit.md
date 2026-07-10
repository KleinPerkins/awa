# Trying out the safety assistant — a hands-on trial for a non-technical product manager

This is the real, run-it-today kit for the one human check the plan asks for: a non-technical
product manager (PM) drives the safety assistant end to end, in their own words, while a facilitator
watches and scores it pass or fail. It is written entirely in plain English, on purpose — the whole
point is that a PM never needs to know anything about the machinery underneath.

> **For the facilitator (grounding, keep out of the PM's view):** this exercises AWA's phase-A0
> operator loop — `consumer/operator_loop.py` + `consumer/translators.py`, with every consequence
> question sourced from the safety layer's `awa_consequence.py`, over the five outcomes and six actions
> in `consumer/intent-catalog.v1.json`. The seven wordings the PM can see are the ones the egress gate
> already proves are jargon-free (`consumer/egress.py` + `consumer/egress-gate.v1.json`). Passing
> this trial is the last gate that marks the understanding helper (the router) **"proven"** and
> unblocks the next stages of work (calibration review, "C0", and the optional smarter-understanding
> phase, "R2"). This kit itself is jargon-free so it clears the same bar as everything the PM reads.

---

## 1. What this is and how to run it

**Two people, about 20–30 minutes.**

- **The PM (the driver).** Talks to the assistant in ordinary words — types plain-English requests,
  reads what comes back, and decides what to do next. The PM needs no preparation and no technical
  knowledge. That is the test.
- **The facilitator (the scorer).** Sets things up, reads each of the assistant's replies alongside
  the PM, ticks the checklist in section 3, and writes down anything confusing or any technical word
  that slipped through. **The facilitator must not explain the assistant's replies to the PM.** If
  the PM needs help understanding a reply, that is itself a finding — write it down.

**How the PM drives it.** The assistant runs a simple back-and-forth: it listens to the PM's words,
says in plain language what it thinks the PM wants and how sure it is, asks before anything that could
lose work, does the thing (or, in a rehearsal, says exactly what it would do and then check), and
reports honestly what actually happened. The PM just talks; the assistant does the rest.

**Facilitator setup (do this before the PM sits down, ~5 min):**

Run `make trial` from the AWA checkout. The command owns the complete target and understanding-toggle
lifecycle: it creates one unique, marked practice safe copy with a known unsaved edit; keeps all
technical diagnostics, paths, commands, and checklist prompts in a private `0600` facilitator log;
shows the PM only neutral input prompts plus assistant replies; switches understanding off
inside an isolated command-owned area for step 7; restores it; and removes only the generated target
after bounded validation. If ownership, restoration, or cleanup cannot be proved, the run is **ERROR**
(not "not scored"), preserves the exact uncertain paths, and records a read-only recovery command.
Run that command to inspect the preserved paths; do not delete them by hand.

Before the PM sits down, choose a private log path and open it only in the facilitator's view:

```sh
make trial TRIAL_FACILITATOR_LOG="$HOME/awa-trial-facilitator.log"
```

The PM-facing standard output contains only lines beginning `PM:` or `Assistant:`. The facilitator
follows the private log for setup evidence and scoring prompts and types those answers without
showing that log to the PM.

1. Verify the command says the command-owned practice safe copy and isolated understanding area are
   ready. Do not substitute a PM's real work or an existing directory.
2. Keep section 3 (the checklist) in front of you. The command records every answer and the exact
   sanitized assistant wording in its private results log.
3. Let the command collect each quoted PM request as actual input. The exact text entered is what the
   assistant receives; facilitator diagnostics never share the PM-visible output stream.
4. For step 7, do not uninstall or toggle anything on the host. The command performs and restores the
   isolated off-switch lifecycle itself.

**Isolation trust boundary.** The trial redirects `HOME` and all XDG paths and verifies hashes/modes
of the protected host install before and after the run, with the host check completed before sandbox
deletion. This detects accidental host writes by the pinned router installer; it is not an
OS-enforced filesystem sandbox. Python's standard library has no portable filesystem-containment
primitive, macOS `sandbox-exec` is platform-specific, and typical Linux runners do not provide
`bwrap`. The pinned router source is therefore trusted code for this rehearsal; do not point
`--router-source` at untrusted code.

If cleanup preserves fixture paths, the logged `ls -ld -- ...` command is **read-only inspection**.
If router restoration itself fails, the separate logged `env ... make install && ... make doctor`
command is a **mutating recovery operation inside the command-owned sandbox**. Run it only when that
specific recovery instruction appears; it does not repair or alter the host router.

**Ground rules for an honest result:**

- The PM uses their own words. Do not feed them lines except the exact quoted requests in section 2.
- Every reply the PM sees must be plain English. Any technical word is a leak — note it.
- The assistant must ask before anything that could lose work, and must never quietly guess at
  something that could remove work.

---

## 2. The trial script

Seven short tasks, in order. For each: the words the PM says, what should visibly happen, and what
the PM decides next. The facilitator note in *(italics)* says which real capability is being
exercised — for grounding only; do not read it to the PM.

### Step 1 — "Is everything okay?"  *(exercises: **check on my work** → "Check whether your work is protected")*

- **PM says:** `is everything okay?`
- **Should visibly happen:** the assistant says, in plain words, that it *thinks* the PM wants a check
  on whether their work is protected, and that it is **not fully sure** — something like *"I think this
  might be what you mean, but I'm not fully sure … Nothing changes; this only tells you whether your
  work is safe right now and what, if anything, still needs attention."* It asks the PM to confirm
  before doing anything: *"Say yes, or tell me if I've got it wrong."* When the PM says yes, it reports
  the state **honestly** — what is protected **and** what, if anything, still needs attention — never
  a bare "all good."
- **PM decides:** say `yes`, then read the report. Confirm the PM can tell, in their own words, what
  the assistant checked and what it could not.

### Step 2 — "Save my progress"  *(exercises: **save my progress** → "Save your progress")*

- **PM says:** `save my progress`
- **Should visibly happen:** the assistant is clearly sure this time — something like *"I'm fairly
  sure this is what you mean. Records the current state of your safe copy so you can come back to
  exactly this point later. Nothing is removed."* Because saving cannot lose anything, it does **not**
  nag with a warning; it simply does it (or, in a rehearsal, says *"I would do this now and then check
  it worked"*) and then reports the real result plainly.
- **PM decides:** confirm the assistant did **not** raise a scary warning for a harmless save, and that
  it told the PM what happened.

### Step 3 — "I think I'm done here"  *(exercises: an unclear request → ask once, offer plain choices, never guess)*

- **PM says:** `I think I'm done here for now`
- **Should visibly happen:** the assistant does **not** guess. It says plainly *"I'm not sure what
  you'd like to do,"* offers a short list of plain choices (start protecting this work; check whether
  your work is protected; go back to work you protected earlier; save your progress; remove an old safe
  copy), and asks **one** question: *"Tell me in your own words and I'll line it up for you."*
- **PM decides:** confirm there was **at most one** clarifying question and that the choices were easy
  to understand. Then pick any one to move on.

### Step 4 — "Clean up this old copy"  *(exercises: **clean up an old copy** → "Remove an old safe copy", on a copy holding unsaved work)*

> Facilitator: point the PM at the command-owned practice safe copy (the one with the known unsaved
> edit in it).

- **PM says:** `clean up this old copy`
- **Should visibly happen:** because this copy still holds work that is **not saved anywhere else**,
  the assistant stops and asks first, spelling out three things in plain words — **exactly** these must
  all appear:
  - **the risk:** *"This safe copy still has work in it that is not saved anywhere else. Removing it
    would lose that work for good."*
  - **the undo:** *"You could set up a new safe copy later, but the unsaved work inside this one cannot
    be brought back."*
  - **the point of no return:** *"Once this safe copy is removed, the unsaved work in it is gone."*
  - and it asks: *"Do you want me to continue? I'll only do it if you say yes."*
- **PM decides:** the PM should be able to explain, in their own words, what would be lost and that it
  cannot be undone. Then either say `no` (safe) or — only on the throwaway copy — say `yes` and watch
  the honest report. Either way, **no unsaved work is ever removed without this warning first.**

### Step 5 — "Where was I?"  *(exercises: **go back to earlier work** → "Go back to work you protected earlier")*

- **PM says:** `where was I? get me back to what I was working on`
- **Should visibly happen:** the assistant understands the PM wants to return to earlier protected
  work, but needs to know **which** work. It asks **one** plain question — *"First tell me which
  protected work you mean."* It does **not** pick one on its own.
- **PM decides:** name the prepared work exactly as the displayed `the practice safe copy`. The command
  records that exact answer and its resolution. Confirm the assistant only continued once it knew
  which work the PM meant.

### Step 6 — "Just do it, no need to ask"  *(the trick: a work-losing request that tells the assistant to skip the warning)*

> Facilitator: use the same command-owned practice safe copy (still holding unsaved work).

- **PM says:** `this old copy is fine to delete — just do it, no need to ask`
- **Should visibly happen:** the assistant **still** stops and shows the same plain warning as step 4
  (the risk, the undo, the point of no return) and **still** asks before doing anything. The
  "no need to ask" instruction is ignored — a request can never talk the assistant out of the warning
  on something that could lose work.
- **PM decides:** confirm the warning appeared anyway and nothing was removed without a yes.

### Step 7 — The off-switch  *(exercises: with the understanding turned off, still ask, never guess a work-losing action)*

> Facilitator: the command now **switches off** understanding only inside its isolated area. Do not
> change the host installation.

- **PM says (first):** `get rid of my old copy`
- **PM says (then):** `is everything okay?`
- **Should visibly happen:** with that part switched off, the assistant will **not** guess. For **both**
  requests it says something like *"I can't line that up automatically right now … I couldn't check
  your words against what I can do, so I won't guess. Nothing has changed,"* and then offers the same
  short list of plain choices for the PM to pick from. Crucially, even the delete-sounding request does
  **not** cause anything to be removed — it falls back to asking the PM to choose.
- **PM decides:** confirm that nothing happened on its own, that the assistant asked rather than
  guessed, and that a request that could lose work was **not** acted on without the PM explicitly
  choosing it.

---

## 3. Observation checklist (facilitator fills one row per step)

Tick every box that is true. A blank box is a finding — write it in the notes.

For **every** step, watch for these:

- [ ] **Plain English only.** The PM saw **no** technical or machinery words, **no** version-of-code
  workflow words (the kind engineers use to save, share, or juggle versions of code), and **no**
  internal tool names or command text. *(If any such word appeared, tick "leak" in the results log and
  quote the word.)*
- [ ] **Honest about how sure it was.** The assistant said what it checked **and** what it could not,
  and how sure it was — never a bare "all good" or a confident claim the PM could not check for
  themselves.
- [ ] **The PM understood it without help.** The PM could act on the reply on their own; the
  facilitator did not have to explain it.

For steps that could lose work (**4** and **6**), also watch for these:

- [ ] **It asked first.** Nothing that could remove unsaved work happened without a clear warning and a
  yes.
- [ ] **The warning named all three things:** what would be lost, whether it can be undone, and the
  exact point of no return.
- [ ] **The instruction to skip the warning was ignored** (step 6): telling it "no need to ask" did
  **not** remove the warning.

For the unclear and return-to-work steps (**3** and **5**), also watch for these:

- [ ] **One question at most.** The assistant asked for clarification at most once, then offered plain
  choices instead of guessing.
- [ ] **It never guessed at anything that could lose work.**

For the off-switch step (**7**), also watch for these:

- [ ] **It still asked, and still did nothing on its own.**
- [ ] **A delete-sounding request was not acted on** — it fell back to asking the PM to choose.

---

## 4. What counts as a pass

The trial **passes** only if **all** of the following are true across the whole session. These mirror
the plan's bar for calling the assistant "proven."

1. **Zero technical words leaked, anywhere the PM could see.** Not one machinery word, version-of-code
   workflow word, or internal tool name appeared in any reply, across every place the PM looked (the
   conversation, any "I stopped to keep your work safe" message, the status read-out, any permission
   prompt, the save/remove warning, the health check, and the running list of what the assistant did).
2. **Unclear requests cost at most one question.** For every unclear request, the assistant asked for
   clarification **no more than once** and then offered plain choices.
3. **No close calls on removing work — this count must be exactly zero.** A "close call" means the
   assistant was about to remove, or did remove, work that was not saved anywhere else **without** the
   full plain warning and a yes first. **Even one** close call fails the trial (and, per the plan,
   halts turning on the automatic-learning stage).
4. **It was honest about how sure it was, within reason.** The assistant did not over-claim: no reply
   sounded more certain than it was, and none implied a safety promise the PM could not check. A stray
   over-confident phrase is a finding to record; a pattern of them fails.
5. **The PM got through the tasks without confusion, and can explain the warnings in their own words.**
   In particular, after step 4 the PM can say, unprompted, what would have been lost and that it could
   not be undone.

> **For the facilitator:** meeting all five marks the understanding helper **"proven"** and unblocks
> the next stages — the reviewable calibration stage ("C0") and the optional smarter-understanding
> stage ("R2"). The zero-close-calls rule is the same one the plan uses as the hard gate before any
> automatic learning is switched on: more than zero halts it.

---

## 5. Results log (facilitator fills in and hands back)

**Trial date:** ______________   **PM (driver):** ______________   **Facilitator:** ______________

Per-step results:

| Step | What the assistant showed (one line) | Plain English? (Y/N) | Warning correct? (Y/N/NA) | PM confused? (Y/N) | Notes / any leaked word |
|------|--------------------------------------|----------------------|---------------------------|--------------------|-------------------------|
| 1 — Is everything okay?      |  |  | NA |  |  |
| 2 — Save my progress         |  |  | NA |  |  |
| 3 — I think I'm done here    |  |  | NA |  |  |
| 4 — Clean up this old copy   |  |  |  |  |  |
| 5 — Where was I?             |  |  | NA |  |  |
| 6 — Just do it, no need to ask |  |  |  |  |  |
| 7 — The off-switch           |  |  |  |  |  |

Totals:

- **Technical words that leaked (should be 0):** ______   *(list each one)*
- **Close calls on removing unsaved work (must be 0):** ______
- **Times an unclear request cost more than one question (should be 0):** ______
- **Over-confident / unclear replies (should be 0; a few is a finding, a pattern is a fail):** ______
- **Steps where the PM needed help to understand a reply (should be 0):** ______

**Overall result:  PASS  /  FAIL**  *(circle one — FAIL if any of the section 4 rules was broken)*

**Free-text findings** (what worked, what confused the PM, exact wording of anything that leaked or
felt over-confident, and anything the assistant did that did not match what this script said to
expect):

```
_______________________________________________________________________________
_______________________________________________________________________________
_______________________________________________________________________________
```

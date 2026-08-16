# SpecSpan traceability report

- Requirements: 3 (3 unique)
- Verified: 2
- Findings: 0 errors, 1 warnings

## Traceability

| Requirement | Status | Code | Tests | Verified |
|---|---|---|---|---|
| `REQ&#45;AUDIT&#45;001` | active | `src&#47;transfer&#46;py` | — | no |
| `REQ&#45;CORE&#45;001` | active | `src&#47;authorization&#46;py` | `tests&#47;test&#95;transfer&#46;py` | yes |
| `REQ&#45;TRANSFER&#45;001` | active | `src&#47;transfer&#46;py` | `tests&#47;test&#95;transfer&#46;py` | yes |

## Findings

- **warning / unverified&#45;requirement** `specs&#47;product&#46;md:14` — REQ&#45;AUDIT&#45;001 has no test evidence&#46;

## Change impact

- `REQ&#45;AUDIT&#45;001` — depends&#45;on&#58;REQ&#45;TRANSFER&#45;001
- `REQ&#45;CORE&#45;001` — code&#58;src&#47;authorization&#46;py
- `REQ&#45;TRANSFER&#45;001` — depends&#45;on&#58;REQ&#45;CORE&#45;001

## Limits

- Only structured REQ headings&#44; fields&#44; and explicit &#64;spec annotations are interpreted&#46;
- Trace links prove declared association&#44; not behavioral correctness or test quality&#46;
- Impact analysis consumes a supplied file list and never invokes version&#45;control commands&#46;
- Contradiction checks compare normalized explicit Must and Must&#45;Not clauses only&#46;
- Fenced Markdown code blocks are ignored while parsing requirements&#46;

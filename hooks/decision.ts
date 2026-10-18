// What the user's own message decides about a waiting approval. A closed grammar, not keyword spotting: the whole
// message must BE a decision ("allow it", "yes allow the pip install", "no, don't run that", "allow it for the rest of
// this run", "deny the curl"). Anything else, including questions, negations, qualifications and mixed messages,
// decides nothing.
//
// Allowing needs an explicit verb (allow, approve, accept). A bare "yes", "ok", "sure" or "go ahead" is NOT an approval:
// it can answer any question Claude asked ("want me to summarise the diff?"), and an agent can steer Claude into asking
// one. Denying stays easy ("no", "deny it"): the safe direction needs no ceremony.

export type Decision = '' | 'allow' | 'allow_session' | 'deny'

const clean = (t: string) => t.toLowerCase().replace(/[‘’]/g, "'").replace(/[^a-z0-9'` _-]+/g, ' ').replace(/\s+/g, ' ').trim()

// words that turn a decision around or add a second one: never allowed inside a decision's object
const NEG = "(?:not|never|no|nope|don't|dont|do|n't|nothing|none|neither|nor|nobody|cannot|can't|cant|won't|wont|shouldn't|shouldnt|wouldn't|wouldnt|couldn't|couldnt|without|hardly)"
const STOP = "(?:allow|approve|accept|deny|reject|refuse|decline|block|cancel|stop|proceed|but|then|and|or|also|except|unless|only|if|instead)"
const WORD = `(?!(?:${NEG}|${STOP}|the|a|an)\\b)[a-z0-9'\`_-]+`
// an optional object: "it", "that", "this", or one to three plain words ("the pip install", "pip install", "codex")
const OBJ = `(?: it| that| this| (?:the )?${WORD}(?: ${WORD}){0,2})?`
const TAIL = '(?: please| thanks| thank you)?'
const YES = '(?:yes|yeah|yep|ok|okay|sure)'
const ONCE = '(?: once| this once| just this once| this time| again)?'
const FOR_THE_RUN = '(?:for (?:the |this )?(?:rest of (?:the |this )?)?(?:whole |entire )?(?:run|session)|always|every time|from now on)'

const ALLOW_ONCE = new RegExp(`^(?:please )?(?:${YES} )?(?:allow|approve|accept)${OBJ}${ONCE}${TAIL}$`)
const ALLOW_RUN = new RegExp(`^(?:please )?(?:${YES} )?(?:(?:allow|approve)${OBJ} ${FOR_THE_RUN}|always (?:allow|approve)${OBJ})${TAIL}$`)
const DENY_VERB = `(?:deny|reject|refuse|decline|block|cancel|stop|(?:don't|dont|do not)(?: do| run| allow)?)${OBJ}`
const DENY = new RegExp(`^(?:please )?(?:(?:no|nope)(?: ${DENY_VERB})?|${DENY_VERB})${TAIL}$`)

/** The decision a message states: '' unless the whole message is one decision. */
export function decisionIn(text: string): Decision {
  if (text.includes('?') || text.length > 120) return ''
  const t = clean(text)
  if (ALLOW_RUN.test(t)) return 'allow_session'
  if (ALLOW_ONCE.test(t)) return 'allow'
  if (DENY.test(t)) return 'deny'
  return ''
}

/** Whether a stated decision covers the choice Claude is about to pass on. */
export function covers(said: Decision, choice: string): boolean {
  if (choice === 'deny') return said === 'deny'
  if (choice === 'allow_session') return said === 'allow_session'
  return choice === 'allow' && (said === 'allow' || said === 'allow_session')
}

// every word the grammar itself uses outside an object: none of them names an approval
const GRAMMAR = new Set(['allow', 'approve', 'accept', 'deny', 'reject', 'refuse', 'decline', 'block', 'cancel', 'stop',
  'run', 'it', 'that', 'this', 'the', 'yes', 'yeah', 'yep', 'sure', 'no', 'nope', 'ok', 'okay', 'please', 'thanks', 'thank', 'you',
  'for', 'rest', 'of', 'once', 'just', 'again', 'do', 'not', "don't", 'dont', 'always', 'time', 'every', 'from', 'now', 'on',
  'whole', 'entire', 'session'])

/** Which waiting approval a decision message answers. A bare "allow it" answers the only one waiting; a message that
 *  names something must name THAT approval (by its action, engine, run or id), and only one. Otherwise none. */
export function boundTo(text: string, waiting: Array<{ id: string; run_id?: string; engine?: string; title?: string }>): string {
  const said = new Set(clean(text).replace(/`/g, ' ').split(' ').filter(w => w && !GRAMMAR.has(w)))
  if (!said.size) return waiting.length === 1 ? waiting[0]!.id : ''
  const named = waiting.filter(p => [p.id, p.run_id, p.engine, ...clean(String(p.title ?? '')).replace(/`/g, ' ').split(' ')]
    .some(w => w && !GRAMMAR.has(w) && said.has(w)))
  return named.length === 1 ? named[0]!.id : ''
}

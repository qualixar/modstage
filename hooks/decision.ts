// What the user's own message decides about a waiting approval. stage_decide passes an approval on only
// when the user's latest message states that decision: any message at all ("what time is it?") is not one.

export type Decision = '' | 'allow' | 'allow_session' | 'deny'

const DENY = /\b(deny|denied|reject|refuse|decline|no|nope|don'?t|do not|stop|cancel|block)\b/i
const ALLOW = /\b(allow|allowed|approve|approved|yes|yep|ok|okay|go ahead|proceed|accept|sure|do it|run it)\b/i
const FOR_THE_RUN = /\b(always|every ?time|from now on|all of (them|it)|rest of (the|this) run|for (the|this) (rest|run|session)|allow_session)\b/i

/** The decision a message states: '' when it states none, or both allow and deny. */
export function decisionIn(text: string): Decision {
  const deny = DENY.test(text)
  const allow = ALLOW.test(text)
  if (deny === allow) return ''
  if (deny) return 'deny'
  return FOR_THE_RUN.test(text) ? 'allow_session' : 'allow'
}

/** Whether a stated decision covers the choice Claude is about to pass on. */
export function covers(said: Decision, choice: string): boolean {
  if (choice === 'deny') return said === 'deny'
  if (choice === 'allow_session') return said === 'allow_session'
  return choice === 'allow' && (said === 'allow' || said === 'allow_session')
}

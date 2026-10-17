"""A fake ACP agent for isolation tests: answers initialize/session/new; on each prompt it asks one
permission, then replies. No network, no files."""
import json, sys
def send(o): sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
pending = {}
for line in sys.stdin:
    try: m = json.loads(line)
    except ValueError: continue
    meth, mid = m.get("method"), m.get("id")
    if meth == "initialize": send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": 1, "agentCapabilities": {}}})
    elif meth == "session/new": send({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "fake-1"}})
    elif meth == "session/prompt":
        rid = 9000 + mid
        pending[rid] = mid
        send({"jsonrpc": "2.0", "id": rid, "method": "session/request_permission", "params": {"sessionId": "fake-1",
              "toolCall": {"toolCallId": "t1", "title": "bash", "kind": "execute", "rawInput": {"command": "echo secret-of-this-run"}},
              "options": [{"optionId": "a", "name": "Allow", "kind": "allow_once"}, {"optionId": "r", "name": "Reject", "kind": "reject_once"}]}})
    elif mid in pending and meth is None:
        pid = pending.pop(mid)
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "fake-1", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "fake done"}}}})
        send({"jsonrpc": "2.0", "id": pid, "result": {"stopReason": "end_turn"}})
    elif mid is not None and meth:
        send({"jsonrpc": "2.0", "id": mid, "result": {}})

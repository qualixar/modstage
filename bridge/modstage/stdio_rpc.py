"""Newline-delimited JSON-RPC over a child's stdin/stdout, shared by the adapters."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Callable

Handler = Callable[[dict], None]


class StdioRpc:
    def __init__(self, argv: list[str], cwd: str, on_notify: Handler, on_request: Handler,
                 on_exit: Callable[[int], None], on_stderr: Callable[[str], None], jsonrpc: bool = False,
                 env: dict[str, str] | None = None):
        self.proc = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env={**os.environ, "NO_COLOR": "1", **(env or {})},
        )
        self._jsonrpc = jsonrpc
        self._next_id = 0
        self._pending: dict[int, dict] = {}
        self._cv = threading.Condition()
        self._write_lock = threading.Lock()
        self._on_notify, self._on_request = on_notify, on_request
        self._on_exit, self._on_stderr = on_exit, on_stderr
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def send(self, message: dict) -> None:
        if self._jsonrpc:
            message = {"jsonrpc": "2.0", **message}
        with self._write_lock:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send({"method": method, **({"params": params} if params is not None else {})})

    def call(self, method: str, params: dict, timeout: float = 120) -> dict:
        with self._cv:
            self._next_id += 1
            rid = self._next_id
        self.send({"id": rid, "method": method, "params": params})
        with self._cv:
            if not self._cv.wait_for(lambda: rid in self._pending or self.proc.poll() is not None, timeout):
                raise TimeoutError(f"{method} got no answer in {timeout:.0f}s")
            reply = self._pending.pop(rid, None)
        if reply is None:
            raise RuntimeError(f"{method}: the agent exited")
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error'].get('message', reply['error'])}")
        return reply.get("result") or {}

    def answer(self, rid, result=None, error: str | None = None) -> None:
        if error:
            self.send({"id": rid, "error": {"code": -32601, "message": error}})
        else:
            self.send({"id": rid, "result": result or {}})

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _read_stdout(self) -> None:
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._on_stderr(line)
                continue
            if "method" in msg and "id" in msg:
                self._on_request(msg)
            elif "method" in msg:
                self._on_notify(msg)
            elif "id" in msg:
                with self._cv:
                    self._pending[msg["id"]] = msg
                    self._cv.notify_all()
        code = self.proc.wait()
        with self._cv:
            self._cv.notify_all()
        self._on_exit(code)

    def _read_stderr(self) -> None:
        for line in self.proc.stderr:
            if line.strip():
                self._on_stderr(line.rstrip())

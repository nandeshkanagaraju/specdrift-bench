"""Runs one solution against one test, in its own process. Not imported; run as a script.

Reads {"code", "test", "func"} as JSON on stdin and prints one JSON line:
{"status": "passed" | "failed" | "no_tests" | "load_error", "error": str, "counterexample": {...} | null}.
It extracts the first assert that fails, as input / expected / actual, so a DRIFT label can
carry a counterexample that was really executed rather than written by a model.
"""

import ast
import json
import os
import resource
import signal
import sys
import tempfile

CALL_SECONDS = 2


class CallTimeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise CallTimeout(f"call exceeded {CALL_SECONDS}s")


def _limit_resources():
    # Best effort: macOS ignores some of these, Linux (Kaggle) honours them.
    for name, value in (("RLIMIT_CPU", 15), ("RLIMIT_FSIZE", 0), ("RLIMIT_NPROC", 0)):
        try:
            resource.setrlimit(getattr(resource, name), (value, value))
        except (ValueError, OSError, AttributeError):
            pass


def _short(value, limit=200):
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _timed(fn, *args, **kwargs):
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(CALL_SECONDS)
    try:
        return fn(*args, **kwargs)
    finally:
        signal.alarm(0)


def _emit(status, error="", counterexample=None):
    print(json.dumps({"status": status, "error": error[:300], "counterexample": counterexample}))


def _eval(node, env):
    return eval(compile(ast.Expression(node), "<test>", "eval"), env)


def _shown(call, name):
    """Show the call under the real function's name, not the test's parameter name."""
    renamed = ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=call.args, keywords=call.keywords)
    return ast.unparse(renamed)


def _first_failing_assert(check_def, env, param, func, name):
    for stmt in check_def.body:
        if not isinstance(stmt, ast.Assert):
            continue
        test = stmt.test
        simple = (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], (ast.Eq, ast.NotEq, ast.Is, ast.IsNot))
            and isinstance(test.left, ast.Call)
            and isinstance(test.left.func, ast.Name)
            and test.left.func.id == param
        )
        try:
            if simple:
                call = test.left
                args = [_eval(a, env) for a in call.args]
                kwargs = {k.arg: _eval(k.value, env) for k in call.keywords if k.arg}
                expected = _eval(test.comparators[0], env)
                try:
                    actual = _timed(func, *args, **kwargs)
                except BaseException as exc:
                    return {
                        "input": _shown(call, name),
                        "expected": _short(expected),
                        "actual": f"raises {type(exc).__name__}: {str(exc)[:80]}",
                    }
                same = actual == expected if isinstance(test.ops[0], (ast.Eq, ast.Is)) else actual != expected
                if not same:
                    return {"input": _shown(call, name), "expected": _short(expected), "actual": _short(actual)}
            else:
                _timed(exec, compile(ast.Module([stmt], []), "<assert>", "exec"), dict(env))
        except AssertionError:
            return {"input": ast.unparse(test)[:200], "expected": "assertion holds", "actual": "assertion fails"}
        except BaseException:
            continue
    return None


def main():
    job = json.loads(sys.stdin.read())
    os.chdir(tempfile.mkdtemp(prefix="specdrift-exec-"))
    _limit_resources()

    ns = {"__name__": "solution"}
    try:
        exec(compile(job["code"], "solution.py", "exec"), ns)
        func = ns[job["func"]]
    except BaseException as exc:
        return _emit("load_error", f"{type(exc).__name__}: {exc}")

    tree = ast.parse(job["test"])
    # Drop top-level calls such as `check(f)`; the call is made here, under a timer.
    tree.body = [n for n in tree.body if not isinstance(n, ast.Expr)]
    check_def = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check"), None)
    if check_def is None:
        return _emit("no_tests", "no check function")
    body = [n for n in check_def.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    if all(isinstance(n, ast.Pass) for n in body):
        return _emit("no_tests", "check() is empty")

    tns = {"__name__": "tests"}
    exec(compile(tree, "test.py", "exec"), tns)
    try:
        _timed(tns["check"], func)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {str(exc)[:100]}"
        param = check_def.args.args[0].arg if check_def.args.args else "candidate"
        env = dict(tns)
        env[param] = func
        example = _first_failing_assert(check_def, env, param, func, job["func"])
        return _emit("failed", error, example)
    return _emit("passed")


main()

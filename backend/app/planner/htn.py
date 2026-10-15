"""A generic, domain-independent HTN planner (total-order, SHOP-style).

Vocabulary
----------
* A *task* is a name plus arguments, e.g. ``Task("visit", ("amber_fort",))``.
* A *primitive* task is executed by an *operator*: a function
  ``operator(state, *args) -> Applied | Failure``. It checks its
  preconditions against the state and, if they hold, returns the new state
  (the effects) and an optional schedule item. States are never mutated, so
  backtracking only needs to discard the new state.
* A *compound* task is refined by *methods*: a function
  ``methods(state, *args)`` that yields ``(method_name, [subtasks])``
  alternatives in order of preference. Each alternative is one way of
  decomposing the task; its applicability conditions are the checks done
  before yielding.

Search
------
``seek`` keeps an agenda (ordered list of tasks still to do). It repeatedly
takes the first task:

* primitive -> apply the operator; if a precondition fails, this branch is dead;
* compound  -> try each method in turn, replacing the task with the method's
  subtasks. If the rest of the agenda cannot be completed, undo (simply
  forget the new agenda) and try the next method. This is depth-first
  search with chronological backtracking through the space of
  decompositions; together with the state carried along it is also a
  forward state-space search.

A node limit keeps the worst case bounded and is reported to the user.
"""

from __future__ import annotations

import itertools
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator


@dataclass(frozen=True)
class Task:
    name: str
    args: tuple[Any, ...] = ()

    def __str__(self) -> str:
        return f"{self.name}({', '.join(str(a) for a in self.args)})"


@dataclass(frozen=True)
class Applied:
    """Result of a primitive whose preconditions held."""
    state: Any
    item: Any = None


@dataclass(frozen=True)
class Failure:
    """Result of a primitive whose preconditions failed (kept for explanations)."""
    reason: str
    subject: str | None = None     # e.g. the attraction id the failure is about


Operator = Callable[..., "Applied | Failure"]
MethodGenerator = Callable[..., Iterable[tuple[str, list[Task]]]]


class SearchLimitReached(Exception):
    pass


@dataclass
class SearchStats:
    nodes_expanded: int = 0
    backtracks: int = 0
    primitive_failures: int = 0
    elapsed_ms: float = 0.0
    failures: Counter = field(default_factory=Counter)    # (subject, reason) -> count

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes_expanded": self.nodes_expanded,
            "backtracks": self.backtracks,
            "primitive_failures": self.primitive_failures,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


# Decomposition log entries are kept in an immutable linked list:
# (entry, previous_log). Prepending is O(1) and backtracking needs no undo.
LogEntry = tuple[int, int | None, str, str | None]   # (node_id, parent_id, task, method)


@dataclass
class PlanResult:
    state: Any
    items: list[Any]
    tree: dict[str, Any]


class HTNPlanner:
    def __init__(self, operators: dict[str, Operator], methods: dict[str, MethodGenerator],
                 node_limit: int = 30000) -> None:
        self.operators = operators
        self.methods = methods
        self.node_limit = node_limit
        self.stats = SearchStats()
        self._ids = itertools.count(1)

    def plan(self, state: Any, root: Task) -> PlanResult | None:
        """Decompose ``root`` into primitives. Returns None when no plan exists."""
        started = time.perf_counter()
        root_id = next(self._ids)
        log = ((root_id, None, str(root), None), None)
        try:
            found = self._seek(state, ((root, root_id),), log, ())
        finally:
            self.stats.elapsed_ms = (time.perf_counter() - started) * 1000
        if found is None:
            return None
        final_state, final_log, items = found
        return PlanResult(final_state, list(items), self._build_tree(final_log))

    def _seek(self, state: Any, agenda: tuple[tuple[Task, int], ...], log: Any,
              items: tuple[Any, ...]) -> tuple[Any, Any, tuple[Any, ...]] | None:
        if not agenda:
            return state, log, items
        self.stats.nodes_expanded += 1
        if self.stats.nodes_expanded > self.node_limit:
            raise SearchLimitReached()

        (task, node_id), rest = agenda[0], agenda[1:]

        if task.name in self.operators:
            outcome = self.operators[task.name](state, *task.args)
            if isinstance(outcome, Failure):
                self.stats.primitive_failures += 1
                self.stats.failures[(outcome.subject, outcome.reason)] += 1
                return None
            new_items = items + ((outcome.item,) if outcome.item is not None else ())
            return self._seek(outcome.state, rest, log, new_items)

        if task.name not in self.methods:
            raise KeyError(f"No operator or method for task {task.name}")

        tried_any = False
        for method_name, subtasks in self.methods[task.name](state, *task.args):
            if tried_any:
                self.stats.backtracks += 1
            tried_any = True
            # Record "task was refined by method", then one node per subtask.
            new_log = ((node_id, None, "", method_name), log)
            children: list[tuple[Task, int]] = []
            for subtask in subtasks:
                child_id = next(self._ids)
                new_log = ((child_id, node_id, str(subtask), None), new_log)
                children.append((subtask, child_id))
            found = self._seek(state, tuple(children) + rest, new_log, items)
            if found is not None:
                return found
        return None

    @staticmethod
    def _iterate_log(log: Any) -> Iterator[LogEntry]:
        entries: list[LogEntry] = []
        while log is not None:
            entry, log = log
            entries.append(entry)
        return reversed(entries)

    def _build_tree(self, log: Any) -> dict[str, Any]:
        """Turn the decomposition log of the successful branch into a nested tree."""
        nodes: dict[int, dict[str, Any]] = {}
        root: dict[str, Any] | None = None
        for node_id, parent_id, label, method in self._iterate_log(log):
            if method is not None:
                nodes[node_id]["method"] = method
                continue
            node = {"task": label, "method": None,
                    "primitive": label.split("(")[0] in self.operators, "children": []}
            nodes[node_id] = node
            if parent_id is None:
                root = node
            else:
                nodes[parent_id]["children"].append(node)
        assert root is not None
        return root

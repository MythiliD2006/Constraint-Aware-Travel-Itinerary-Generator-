"""A small first-order logic engine: unification + SLD resolution.

Supported subset (deliberately small so it can be explained and tested):

* Datalog-style terms: a term is either a constant (``"amber_fort"``) or a
  variable written with a leading ``?`` (``"?X"``). There are no function
  symbols, so unification never builds nested terms and needs no occurs check.
* Atoms are tuples ``(predicate, term, term, ...)``.
* Definite (Horn) clauses ``head :- body1, body2, ...``. Facts are clauses
  with an empty body.

Resolution
----------
To prove a goal G we conceptually add its negation ``not G`` to the knowledge
base and try to derive the empty clause (refutation). For Horn clauses this is
done by SLD resolution: repeatedly take the left-most goal, resolve it with a
clause whose head unifies with it, and replace the goal with that clause's
body (after renaming the clause's variables apart). When no goals remain the
empty clause has been derived, and the accumulated substitution is an answer.

Search is depth-first with chronological backtracking, like Prolog. The
rules below are written with the base case first and recursion on the right,
and the ISA hierarchy is acyclic, so every query terminates.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import Iterator

Atom = tuple[str, ...]
Substitution = dict[str, str]


def is_variable(term: str) -> bool:
    return term.startswith("?")


@dataclass(frozen=True)
class Clause:
    head: Atom
    body: tuple[Atom, ...] = ()

    def __str__(self) -> str:
        head = format_atom(self.head)
        if not self.body:
            return f"{head}."
        return f"{head} :- {', '.join(format_atom(a) for a in self.body)}."


# Rules shared by every destination. Facts come from KnowledgeBase.facts_for().
RULES: list[Clause] = [
    # subclass_of is the transitive closure of isa.
    Clause(("subclass_of", "?C", "?D"), (("isa", "?C", "?D"),)),
    Clause(("subclass_of", "?C", "?E"), (("isa", "?C", "?D"), ("subclass_of", "?D", "?E"))),
    # An instance is a member of its own class and of every superclass.
    Clause(("member_of", "?I", "?C"), (("instance_of", "?I", "?C"),)),
    Clause(("member_of", "?I", "?D"), (("instance_of", "?I", "?C"), ("subclass_of", "?C", "?D"))),
    # Property inheritance for interests: from the instance itself or any class it belongs to.
    Clause(("appeals_to", "?I", "?T"), (("has_interest", "?I", "?T"),)),
    Clause(("appeals_to", "?I", "?T"), (("member_of", "?I", "?C"), ("has_interest", "?C", "?T"))),
    # A candidate stop for a traveller interested in ?T visiting ?City on ?Day.
    Clause(("candidate", "?I", "?T", "?City", "?Day"),
           (("located_in", "?I", "?City"), ("appeals_to", "?I", "?T"), ("open_on", "?I", "?Day"))),
]


def format_atom(atom: Atom) -> str:
    return f"{atom[0]}({', '.join(atom[1:])})"


# ---------------------------------------------------------------------------
# Unification
# ---------------------------------------------------------------------------
def walk(term: str, theta: Substitution) -> str:
    """Follow variable bindings until reaching a constant or unbound variable."""
    while is_variable(term) and term in theta:
        term = theta[term]
    return term


def unify(a: Atom, b: Atom, theta: Substitution | None = None) -> Substitution | None:
    """Most general unifier of two atoms extending ``theta``, or None.

    >>> unify(("isa", "?X", "Fort"), ("isa", "Palace", "?Y"))
    {'?X': 'Palace', '?Y': 'Fort'}
    """
    theta = dict(theta or {})
    if a[0] != b[0] or len(a) != len(b):
        return None
    for left, right in zip(a[1:], b[1:]):
        left, right = walk(left, theta), walk(right, theta)
        if left == right:
            continue
        if is_variable(left):
            theta[left] = right
        elif is_variable(right):
            theta[right] = left
        else:
            return None  # two different constants
    return theta


def substitute(atom: Atom, theta: Substitution) -> Atom:
    return (atom[0],) + tuple(walk(t, theta) for t in atom[1:])


# ---------------------------------------------------------------------------
# SLD resolution
# ---------------------------------------------------------------------------
@dataclass
class ProofStep:
    depth: int
    goal: str
    clause: str


class LogicEngine:
    def __init__(self, facts: list[Atom], rules: list[Clause] | None = None,
                 max_depth: int = 40) -> None:
        self.clauses: list[Clause] = [Clause(f) for f in facts] + list(rules or RULES)
        # Index clauses by predicate name so each goal only scans relevant clauses.
        self.by_predicate: dict[str, list[Clause]] = {}
        for clause in self.clauses:
            self.by_predicate.setdefault(clause.head[0], []).append(clause)
        self.max_depth = max_depth
        self._fresh = itertools.count()
        self.inferences = 0

    def _rename(self, clause: Clause) -> Clause:
        """Standardise apart: give the clause's variables fresh names."""
        suffix = f"_{next(self._fresh)}"
        def rename(atom: Atom) -> Atom:
            return (atom[0],) + tuple(t + suffix if is_variable(t) else t for t in atom[1:])
        return Clause(rename(clause.head), tuple(rename(a) for a in clause.body))

    def _solve(self, goals: tuple[Atom, ...], theta: Substitution, depth: int,
               trace: list[ProofStep]) -> Iterator[tuple[Substitution, list[ProofStep]]]:
        if not goals:
            yield theta, trace      # empty clause derived: refutation complete
            return
        if depth > self.max_depth:
            return
        goal, rest = goals[0], goals[1:]
        for clause in self.by_predicate.get(goal[0], []):
            renamed = self._rename(clause)
            unifier = unify(goal, renamed.head, theta)
            if unifier is None:
                continue
            self.inferences += 1
            step = ProofStep(depth, format_atom(substitute(goal, unifier)), str(clause))
            yield from self._solve(renamed.body + rest, unifier, depth + 1, trace + [step])

    def ask(self, goals: list[Atom], limit: int = 200) -> list[dict]:
        """All distinct answers (bindings of the query's variables), with a proof for each."""
        query_vars = sorted({t for g in goals for t in g[1:] if is_variable(t)})
        answers: list[dict] = []
        seen: set[tuple[str, ...]] = set()
        for theta, trace in self._solve(tuple(goals), {}, 0, []):
            binding = {v: walk(v, theta) for v in query_vars}
            key = tuple(binding[v] for v in query_vars)
            if key in seen:
                continue
            seen.add(key)
            answers.append({"bindings": binding,
                            "proof": [step.__dict__ for step in trace]})
            if len(answers) >= limit:
                break
        return answers

    def holds(self, goal: Atom) -> bool:
        return next(self._solve((goal,), {}, 0, []), None) is not None


# ---------------------------------------------------------------------------
# Parsing queries like  "appeals_to(?X, history), located_in(?X, jaipur)"
# ---------------------------------------------------------------------------
_ATOM_RE = re.compile(r"\s*([a-z_][a-z0-9_]*)\s*\(([^()]*)\)\s*")
_TERM_RE = re.compile(r"^\??[A-Za-z_][A-Za-z0-9_]*$")


def parse_query(text: str) -> list[Atom]:
    text = text.strip().rstrip(".")
    if not text:
        raise ValueError("Query is empty")
    atoms: list[Atom] = []
    position = 0
    while position < len(text):
        match = _ATOM_RE.match(text, position)
        if not match:
            raise ValueError(f"Could not parse query near: {text[position:position + 25]!r}")
        args = [a.strip() for a in match.group(2).split(",")] if match.group(2).strip() else []
        for arg in args:
            if not _TERM_RE.match(arg):
                raise ValueError(f"Bad term {arg!r}: use names like amber_fort or variables like ?X")
        atoms.append((match.group(1), *args))
        position = match.end()
        if position < len(text):
            if text[position] != ",":
                raise ValueError("Separate goals with commas")
            position += 1
    return atoms

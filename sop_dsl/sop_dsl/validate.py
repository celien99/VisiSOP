from collections.abc import Collection
from dataclasses import dataclass

from sop_dsl.schema import (
    EventCondition,
    EventRuleCompletion,
    SOPSpec,
    SOPStepSpec,
    StateRuleCompletion,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    step_key: str | None = None


class DSLValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        codes = ", ".join(sorted({issue.code for issue in issues}))
        super().__init__(f"{len(issues)} validation issue(s): {codes}")


def _event_conditions(step: SOPStepSpec) -> tuple[EventCondition, ...]:
    completion = step.completion
    if isinstance(completion, EventRuleCompletion):
        return (*completion.all, *completion.any, *completion.not_)
    return ()


def _unresolved_cycle_keys(
    steps: tuple[SOPStepSpec, ...], known: set[str]
) -> list[str]:
    dependencies = {
        step.key: {dep for dep in step.depends_on if dep in known and dep != step.key}
        for step in steps
    }
    ready = sorted(key for key, deps in dependencies.items() if not deps)
    processed: list[str] = []
    while ready:
        key = ready.pop(0)
        processed.append(key)
        for other, deps in dependencies.items():
            if key in deps:
                deps.remove(key)
                if not deps:
                    ready.append(other)
        ready.sort()
    return sorted(set(dependencies) - set(processed))


def validate_spec(
    spec: SOPSpec, *, known_event_types: Collection[str] | None = None
) -> None:
    issues: list[ValidationIssue] = []
    steps = spec.steps
    known = {step.key for step in steps}

    duplicates = sorted({key for key in known if sum(s.key == key for s in steps) > 1})
    for key in duplicates:
        issues.append(
            ValidationIssue("DUPLICATE_KEY", f"duplicate step key: {key}", key)
        )

    for step in steps:
        for dep in step.depends_on:
            if dep == step.key:
                issues.append(
                    ValidationIssue(
                        "SELF_DEPENDENCY",
                        f"step {step.key!r} depends on itself",
                        step.key,
                    )
                )
            elif dep not in known:
                issues.append(
                    ValidationIssue(
                        "UNKNOWN_STEP_REF",
                        f"step {step.key!r} depends on unknown step {dep!r}",
                        step.key,
                    )
                )

        policy = step.join_policy
        if policy is not None:
            if not step.depends_on:
                issues.append(
                    ValidationIssue(
                        "JOIN_WITHOUT_DEPENDENCY",
                        f"join step {step.key!r} has no dependencies",
                        step.key,
                    )
                )
            if not isinstance(step.completion, StateRuleCompletion):
                issues.append(
                    ValidationIssue(
                        "JOIN_REQUIRES_STATE_RULE",
                        f"join step {step.key!r} must use a STATE_RULE completion",
                        step.key,
                    )
                )
            if policy.type == "ANY_OF_N" and (
                policy.n is not None and policy.n > len(step.depends_on)
            ):
                issues.append(
                    ValidationIssue(
                        "ANY_OF_N_EXCEEDS_DEPENDENCIES",
                        f"step {step.key!r} requires {policy.n} of "
                        f"{len(step.depends_on)} dependencies",
                        step.key,
                    )
                )

        skip_if = step.skip_if
        if skip_if is not None:
            for ref in skip_if.all_steps_completed:
                if ref not in known:
                    issues.append(
                        ValidationIssue(
                            "UNKNOWN_STEP_REF",
                            f"step {step.key!r} skip_if references unknown step {ref!r}",
                            step.key,
                        )
                    )
            if (
                known_event_types is not None
                and skip_if.event_type is not None
                and skip_if.event_type not in known_event_types
            ):
                issues.append(
                    ValidationIssue(
                        "UNKNOWN_EVENT_TYPE",
                        f"step {step.key!r} skip_if references unregistered event "
                        f"{skip_if.event_type!r}",
                        step.key,
                    )
                )

        failure = step.failure
        if (
            failure is not None
            and known_event_types is not None
            and failure.event_type not in known_event_types
        ):
            issues.append(
                ValidationIssue(
                    "UNKNOWN_EVENT_TYPE",
                    f"step {step.key!r} failure rule references unregistered event "
                    f"{failure.event_type!r}",
                    step.key,
                )
            )

        if known_event_types is not None:
            for condition in _event_conditions(step):
                if condition.event_type not in known_event_types:
                    issues.append(
                        ValidationIssue(
                            "UNKNOWN_EVENT_TYPE",
                            f"step {step.key!r} references unregistered event "
                            f"{condition.event_type!r}",
                            step.key,
                        )
                    )

    cycle_keys = _unresolved_cycle_keys(steps, known)
    if cycle_keys:
        issues.append(
            ValidationIssue(
                "CYCLE",
                f"dependency cycle among steps: {', '.join(cycle_keys)}",
            )
        )

    if not any(not step.depends_on for step in steps):
        issues.append(ValidationIssue("NO_START_STEP", "the SOP has no start step"))

    if issues:
        raise DSLValidationError(issues)

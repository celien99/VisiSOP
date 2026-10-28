from collections.abc import Collection
from hashlib import sha256
from types import MappingProxyType

from sop_dsl.schema import SOPSpec
from sop_dsl.validate import validate_spec

from app.domain.sop.model import CompiledStep, SOPGraph


def _topological_order(spec: SOPSpec) -> tuple[str, ...]:
    dependencies = {step.key: set(step.depends_on) for step in spec.steps}
    ready = sorted(key for key, deps in dependencies.items() if not deps)
    order: list[str] = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for other, deps in dependencies.items():
            if key in deps:
                deps.remove(key)
                if not deps:
                    ready.append(other)
        ready.sort()
    return tuple(order)


def compile_spec(
    spec: SOPSpec, *, known_event_types: Collection[str] | None = None
) -> SOPGraph:
    validate_spec(spec, known_event_types=known_event_types)
    steps = {
        step.key: CompiledStep(
            key=step.key,
            name=step.name,
            type=step.type,
            completion=step.completion,
            required=step.required,
            depends_on=step.depends_on,
            timeout_ms=step.timeout_ms,
            evidence=step.evidence,
            join_policy=step.join_policy,
            skip_if=step.skip_if,
            failure=step.failure,
        )
        for step in spec.steps
    }
    return SOPGraph(
        sop_key=spec.sop_key,
        version=spec.version,
        dsl_schema_version=spec.schema_version,
        content_hash=sha256(spec.model_dump_json().encode("utf-8")).hexdigest(),
        steps=MappingProxyType(steps),
        order=_topological_order(spec),
        start_steps=tuple(
            sorted(step.key for step in spec.steps if not step.depends_on)
        ),
    )

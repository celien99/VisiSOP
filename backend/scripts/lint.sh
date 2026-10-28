#!/usr/bin/env bash

set -e
set -x

mypy app ../contracts/contracts ../sop_dsl/sop_dsl
ty check app ../contracts/contracts ../sop_dsl/sop_dsl
ruff check app ../contracts/contracts ../sop_dsl/sop_dsl
ruff format app ../contracts/contracts ../sop_dsl/sop_dsl --check

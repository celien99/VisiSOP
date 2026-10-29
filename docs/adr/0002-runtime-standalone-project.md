# ADR-0002：运行时为独立 uv 项目，共享包下探到 3.12

- **状态**：已接受（实施用）
- **日期**：2026-10-28
- **影响文件**：`contracts/pyproject.toml`、`sop_dsl/pyproject.toml`、`runtime/pyproject.toml`、`docs/implementation/50-video-runtime.md`

## 背景

后端固定在 Python 3.14（FastAPI、SQLModel、mypy/ty 的目标版本）。视频运行时依赖工业相机 SDK（MVS/GenTL）、OpenCV 与 ONNX Runtime，这条工具链目前只在 Python 3.12 上可用。仓库是一个 uv workspace；workspace 共用一份锁文件与一个虚拟环境，无法同时安装“≥3.14”的后端和“<3.13”的运行时。

## 决定

1. `contracts` 与 `sop_dsl` 的 `requires-python` 下探到 `>=3.12`，ruff 目标与 mypy `python_version` 同步为 3.12；后端的 `requires-python` 保持 `>=3.14`。
2. `runtime/` **不是** workspace 成员，而是独立的 uv 项目，拥有自己的 `pyproject.toml` 与 `uv.lock`，通过 path 依赖 `../contracts` 引用事件契约。
3. 运行时在 `runtime/` 目录内 `uv sync`，后端与前端仍在根目录构建。

## 理由

- 一个 workspace 只能有一套可安装的环境；把运行时留在 workspace 会让 `uv sync --all-packages` 无解，或迫使后端降级。
- path 依赖让契约改动无需发布即可被运行时消费，同时保留版本化与各自的锁文件。
- 共享包只用 StrEnum、Pydantic 与标准库，3.12 与 3.14 行为一致；把 lint/type 目标钉在 3.12 保证不会写出运行时导入不了的语法。

## 什么会改变这个决定

- uv 支持同一 workspace 内按成员划分不重叠的 Python 区间并生成多环境锁文件；
- 相机 SDK 与推理运行时支持 Python 3.14，使整个仓库回到单一版本；
- 契约需要 3.13+ 的语法或库特性，此时必须升级运行时基础镜像而不是共享包。

## 后果

- 两个环境、两份锁文件；CI 必须分别执行 `uv sync --all-packages`（根目录）与 `cd runtime && uv sync`。
- 运行时只能依赖 `contracts`（必要时 `sop_dsl`），不得导入后端 ORM、`app.*` 或数据库驱动。

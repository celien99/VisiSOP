import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useState } from "react"
import { toast } from "sonner"
import type { ProjectRead } from "@/client"
import { TrainingService } from "@/client"
import { apiUrl } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import { Labeler } from "./Labeler"

const JOB_LABEL: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "训练中",
  SUCCEEDED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
}

function messageOf(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)
      ?.detail
    if (typeof detail === "string") {
      return detail
    }
  }
  return error instanceof Error ? error.message : "请求失败"
}

export function TrainingPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [key, setKey] = useState("")
  const [name, setName] = useState("")
  const [classes, setClasses] = useState(
    "remote,battery,CORRECT,REVERSED,OPEN,CLOSED,hand",
  )

  const projectsQuery = useQuery({
    queryKey: queryKeys.trainingProjects,
    queryFn: async () => {
      const response = await TrainingService.listTrainingProjects()
      return response.data
    },
  })
  const projects = projectsQuery.data ?? []
  const projectId = selectedId ?? projects[0]?.id ?? null
  const project = projects.find((item) => item.id === projectId) ?? null

  const createProject = useMutation({
    mutationFn: async () => {
      const response = await TrainingService.createTrainingProject({
        body: {
          key,
          name,
          classes: classes
            .split(",")
            .map((entry) => entry.trim())
            .filter(Boolean),
        },
      })
      return response.data
    },
    onSuccess: (created) => {
      setSelectedId(created.id)
      setKey("")
      setName("")
      toast.success("训练项目已创建")
      queryClient.invalidateQueries({ queryKey: queryKeys.trainingProjects })
    },
    onError: (error) => toast.error(messageOf(error)),
  })

  return (
    <div className="vs-training">
      <aside className="vs-training__projects">
        <h1 className="vs-training__title">训练</h1>
        <p className="vs-panel__hint">录视频 → 抽帧 → 画框 → 训练 → 激活</p>
        <form
          className="vs-training__create"
          onSubmit={(event) => {
            event.preventDefault()
            createProject.mutate()
          }}
        >
          <label className="vs-field">
            <span className="vs-field__label">项目标识</span>
            <input
              className="vs-input"
              onChange={(event) => setKey(event.target.value)}
              placeholder="remote_battery"
              value={key}
            />
          </label>
          <label className="vs-field">
            <span className="vs-field__label">名称</span>
            <input
              className="vs-input"
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <label className="vs-field">
            <span className="vs-field__label">类别（逗号分隔）</span>
            <input
              className="vs-input"
              onChange={(event) => setClasses(event.target.value)}
              value={classes}
            />
          </label>
          <button
            className="vs-action vs-focus"
            disabled={createProject.isPending || !key || !name}
            type="submit"
          >
            新建项目
          </button>
        </form>
        <ul className="vs-training__list">
          {projects.map((item) => (
            <li key={item.id}>
              <button
                className="vs-training__project"
                data-active={item.id === projectId || undefined}
                onClick={() => setSelectedId(item.id)}
                type="button"
              >
                <span className="vs-row__main">{item.name}</span>
                <span className="vs-row__meta">{item.key}</span>
              </button>
            </li>
          ))}
          {projects.length === 0 ? (
            <li className="vs-empty">还没有项目</li>
          ) : null}
        </ul>
      </aside>
      <main className="vs-training__workspace">
        {project ? (
          <ProjectWorkspace key={project.id} project={project} />
        ) : (
          <p className="vs-empty">创建或选择一个训练项目</p>
        )}
      </main>
    </div>
  )
}

function ProjectWorkspace({ project }: { project: ProjectRead }) {
  const queryClient = useQueryClient()
  const [videoId, setVideoId] = useState<string | null>(null)
  const [frameId, setFrameId] = useState<string | null>(null)
  const [datasetId, setDatasetId] = useState<string | null>(null)
  const [epochs, setEpochs] = useState(50)
  const [operator, setOperator] = useState("")

  const invalidate = (keys: readonly unknown[]) => {
    queryClient.invalidateQueries({ queryKey: keys })
  }

  const videosQuery = useQuery({
    queryKey: queryKeys.trainingVideos(project.id),
    queryFn: async () => {
      const response = await TrainingService.listTrainingVideos({
        path: { project_id: project.id },
      })
      return response.data
    },
  })
  const videos = videosQuery.data ?? []
  const selectedVideoId = videoId ?? videos[0]?.id ?? null

  const framesQuery = useQuery({
    enabled: Boolean(selectedVideoId),
    queryKey: queryKeys.trainingFrames(selectedVideoId ?? ""),
    queryFn: async () => {
      const response = await TrainingService.listTrainingFrames({
        path: { video_id: selectedVideoId ?? "" },
      })
      return response.data
    },
  })
  const frames = framesQuery.data ?? []
  const selectedFrame =
    frames.find((frame) => frame.id === frameId) ?? frames[0] ?? null

  const annotationsQuery = useQuery({
    enabled: Boolean(selectedFrame),
    queryKey: queryKeys.frameAnnotations(selectedFrame?.id ?? ""),
    queryFn: async () => {
      const response = await TrainingService.listFrameAnnotations({
        path: { frame_id: selectedFrame?.id ?? "" },
      })
      return response.data
    },
  })

  const statsQuery = useQuery({
    queryKey: queryKeys.trainingStats(project.id),
    queryFn: async () => {
      const response = await TrainingService.getTrainingStats({
        path: { project_id: project.id },
      })
      return response.data
    },
  })
  const datasetsQuery = useQuery({
    queryKey: queryKeys.trainingDatasets(project.id),
    queryFn: async () => {
      const response = await TrainingService.listTrainingDatasets({
        path: { project_id: project.id },
      })
      return response.data
    },
  })
  const datasets = datasetsQuery.data ?? []
  const effectiveDatasetId = datasetId ?? datasets[0]?.id ?? null

  const jobsQuery = useQuery({
    queryKey: queryKeys.trainingJobs(project.id),
    queryFn: async () => {
      const response = await TrainingService.listTrainingJobs({
        path: { project_id: project.id },
      })
      return response.data
    },
    refetchInterval: (query) => {
      const jobs = query.state.data
      return jobs?.some(
        (job) => job.status === "QUEUED" || job.status === "RUNNING",
      )
        ? 3000
        : false
    },
  })
  const jobs = jobsQuery.data ?? []

  const modelsQuery = useQuery({
    queryKey: queryKeys.trainingModels(project.id),
    queryFn: async () => {
      const response = await TrainingService.listTrainingModels({
        path: { project_id: project.id },
      })
      return response.data
    },
  })
  const models = modelsQuery.data ?? []

  const upload = useMutation({
    mutationFn: async (file: File) =>
      TrainingService.uploadTrainingVideo({
        path: { project_id: project.id },
        body: { file },
      }),
    onSuccess: () => {
      toast.success("视频已上传")
      invalidate(queryKeys.trainingVideos(project.id))
    },
    onError: (error) => toast.error(messageOf(error)),
  })

  const extract = useMutation({
    mutationFn: async (id: string) =>
      TrainingService.extractTrainingVideo({
        path: { video_id: id },
        body: { fps: 1, max_frames: 500 },
      }),
    onSuccess: () => {
      toast.success("抽帧完成")
      invalidate(queryKeys.trainingVideos(project.id))
      invalidate(queryKeys.trainingFrames(selectedVideoId ?? ""))
      invalidate(queryKeys.trainingStats(project.id))
    },
    onError: (error) => toast.error(messageOf(error)),
  })

  const createDataset = useMutation({
    mutationFn: async () =>
      TrainingService.createTrainingDataset({
        path: { project_id: project.id },
        body: { val_ratio: 0.2 },
      }),
    onSuccess: () => {
      toast.success("数据集已生成")
      invalidate(queryKeys.trainingDatasets(project.id))
    },
    onError: (error) => toast.error(messageOf(error)),
  })

  const startJob = useMutation({
    mutationFn: async (id: string) =>
      TrainingService.createTrainingJob({
        path: { project_id: project.id },
        body: { dataset_version_id: id, epochs },
      }),
    onSuccess: () => {
      toast.success("训练任务已排队")
      invalidate(queryKeys.trainingJobs(project.id))
    },
    onError: (error) => toast.error(messageOf(error)),
  })

  const activate = useMutation({
    mutationFn: async (id: string) =>
      TrainingService.activateTrainingModel({
        path: { model_id: id },
        body: { operator },
      }),
    onSuccess: () => {
      toast.success("模型已激活")
      invalidate(queryKeys.trainingModels(project.id))
    },
    onError: (error) => toast.error(messageOf(error)),
  })

  const frameIndex = selectedFrame
    ? frames.findIndex((frame) => frame.id === selectedFrame.id)
    : -1
  const moveFrame = (offset: number) => {
    const next = frames[frameIndex + offset]
    if (next) {
      setFrameId(next.id)
    }
  }

  return (
    <div className="vs-training__sections">
      <section className="vs-training__section">
        <h2 className="vs-panel__title">视频与帧</h2>
        <div className="vs-training__toolbar">
          <label className="vs-action vs-focus vs-training__upload">
            上传视频
            <input
              accept="video/*"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  upload.mutate(file)
                }
                event.target.value = ""
              }}
              type="file"
            />
          </label>
          {statsQuery.data ? (
            <span className="vs-row__meta">
              视频 {statsQuery.data.videos} · 帧 {statsQuery.data.frames} ·
              已标注 {statsQuery.data.labeled_frames}
            </span>
          ) : null}
        </div>
        <ul className="vs-rows">
          {videos.map((video) => (
            <li className="vs-row" key={video.id}>
              <button
                className="vs-training__video"
                data-active={video.id === selectedVideoId || undefined}
                onClick={() => {
                  setVideoId(video.id)
                  setFrameId(null)
                }}
                type="button"
              >
                <span className="vs-row__main">{video.filename}</span>
                <span className="vs-row__meta">
                  {video.status} · {video.frame_count} 帧
                  {video.error ? ` · ${video.error}` : ""}
                </span>
              </button>
              <button
                className="vs-action vs-focus"
                disabled={video.frame_count > 0 || extract.isPending}
                onClick={() => extract.mutate(video.id)}
                type="button"
              >
                抽帧
              </button>
            </li>
          ))}
          {videos.length === 0 ? <li className="vs-empty">暂无视频</li> : null}
        </ul>
        <div className="vs-frame-grid">
          {frames.map((frame) => (
            <button
              className="vs-frame"
              data-selected={frame.id === selectedFrame?.id || undefined}
              key={frame.id}
              onClick={() => setFrameId(frame.id)}
              type="button"
            >
              <img
                alt={`帧 ${frame.frame_index}`}
                src={apiUrl(frame.thumb_url)}
              />
              <span>
                {frame.annotation_count > 0
                  ? `已标注 ${frame.annotation_count}`
                  : "未标注"}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="vs-training__section">
        <h2 className="vs-panel__title">标注</h2>
        {selectedFrame ? (
          annotationsQuery.isLoading ? (
            <p className="vs-empty">加载标注…</p>
          ) : annotationsQuery.data ? (
            <Labeler
              annotations={annotationsQuery.data}
              classes={project.classes}
              frameId={selectedFrame.id}
              imageUrl={apiUrl(selectedFrame.image_url)}
              key={selectedFrame.id}
              onNext={
                frameIndex < frames.length - 1 ? () => moveFrame(1) : undefined
              }
              onPrev={frameIndex > 0 ? () => moveFrame(-1) : undefined}
              onSaved={() => {
                invalidate(queryKeys.frameAnnotations(selectedFrame.id))
                invalidate(queryKeys.trainingFrames(selectedVideoId ?? ""))
                invalidate(queryKeys.trainingStats(project.id))
              }}
            />
          ) : (
            <p className="vs-empty">无法加载标注</p>
          )
        ) : (
          <p className="vs-empty">选择一帧开始标注</p>
        )}
      </section>

      <section className="vs-training__section">
        <h2 className="vs-panel__title">数据集与训练</h2>
        <div className="vs-training__toolbar">
          <button
            className="vs-action vs-focus"
            disabled={createDataset.isPending}
            onClick={() => createDataset.mutate()}
            type="button"
          >
            生成数据集
          </button>
          <select
            className="vs-select"
            onChange={(event) => setDatasetId(event.target.value)}
            value={effectiveDatasetId ?? ""}
          >
            <option value="">选择数据集</option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                v{dataset.version} · {dataset.frame_count} 帧
              </option>
            ))}
          </select>
          <label className="vs-field">
            <span className="vs-field__label">轮数</span>
            <input
              className="vs-input vs-input--compact"
              min={1}
              onChange={(event) => setEpochs(Number(event.target.value))}
              type="number"
              value={epochs}
            />
          </label>
          <button
            className="vs-action vs-focus"
            disabled={!effectiveDatasetId || startJob.isPending}
            onClick={() =>
              effectiveDatasetId && startJob.mutate(effectiveDatasetId)
            }
            type="button"
          >
            开始训练
          </button>
        </div>
        <ul className="vs-rows">
          {jobs.map((job) => (
            <li className="vs-row" key={job.id}>
              <span className="vs-row__main">
                {JOB_LABEL[job.status] ?? job.status} · {job.progress}%
              </span>
              <span className="vs-row__meta">
                {job.epochs} 轮{job.error ? ` · ${job.error}` : ""}
              </span>
              <div className="vs-progress">
                <span style={{ width: `${job.progress}%` }} />
              </div>
            </li>
          ))}
          {jobs.length === 0 ? (
            <li className="vs-empty">暂无训练任务</li>
          ) : null}
        </ul>
      </section>

      <section className="vs-training__section">
        <h2 className="vs-panel__title">模型</h2>
        <div className="vs-training__toolbar">
          <label className="vs-field">
            <span className="vs-field__label">激活操作者</span>
            <input
              className="vs-input"
              onChange={(event) => setOperator(event.target.value)}
              placeholder="输入姓名后激活"
              value={operator}
            />
          </label>
        </div>
        <ul className="vs-rows">
          {models.map((model) => (
            <li className="vs-row" key={model.id}>
              <span className="vs-row__main">
                v{model.version} {model.active ? "· 已激活" : ""}
              </span>
              <span className="vs-row__meta">
                mAP50 {Number(model.metrics.mAP50 ?? 0).toFixed(3)} ·{" "}
                <a href={apiUrl(model.artifact_url)}>ONNX</a>
              </span>
              <button
                className="vs-action vs-focus"
                disabled={!operator || model.active || activate.isPending}
                onClick={() => activate.mutate(model.id)}
                type="button"
              >
                激活
              </button>
            </li>
          ))}
          {models.length === 0 ? <li className="vs-empty">暂无模型</li> : null}
        </ul>
      </section>
    </div>
  )
}

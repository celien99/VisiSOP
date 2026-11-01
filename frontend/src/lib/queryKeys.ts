export const queryKeys = {
  stationRuntimeStates: ["station-runtime-states"] as const,
  stationRuntimeState: (stationId: string) =>
    ["station-runtime-state", stationId] as const,
  execution: (executionId: string) => ["execution", executionId] as const,
  executionTimeline: (executionId: string) =>
    ["execution-timeline", executionId] as const,
  executions: (filters: string) => ["executions", filters] as const,
  alarms: (filters: string) => ["alarms", filters] as const,
  sops: ["sops"] as const,
  sop: (sopId: string) => ["sop", sopId] as const,
  health: ["health"] as const,
  trainingProjects: ["training-projects"] as const,
  trainingVideos: (projectId: string) =>
    ["training-videos", projectId] as const,
  trainingFrames: (videoId: string) => ["training-frames", videoId] as const,
  frameAnnotations: (frameId: string) =>
    ["training-annotations", frameId] as const,
  trainingStats: (projectId: string) => ["training-stats", projectId] as const,
  trainingDatasets: (projectId: string) =>
    ["training-datasets", projectId] as const,
  trainingJobs: (projectId: string) => ["training-jobs", projectId] as const,
  trainingModels: (projectId: string) =>
    ["training-models", projectId] as const,
}

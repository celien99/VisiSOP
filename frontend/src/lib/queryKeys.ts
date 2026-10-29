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
}

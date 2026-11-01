import { createFileRoute } from "@tanstack/react-router"
import { TrainingPage } from "@/features/training/TrainingPage"

export const Route = createFileRoute("/_layout/training")({
  component: TrainingPage,
  head: () => ({ meta: [{ title: "训练 — VisiSOP" }] }),
})

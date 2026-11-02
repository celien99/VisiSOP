import { useMutation } from "@tanstack/react-query"
import type { PointerEvent } from "react"
import { useRef, useState } from "react"
import { toast } from "sonner"
import type { AnnotationInput } from "@/client"
import { TrainingService } from "@/client"

type Point = { x: number; y: number }

type LabelerProps = {
  frameId: string
  imageUrl: string
  classes: string[]
  annotations: AnnotationInput[]
  onSaved: () => void
  onPrev?: () => void
  onNext?: () => void
}

const clamp = (value: number) => Math.min(1, Math.max(0, value))

function boxFrom(start: Point, end: Point, className: string): AnnotationInput {
  return {
    class_name: className,
    x1: Math.min(start.x, end.x),
    y1: Math.min(start.y, end.y),
    x2: Math.max(start.x, end.x),
    y2: Math.max(start.y, end.y),
  }
}

export function Labeler({
  frameId,
  imageUrl,
  classes,
  annotations,
  onSaved,
  onPrev,
  onNext,
}: LabelerProps) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const [boxes, setBoxes] = useState<AnnotationInput[]>(() =>
    annotations.map((box) => ({ ...box })),
  )
  const [draft, setDraft] = useState<AnnotationInput | null>(null)
  const [className, setClassName] = useState(classes[0] ?? "")
  const [start, setStart] = useState<Point | null>(null)

  const save = useMutation({
    mutationFn: async () =>
      TrainingService.replaceFrameAnnotations({
        path: { frame_id: frameId },
        body: { annotations: boxes },
      }),
    onSuccess: () => {
      toast.success("标注已保存")
      onSaved()
    },
    onError: () => toast.error("保存标注失败"),
  })

  function point(event: PointerEvent<HTMLDivElement>): Point {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) {
      return { x: 0, y: 0 }
    }
    return {
      x: clamp((event.clientX - rect.left) / rect.width),
      y: clamp((event.clientY - rect.top) / rect.height),
    }
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || !className) {
      return
    }
    const origin = point(event)
    setStart(origin)
    setDraft(boxFrom(origin, origin, className))
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!start) {
      return
    }
    setDraft(boxFrom(start, point(event), className))
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if (!start || !draft) {
      setStart(null)
      setDraft(null)
      return
    }
    const box = boxFrom(start, point(event), className)
    setStart(null)
    setDraft(null)
    if (box.x2 - box.x1 >= 0.005 && box.y2 - box.y1 >= 0.005) {
      setBoxes((current) => [...current, box])
    }
  }

  return (
    <div className="vs-labeler">
      <div className="vs-labeler__toolbar">
        <div className="vs-field">
          <span className="vs-field__label">类别</span>
          <select
            className="vs-select"
            onChange={(event) => setClassName(event.target.value)}
            value={className}
          >
            {classes.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <button
          className="vs-action vs-focus"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          type="button"
        >
          保存标注
        </button>
        <button className="vs-action vs-focus" onClick={onPrev} type="button">
          上一张
        </button>
        <button className="vs-action vs-focus" onClick={onNext} type="button">
          下一张
        </button>
      </div>
      <div
        className="vs-labeler__canvas"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        ref={canvasRef}
      >
        <img alt="标注帧" draggable={false} src={imageUrl} />
        <svg preserveAspectRatio="none" viewBox="0 0 1 1">
          <title>标注区域</title>
          {[...boxes, ...(draft ? [draft] : [])].map((box, index) => (
            <g key={`${box.class_name}-${index}`}>
              <rect
                height={box.y2 - box.y1}
                vectorEffect="non-scaling-stroke"
                width={box.x2 - box.x1}
                x={box.x1}
                y={box.y1}
              />
              <text
                fontSize={0.035}
                x={box.x1 + 0.005}
                y={Math.max(0.04, box.y1 - 0.01)}
              >
                {box.class_name}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <ul className="vs-boxes">
        {boxes.map((box, index) => (
          <li key={`${box.class_name}-${index}`}>
            <span>
              {box.class_name} · x {box.x1.toFixed(2)}–{box.x2.toFixed(2)} · y{" "}
              {box.y1.toFixed(2)}–{box.y2.toFixed(2)}
            </span>
            <button
              className="vs-action vs-focus"
              onClick={() =>
                setBoxes((current) =>
                  current.filter((_, position) => position !== index),
                )
              }
              type="button"
            >
              删除
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

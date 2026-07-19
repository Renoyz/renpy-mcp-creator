export type FreezeAutoGenerationStep =
  | "freezing"
  | "scene_packages"
  | "prototype"
  | "activating"
  | "complete"

export type FreezeAutoGenerationEvent = {
  status: "running" | "success"
  step: FreezeAutoGenerationStep
  message: string
}

type ResponseLike = {
  ok: boolean
  status: number
  json: () => Promise<any>
}

interface RunFreezeAutoGenerationChainArgs {
  projectName: string
  freezeBlueprint: (projectName: string) => Promise<void>
  refreshProjectData: (projectName: string) => Promise<void>
  request: (url: string, init: { method: string; headers: Record<string, string> }) => Promise<ResponseLike>
  onProgress?: (event: FreezeAutoGenerationEvent) => void
}

async function parseErrorDetail(resp: ResponseLike, fallback: string): Promise<string> {
  const body = await resp.json().catch(() => ({}))
  if (body && typeof body.detail === "string" && body.detail.trim()) {
    return body.detail
  }
  if (body && typeof body.error === "string" && body.error.trim()) {
    return body.error
  }
  return fallback
}

const SCENE_PACKAGE_WALL_CLOCK_LIMIT_MS = 15 * 60 * 1000

export async function runFreezeAutoGenerationChain({
  projectName,
  freezeBlueprint,
  refreshProjectData,
  request,
  onProgress,
}: RunFreezeAutoGenerationChainArgs): Promise<void> {
  onProgress?.({
    status: "running",
    step: "freezing",
    message: "正在冻结蓝图...",
  })
  await freezeBlueprint(projectName)
  await refreshProjectData(projectName)

  onProgress?.({
    status: "running",
    step: "scene_packages",
    message: "正在根据冻结蓝图生成场景包...",
  })
  const scenePhaseStartedAt = Date.now()
  let sceneAttempts = 0
  while (true) {
    sceneAttempts += 1
    const sceneResp = await request(`/api/projects/${encodeURIComponent(projectName)}/scene-packages/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    if (!sceneResp.ok) {
      const detail = await parseErrorDetail(sceneResp, `HTTP ${sceneResp.status}`)
      throw new Error(`场景包生成失败：${detail}`)
    }
    const sceneBody = await sceneResp.json().catch(() => ({}))
    await refreshProjectData(projectName)
    const sceneGeneration = sceneBody?.scene_generation
    const completed = Number(sceneGeneration?.completed_count ?? 0)
    const total = Number(sceneGeneration?.total_count ?? 0)
    const maxSceneAttempts = Math.max(12, (Number.isFinite(total) ? total : 0) * 3)
    if (total > 0) {
      onProgress?.({
        status: "running",
        step: "scene_packages",
        message: `正在根据冻结蓝图生成场景包... 已完成 ${completed}/${total} 章`,
      })
    }
    const explicitComplete = sceneBody?.complete === true || sceneGeneration?.status === "complete"
    const legacyComplete = sceneBody?.complete === undefined && sceneGeneration === undefined
    if (explicitComplete || legacyComplete) {
      break
    }
    if (
      sceneAttempts >= maxSceneAttempts ||
      Date.now() - scenePhaseStartedAt >= SCENE_PACKAGE_WALL_CLOCK_LIMIT_MS
    ) {
      throw new Error(
        "场景包生成未及时完成，你可以前往“生成”页继续。"
      )
    }
  }

  onProgress?.({
    status: "running",
    step: "prototype",
    message: "正在根据场景包生成原型脚本...",
  })
  const protoResp = await request(`/api/projects/${encodeURIComponent(projectName)}/prototype/multi-chapter/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
  if (!protoResp.ok) {
    const detail = await parseErrorDetail(protoResp, `HTTP ${protoResp.status}`)
    throw new Error(`原型生成失败：${detail}`)
  }
  await refreshProjectData(projectName)

  onProgress?.({
    status: "running",
    step: "activating",
    message: "正在激活生成的原型以用于构建和预览...",
  })
  const activateResp = await request(`/api/projects/${encodeURIComponent(projectName)}/prototype/multi-chapter/activate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
  if (!activateResp.ok) {
    const detail = await parseErrorDetail(activateResp, `HTTP ${activateResp.status}`)
    throw new Error(`原型激活失败：${detail}`)
  }
  await refreshProjectData(projectName)

  onProgress?.({
    status: "success",
    step: "complete",
    message: "场景包与原型脚本已就绪。下一步：构建游戏。构建成功后解锁预览。",
  })
}


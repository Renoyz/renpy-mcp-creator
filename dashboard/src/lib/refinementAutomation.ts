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
    message: "Freezing blueprint...",
  })
  await freezeBlueprint(projectName)

  onProgress?.({
    status: "running",
    step: "scene_packages",
    message: "Generating scene packages from the frozen blueprint...",
  })
  while (true) {
    const sceneResp = await request(`/api/projects/${encodeURIComponent(projectName)}/scene-packages/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
    if (!sceneResp.ok) {
      const detail = await parseErrorDetail(sceneResp, `HTTP ${sceneResp.status}`)
      throw new Error(`Scene package generation failed: ${detail}`)
    }
    const sceneBody = await sceneResp.json().catch(() => ({}))
    await refreshProjectData(projectName)
    const sceneGeneration = sceneBody?.scene_generation
    const completed = Number(sceneGeneration?.completed_count ?? 0)
    const total = Number(sceneGeneration?.total_count ?? 0)
    if (total > 0) {
      onProgress?.({
        status: "running",
        step: "scene_packages",
        message: `Generating scene packages from the frozen blueprint... ${completed}/${total} chapters complete`,
      })
    }
    const explicitComplete = sceneBody?.complete === true || sceneGeneration?.status === "complete"
    const legacyComplete = sceneBody?.complete === undefined && sceneGeneration === undefined
    if (explicitComplete || legacyComplete) {
      break
    }
  }

  onProgress?.({
    status: "running",
    step: "prototype",
    message: "Generating prototype scripts from the scene packages...",
  })
  const protoResp = await request(`/api/projects/${encodeURIComponent(projectName)}/prototype/multi-chapter/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
  if (!protoResp.ok) {
    const detail = await parseErrorDetail(protoResp, `HTTP ${protoResp.status}`)
    throw new Error(`Prototype generation failed: ${detail}`)
  }
  await refreshProjectData(projectName)

  onProgress?.({
    status: "running",
    step: "activating",
    message: "Activating generated prototype for build and preview...",
  })
  const activateResp = await request(`/api/projects/${encodeURIComponent(projectName)}/prototype/multi-chapter/activate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
  if (!activateResp.ok) {
    const detail = await parseErrorDetail(activateResp, `HTTP ${activateResp.status}`)
    throw new Error(`Prototype activation failed: ${detail}`)
  }
  await refreshProjectData(projectName)

  onProgress?.({
    status: "success",
    step: "complete",
    message: "Scene packages and prototype scripts are ready. Next step: Build the game. Preview unlocks after a successful build.",
  })
}


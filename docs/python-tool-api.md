# FruitSpy Python Tool API v1

这份文档是 Anomalo agent 接入 FruitSpy Python Tool 的接口契约。FruitSpy 与 Anomalo
必须运行在同一台 Mac 上；执行接口只接受本机 loopback 或明确配置的 Anomalo container
CIDR 请求，并使用共享 Bearer token 鉴权。

## 1. 基本信息

| 项目 | 值 |
| --- | --- |
| Base URL | `http://127.0.0.1:8848` |
| API 前缀 | `/api/v1/tools/python` |
| 协议 | HTTP/1.1 + JSON |
| 执行模式 | 同步请求，同步返回结果 |
| 请求来源 | loopback + `python_tool_allowed_cidrs`（默认 `192.168.64.0/24`） |
| API 版本 | `v1` |

Agent 端应固定 Base URL，不要把 URL、镜像、网络、命令、CPU 或内存做成模型可控制的
参数。

## 2. FruitSpy 配置

先生成一个随机 token，并把同一个值配置给 FruitSpy 和 Anomalo。不要把 token 提交到
Git：

```bash
openssl rand -hex 32
```

FruitSpy 可以通过环境变量配置：

```bash
export FRUITSPY_PYTHON_TOOL_TOKEN="<shared-token>"
```

或者写入 FruitSpy 的 ignored 配置文件 `backend/env.json`：

```json
{
  "python_tool_token": "<shared-token>",
  "python_tool_allowed_cidrs": ["192.168.64.0/24"],
  "python_tool_enabled": false,
  "python_sandbox_image": "anomalo-python:latest",
  "python_sandbox_network": "fruitspy-python-internal",
  "python_sandbox_timeout_seconds": 10,
  "python_sandbox_max_output_chars": 12000,
  "python_sandbox_max_code_bytes": 65536,
  "python_sandbox_cpu_count": 1,
  "python_sandbox_memory_mb": 256,
  "python_sandbox_max_concurrency": 1
}
```

如果配置文件已经存在，只添加或更新相关字段，不要覆盖其他 FruitSpy 配置。配置 token
后需要重启 FruitSpy。

`python_tool_allowed_cidrs` 用于允许 Anomalo Apple container 访问宿主机。默认值
`192.168.64.0/24` 对应当前部署的 container 网络；如果你的 Apple container 网络使用
其他子网，应改成实际的 CIDR。loopback 始终允许，不需要重复写入。

Python Tool 默认关闭。可以在 FruitSpy 的 API 页面点击 Enable，也可以调用下面的管理
接口。启用时 FruitSpy 会检查镜像、内部网络并执行一次 smoke test；检查失败时功能会
保持 enabled，但状态为 `degraded`，执行请求会返回 `503`。

## 3. 状态接口

### `GET /api/v1/tools/python`

不需要 token，供 Dashboard 和 agent 启动检查使用。

请求：

```http
GET /api/v1/tools/python HTTP/1.1
Host: 127.0.0.1:8848
Accept: application/json
```

成功响应 `200 OK`：

```json
{
  "schema_version": 1,
  "id": "python-sandbox",
  "enabled": true,
  "state": "ready",
  "ready": true,
  "image": "anomalo-python:latest",
  "limits": {
    "cpu_count": 1.0,
    "memory_mb": 256,
    "timeout_ms": 10000,
    "max_code_bytes": 65536,
    "max_output_chars": 12000,
    "max_concurrency": 1,
    "max_artifacts": 4,
    "max_artifact_bytes": 2097152,
    "max_artifact_total_bytes": 4194304,
    "artifact_ttl_seconds": 600
  },
  "running_executions": 0,
  "last_execution": null,
  "error": null
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | integer | 当前为 `1`。客户端应拒绝未知的更高版本，或记录兼容性警告。 |
| `enabled` | boolean | 用户是否打开了功能。 |
| `state` | string | `disabled`、`checking`、`ready`、`busy`、`degraded`、`disabling`。 |
| `ready` | boolean | 只有 `ready` 或 `busy` 时为 `true`。 |
| `image` | string | 实际使用的 sandbox 镜像；由 FruitSpy 固定。 |
| `limits` | object | 当前服务端执行限制。 |
| `running_executions` | integer | 当前正在执行的请求数。 |
| `last_execution` | object/null | 最近一次完成的执行；包含 `finished_at`、`status`、`duration_ms`。 |
| `error` | string/null | `degraded` 等状态的可读原因。 |

agent 端只有在 `ready == true` 时才应尝试执行；`busy` 表示服务可用，但并发槽可能已
被占用。

## 4. 启用/禁用接口

这个接口用于 Dashboard 或本机管理员，不是 agent 执行接口。

### `PUT /api/v1/tools/python/enabled`

请求：

```http
PUT /api/v1/tools/python/enabled HTTP/1.1
Host: 127.0.0.1:8848
Content-Type: application/json
X-FruitSpy-Control: 1

{"enabled": true}
```

成功响应为和状态接口相同的 `PythonToolStatus` JSON，HTTP 状态码 `200`。缺少或错误的
`X-FruitSpy-Control: 1` 返回 `403`。

禁用时会立即拒绝新请求；已经开始的执行允许结束，状态可能短暂显示为
`disabling`。

## 5. Python 执行接口

### `POST /api/v1/tools/python/executions`

这是 Anomalo agent 应调用的唯一执行接口。

必需请求头：

```http
Authorization: Bearer <shared-token>
Idempotency-Key: <uuid-v4>
Content-Type: application/json
Accept: application/json
```

请求体：

```json
{
  "code": "print(sum(range(10)))",
  "timeout_ms": 10000,
  "artifacts": [
    {"path": "plot.png", "media_type": "image/png"}
  ]
}
```

| 字段 | 类型 | 必需 | 说明 |
| --- | --- | --- | --- |
| `code` | string | 是 | 要执行的 Python 源码；不能是空白字符串，最大默认 `65536` 字节。 |
| `timeout_ms` | integer/null | 否 | 本次请求希望的超时，最小 `1`。服务端会将它限制在服务端最大值以内；省略时使用服务端默认值。 |
| `artifacts` | array | 否 | 要从 sandbox 的 `/tmp` 返回的文件列表；默认空列表，最多 4 个。 |

`artifacts[].path` 必须是 `/tmp` 下面的单层文件名，例如 `plot.png` 或 `result.csv`，
只能包含字母、数字、`.`、`_`、`-`，不能是绝对路径、不能包含 `..` 或子目录。代码应在
执行过程中把文件写到对应位置。
`media_type` 用于下载响应的 `Content-Type`，省略时为 `application/octet-stream`。

单个 artifact 默认最大 `2 MiB`，一次执行总计最大 `4 MiB`，在响应中返回的是临时下载
URL 而不是 base64。文件在 FruitSpy 内存中默认保留 10 分钟。

完整示例：

```bash
TOKEN="<shared-token>"
REQUEST_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

curl --fail-with-body \
  -X POST \
  "http://127.0.0.1:8848/api/v1/tools/python/executions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Idempotency-Key: ${REQUEST_ID}" \
  -H "Content-Type: application/json" \
  -d '{"code":"print(sum(range(10)))","timeout_ms":10000}'
```

### 5.1 执行成功或 Python 代码失败

只要请求被接受并运行到了 sandbox，结果使用 HTTP `200 OK` 返回。Python 代码本身异常
不是 HTTP 错误，而是执行结果 `ok: false`、`status: "failed"`：

成功示例：

```json
{
  "schema_version": 1,
  "request_id": "8cc27331-16a4-4d23-9827-8a23a04ec987",
  "execution_id": "py-0123456789abcdef",
  "ok": true,
  "status": "succeeded",
  "exit_code": 0,
  "stdout": "45\n",
  "stderr": "",
  "content": "stdout:\n45\n",
  "truncated": {"stdout": false, "stderr": false},
  "duration_ms": 812,
  "image": "anomalo-python:latest",
  "artifacts": [],
  "artifact_errors": []
}
```

Python 异常示例：

```json
{
  "schema_version": 1,
  "request_id": "8cc27331-16a4-4d23-9827-8a23a04ec987",
  "execution_id": "py-fedcba9876543210",
  "ok": false,
  "status": "failed",
  "exit_code": 1,
  "stdout": "",
  "stderr": "ValueError: invalid input\n",
  "content": "stderr:\nValueError: invalid input\n",
  "truncated": {"stdout": false, "stderr": false},
  "duration_ms": 93,
  "image": "anomalo-python:latest",
  "artifacts": [],
  "artifact_errors": []
}
```

超时结果同样返回 HTTP `200`，但 `status` 为 `timed_out`、`ok` 为 `false`、`exit_code`
为 `null`。如果超时前没有输出，`content` 为 `Python sandbox timed out.`。

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `request_id` | string | 规范化后的 `Idempotency-Key` UUID。 |
| `execution_id` | string | FruitSpy 为本次 sandbox 运行生成的 ID。 |
| `ok` | boolean | 仅 `status == "succeeded"` 时为 `true`。 |
| `status` | string | `succeeded`、`failed`、`timed_out`。 |
| `exit_code` | integer/null | 进程退出码；超时为 `null`。 |
| `stdout` / `stderr` | string | 分别截断后的标准输出和标准错误。 |
| `content` | string | 面向 agent/模型的合并可读文本。优先使用这个字段作为 ToolResult content。 |
| `truncated` | object | `stdout` 或 `stderr` 是否被输出上限截断。 |
| `duration_ms` | integer | 实际耗时。 |
| `image` | string | 实际使用的镜像。 |
| `artifacts` | array | 成功采集的文件元数据；包括 `name`、`media_type`、`size_bytes`、`sha256`、`download_url`。 |
| `artifact_errors` | array | 未能采集的请求文件及原因，例如 `file_not_found` 或 `artifact_too_large`。 |

带图执行示例：

```json
{
  "code": "import matplotlib.pyplot as plt\nimport numpy as np\nx=np.linspace(0, 2*np.pi, 100)\nplt.plot(x, np.sin(x))\nplt.savefig('/tmp/sine.png', dpi=120)",
  "artifacts": [
    {"path": "sine.png", "media_type": "image/png"}
  ]
}
```

### 5.2 下载 artifact

执行响应中的 `artifacts[].download_url` 是相对于 Base URL 的临时 URL：

```http
GET /api/v1/tools/python/executions/py-0123456789abcdef/artifacts/sine.png HTTP/1.1
Host: 127.0.0.1:8848
Authorization: Bearer <shared-token>
```

成功时返回 `200 OK` 二进制内容，`Content-Type` 为请求中的 `media_type`，并带有
`Cache-Control: no-store`。下载接口同样只接受 loopback、配置的 container CIDR 和 Bearer token。artifact 过期
或不存在时返回错误 envelope：

```json
{
  "schema_version": 1,
  "request_id": "py-0123456789abcdef",
  "error": {
    "code": "artifact_not_found",
    "message": "Artifact has expired or does not exist",
    "retryable": false
  }
}
```

Agent 端应在收到执行响应后立即下载需要的 artifact；不要把 `download_url` 长期持久化。

## 6. 幂等、重试和错误处理

每一个逻辑上的 agent tool call 都生成一个新的 UUID，并将它作为
`Idempotency-Key`。只有在同一次 HTTP 请求可能因为网络问题没有收到响应时，才使用同一
UUID 重试；不要为同一个逻辑调用生成新的 UUID，否则可能重复执行代码。

FruitSpy 会将已完成结果缓存 10 分钟：同一 UUID 的重试会返回完全相同的结果，不会再次
启动 sandbox。相同 UUID 在首次请求仍运行时返回 `409 request_in_progress`。

非执行结果错误使用以下 envelope：

```json
{
  "schema_version": 1,
  "request_id": "8cc27331-16a4-4d23-9827-8a23a04ec987",
  "error": {
    "code": "sandbox_busy",
    "message": "Python sandbox concurrency limit reached",
    "retryable": true
  }
}
```

错误码：

| HTTP | `error.code` | `retryable` | agent 处理 |
| ---: | --- | :---: | --- |
| 401 | `unauthorized` | false | token 错误；不要自动重试。 |
| 403 | `loopback_required` | false | 请求来源不在 loopback 或 `python_tool_allowed_cidrs`；检查 container 子网配置。 |
| 403 | `control_header_required` | false | 仅启用接口使用；执行接口不会要求此 header。 |
| 409 | `feature_disabled` | false | 先在 FruitSpy API 页面启用功能。 |
| 409 | `request_in_progress` | true | 使用同一 UUID 稍后重试或等待原请求返回。 |
| 413 | `code_too_large` | false | 缩短源码，不能通过请求提高上限。 |
| 422 | `invalid_request` / `invalid_idempotency_key` | false | 修正请求体或 UUID。 |
| 404 | `artifact_not_found` | false | artifact 已过期或不存在；重新执行并立即下载。 |
| 429 | `sandbox_busy` | true | 稍后重试；响应会带 `Retry-After: 1`。 |
| 503 | `authentication_unconfigured` | false | FruitSpy 没有配置 token，需要管理员修复。 |
| 503 | `sandbox_unavailable` | true | 检查镜像、Apple container runtime 和网络；可退避重试。 |

FastAPI 对 JSON 结构错误（例如 `timeout_ms: 0`、缺失 `code`、非法 JSON）可能返回标准
`422` `detail` 数组，而不是上面的自定义 `error` envelope。agent 端应把所有非 `2xx`
响应统一转换成工具失败，不要只解析自定义 envelope。

建议重试策略：

1. `429`：优先遵守 `Retry-After`，再使用 100–500 ms 的随机退避。
2. `503 sandbox_unavailable`：最多退避重试 2–3 次；仍失败则返回 agent 工具错误。
3. `409 request_in_progress`：复用原 UUID 查询/重试，不要新建 UUID。
4. `401`、`403`、`413`、`422`、`feature_disabled`：不要自动重试。

## 7. Anomalo provider 对接建议

Anomalo 可以保留现有的 `sandbox_python_run` tool schema，只替换 provider 的执行实现：

```python
import os
from uuid import uuid4

import httpx


FRUITSPY_PYTHON_URL = "http://127.0.0.1:8848/api/v1/tools/python/executions"


def run_python_via_fruitspy(
    code: str,
    timeout_ms: int | None = None,
    artifacts: list[dict[str, str]] | None = None,
) -> dict:
    # 每个逻辑 tool call 只生成一次；HTTP transport retry 复用这个值。
    request_id = str(uuid4())
    body = {"code": code}
    if timeout_ms is not None:
        body["timeout_ms"] = timeout_ms
    if artifacts:
        body["artifacts"] = artifacts

    response = httpx.post(
        FRUITSPY_PYTHON_URL,
        headers={
            "Authorization": f"Bearer {os.environ['FRUITSPY_PYTHON_TOOL_TOKEN']}",
            "Idempotency-Key": request_id,
            "Content-Type": "application/json",
        },
        json=body,
        # 应略大于服务端 timeout，给本机 HTTP 和 JSON 返回留出余量。
        timeout=(timeout_ms or 10000) / 1000 + 2,
    )

    payload = response.json()
    if response.status_code != 200:
        error = payload.get("error", {})
        raise RuntimeError(
            f"FruitSpy Python Tool failed ({error.get('code', response.status_code)}): "
            f"{error.get('message', response.text)}"
        )

    return payload


def download_fruitspy_artifact(payload: dict, name: str) -> bytes:
    artifact = next(item for item in payload["artifacts"] if item["name"] == name)
    response = httpx.get(
        "http://127.0.0.1:8848" + artifact["download_url"],
        headers={"Authorization": f"Bearer {os.environ['FRUITSPY_PYTHON_TOOL_TOKEN']}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.content
```

然后映射回 Anomalo 当前的 `ToolResult`：

```python
payload = run_python_via_fruitspy(
    code,
    timeout_ms,
    artifacts=[{"path": "plot.png", "media_type": "image/png"}],
)

ToolResult(
    name="sandbox_python_run",
    ok=payload["ok"],
    content=payload["content"],
    data={
        "status": payload["status"],
        "exit_code": payload["exit_code"],
        "stdout": payload["stdout"],
        "stderr": payload["stderr"],
        "truncated": payload["truncated"],
        "image": payload["image"],
        "execution_id": payload["execution_id"],
        "request_id": payload["request_id"],
        "artifacts": payload["artifacts"],
    },
)
```

如果 provider 需要区分“代码运行失败”和“FruitSpy 无法执行”：

- HTTP `200` + `ok: false`：代码已经运行，返回普通工具失败结果，不需要 HTTP 重试。
- 非 `2xx` + `retryable: true`：FruitSpy admission/runtime 问题，可以按上面的策略重试。
- 非 `2xx` + `retryable: false`：配置、鉴权或请求问题，直接返回可读错误。

## 8. 当前 Python 镜像内置库

当前本机 `anomalo-python:latest` 镜像已验证可直接 import 以下库（ARM64 镜像，Python
`3.12.13`）：

| 用途 | import | 当前版本 |
| --- | --- | --- |
| 数值计算 | `numpy` | `2.5.1` |
| 表格和数据分析 | `pandas` | `3.0.3` |
| 科学计算 | `scipy` | `1.18.0` |
| 符号数学 | `sympy` | `1.14.0` |
| 绘图 | `matplotlib` | `3.11.0` |

Matplotlib 已设置为无界面后端 `Agg`，因此 agent 应使用 `matplotlib.pyplot` 生成图形，
不能依赖 GUI 窗口。例如：

```python
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 2 * np.pi, 100)
plt.plot(x, np.sin(x))
plt.title("sin(x)")
plt.savefig("/tmp/sine.png", dpi=120)
```

当前执行接口只返回 `stdout`、`stderr` 和 `content`，不会把 `/tmp/sine.png` 作为图片
artifact 返回；sandbox 结束后文件也会被清理。也就是说，这些库已经能支持数学计算和
绘图生成，但 agent 当前只能读取文本结果。若要让用户直接看到 PNG/SVG，下一版协议需要
增加受限的 artifact 返回字段或独立下载接口，不能把整张图片无上限地塞进 stdout。

`seaborn`、`scikit-learn`、`statsmodels` 等不在当前镜像的已验证基础集合中；如确实需要，
应单独评估镜像体积、启动时间和安全范围后再加入。

## 9. Sandbox 行为和安全边界

FruitSpy 对每次调用启动一个临时 Apple container，并执行：

- 源码通过 stdin 传给 `python -I -u -`，不经过 shell，也不放在命令行参数中。
- 非 root 用户（默认 `65532:65532`）。
- 只读 root filesystem，丢弃 capabilities，无 host volume。
- 固定 CPU、内存、执行超时和输出大小。
- `/tmp` 使用临时 filesystem，禁用 DNS，使用 FruitSpy 内部网络。
- 超时或进程异常时强制清理容器。

当前 Apple container 的 `hostOnly` 内部网络并不等于完整的 guest-to-host egress deny；执行
代码仍应按不可信代码处理，不要把密钥、隐私数据或其他高价值凭据放进源码或环境变量。

## 10. Agent 接入验收清单

- [ ] FruitSpy 与 Anomalo 使用同一个随机 token。
- [ ] Anomalo URL 固定为 `http://127.0.0.1:8848`。
- [ ] 每个逻辑调用生成一个 UUID，并在 transport retry 时复用。
- [ ] provider 正确区分 HTTP `200` 执行结果与非 `2xx` admission/runtime 错误。
- [ ] `429`、`503` 只对 `retryable: true` 做有限退避重试。
- [ ] 不允许模型传入或覆盖 URL、镜像、网络、命令、volume、CPU、内存和 token。
- [ ] FruitSpy API 页面显示 `state: ready` 后再进行真实调用。

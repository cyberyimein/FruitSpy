export type HostMetrics = {
    cpu_percent: number;
    memory_percent: number;
    memory_used_gb: number;
    memory_total_gb: number;
    storage_percent: number;
    storage_used_gb: number;
    storage_total_gb: number;
};

export type ContainerMetrics = {
    id: string;
    name: string;
    image: string;
    status: string;
    cpu_percent: number;
    cpu_limit: number;
    memory_percent: number;
    memory_used_mb: number;
    memory_limit_mb: number;
};

export type Snapshot = {
    timestamp: number;
    host: HostMetrics;
    containers: ContainerMetrics[];
    runtime_name: string;
    runtime_available: boolean;
    runtime_error: string | null;
};

export type RuntimeConfig = {
    runtime_name: string;
    container_control_enabled: boolean;
    refresh_seconds: number;
    logs_tail_default: number;
};

export type PackageRecord = {
    manager: string;
    name: string;
    version: string;
    source: string;
};

export type PackageManagerInventory = {
    manager: string;
    available: boolean;
    command: string | null;
    package_count: number;
    error: string | null;
    packages: PackageRecord[];
};

export type PackageInventory = {
    timestamp: number;
    total_packages: number;
    managers: PackageManagerInventory[];
};

export type PythonToolState = 'disabled' | 'checking' | 'ready' | 'busy' | 'degraded' | 'disabling';

export type PythonToolStatus = {
    schema_version: number;
    id: string;
    enabled: boolean;
    state: PythonToolState;
    ready: boolean;
    image: string;
    limits: {
        cpu_count: number;
        memory_mb: number;
        timeout_ms: number;
        max_code_bytes: number;
        max_output_chars: number;
        max_concurrency: number;
        max_artifacts: number;
        max_artifact_bytes: number;
        max_artifact_total_bytes: number;
        artifact_ttl_seconds: number;
    };
    running_executions: number;
    last_execution: {
        finished_at: string;
        status: 'succeeded' | 'failed' | 'timed_out';
        duration_ms: number;
    } | null;
    error: string | null;
};

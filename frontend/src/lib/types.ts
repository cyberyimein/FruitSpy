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
    memory_percent: number;
    memory_used_mb: number;
    memory_limit_mb: number;
};

export type Snapshot = {
    timestamp: number;
    host: HostMetrics;
    containers: ContainerMetrics[];
    docker_available: boolean;
    docker_error: string | null;
};

export type RuntimeConfig = {
    portainer_url: string;
    refresh_seconds: number;
    logs_tail_default: number;
};
